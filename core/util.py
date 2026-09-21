"""Small shared helpers used by more than one task module."""

import json
from typing import Any, List


def canonical(value: Any) -> Any:
    """Normalizes a value so ordering differences do not create false diffs.

    Sorts lists and dictionary keys, so two configs that mean the same thing
    (for example tags in a different order) compare as equal.
    """
    if isinstance(value, list):
        return sorted(
            (canonical(item) for item in value),
            key=lambda item: json.dumps(item, sort_keys=True),
        )
    if isinstance(value, dict):
        return {key: canonical(value[key]) for key in sorted(value)}
    return value


def sort_port_ids(ids) -> List[str]:
    """Sorts port IDs numerically where possible.

    Falls back to string sorting for unusual layouts such as stacked or
    module ports ("1_1"), so the tool never crashes on an odd switch.
    """
    ids = list(ids)
    try:
        return sorted(ids, key=lambda pid: int(pid))
    except (ValueError, TypeError):
        return sorted(ids, key=str)
