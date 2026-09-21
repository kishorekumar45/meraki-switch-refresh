"""Meraki Dashboard connection and transient-error retry.

Single place where the API key is loaded and where transient failures are
retried. Every task module should call load_dashboard() and wrap its API
calls in with_retry().
"""

import os
import time

try:
    import truststore
except ImportError:
    raise SystemExit(
        "Missing dependency: truststore. Run: python -m pip install truststore"
    )

# Called once, here. The original main.py called this twice.
truststore.inject_into_ssl()

try:
    import meraki
    from dotenv import load_dotenv
except ImportError:
    meraki = None
    load_dotenv = None


# A read can always be retried safely. A write cannot: a timeout or 5xx
# leaves the outcome unknown, and retrying may apply the change twice. Only
# a rate-limit rejection is known not to have been applied.
READ_RETRY_MARKERS = (
    "429", "500", "502", "503", "504",
    "rate limit", "timed out", "timeout",
)
WRITE_RETRY_MARKERS = ("429", "rate limit")
MAX_RETRIES = 4
BASE_BACKOFF_SECONDS = 1.0


def load_dashboard():
    """Loads MERAKI_API_KEY from .env and returns a Dashboard API client.

    wait_on_rate_limit and maximum_retries let the Meraki SDK ride out rate
    limits on its own; with_retry() adds a second safety net.
    """
    if load_dotenv is None or meraki is None:
        raise SystemExit("Missing dependencies. Run: pip install -r requirements.txt")

    load_dotenv()
    api_key = os.getenv("MERAKI_API_KEY")
    if not api_key:
        raise SystemExit(
            "MERAKI_API_KEY missing. Create a .env file with MERAKI_API_KEY=your_key"
        )

    return meraki.DashboardAPI(
        api_key,
        suppress_logging=True,
        print_console=False,
        wait_on_rate_limit=True,
        maximum_retries=MAX_RETRIES,
    )


def _run(func, markers, args, kwargs):
    """Runs a call, retrying only errors matching markers."""
    attempt = 0
    while True:
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            attempt += 1
            text = str(exc).lower()
            if attempt > MAX_RETRIES or not any(m in text for m in markers):
                raise
            delay = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(
                f"[RETRY] transient error ({exc}); "
                f"retry {attempt}/{MAX_RETRIES} in {delay:.1f}s"
            )
            time.sleep(delay)


def with_retry(func, *args, **kwargs):
    """For reads. Retries rate limits, timeouts and 5xx."""
    return _run(func, READ_RETRY_MARKERS, args, kwargs)


def write_once(func, *args, **kwargs):
    """For writes. Retries only a rate-limit rejection.

    A timeout or 5xx is not retried: the write may already have landed, and
    repeating it would apply the change twice.
    """
    return _run(func, WRITE_RETRY_MARKERS, args, kwargs)
