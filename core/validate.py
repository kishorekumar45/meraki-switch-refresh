"""Device validation that runs before any task.

These checks are not specific to one task, so they must not live inside one.
Selecting only --tasks mgmt-ip previously skipped them entirely.

Direction is checked even under --force. A reversed source/target pair would
overwrite the production switch with the replacement's factory config and
report success, because verification would compare in the reversed direction
too. No flag may disable that check.
"""

from typing import Any, Dict

from core import ui
from core.client import with_retry
from core.task import Context

SOURCE_MODEL = "MS120-48LP"
TARGET_MODEL = "MS130-48X"


def _device(ctx: Context, serial: str) -> Dict[str, Any]:
    return with_retry(ctx.dashboard.devices.getDevice, serial)


def devices(ctx: Context) -> None:
    """Validates the pair before anything reads or writes device config."""
    if ctx.source == ctx.target:
        raise SystemExit("Source and target serials are the same. Aborting.")

    source = _device(ctx, ctx.source)
    target = _device(ctx, ctx.target)

    source_model = str(source.get("model", ""))
    target_model = str(target.get("model", ""))

    print(f"[DEVICE] Source {ctx.source}: {source_model} ({source.get('name', '')})")
    print(f"[DEVICE] Target {ctx.target}: {target_model} ({target.get('name', '')})")

    _check_network(ctx, source, target)
    _check_direction(ctx, source_model, target_model)
    _check_models(ctx, source_model, target_model)


def _check_network(ctx: Context, source: Dict[str, Any], target: Dict[str, Any]) -> None:
    """Both devices must sit in the same Meraki network."""
    source_network = source.get("networkId")
    target_network = target.get("networkId")

    if not source_network or not target_network:
        raise SystemExit(
            "Could not read the network for one or both devices. "
            "Confirm both serials are claimed into a network."
        )

    if source_network != target_network:
        raise SystemExit(
            "Source and target are in different Meraki networks.\n"
            f"Source {ctx.source}: {source_network}\n"
            f"Target {ctx.target}: {target_network}\n"
            "Move the replacement into the same network before migrating."
        )

    print(f"[NETWORK] Both devices in {source_network}")


def _check_direction(ctx: Context, source_model: str, target_model: str) -> None:
    """Refuses to write to the old switch. Not skippable by --force."""
    if TARGET_MODEL in source_model and SOURCE_MODEL in target_model:
        raise SystemExit(
            "Source and target look reversed.\n"
            f"Source {ctx.source} is a {source_model} (the replacement).\n"
            f"Target {ctx.target} is a {target_model} (the switch in production).\n"
            "This would overwrite the production switch. Swap the serials.\n"
            "This check cannot be skipped with --force."
        )

    if SOURCE_MODEL in target_model:
        raise SystemExit(
            f"Target {ctx.target} is a {target_model}, the model being replaced.\n"
            "The target must be the replacement switch, not the one in production.\n"
            "This check cannot be skipped with --force."
        )


def _check_models(ctx: Context, source_model: str, target_model: str) -> None:
    """Confirms both devices are the expected models. Skippable by --force."""
    if ctx.force:
        ui.info("Model validation skipped (--force). Direction check still enforced.")
        return

    for serial, model, expected in (
        (ctx.source, source_model, SOURCE_MODEL),
        (ctx.target, target_model, TARGET_MODEL),
    ):
        if expected not in model:
            raise SystemExit(
                f"Model check failed for {serial}. Expected '{expected}', got '{model}'. "
                "Re-run with --force if the serials are definitely correct."
            )
