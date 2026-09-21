"""Task registry.

Adding a task means writing the module and adding one line here. main.py
never changes.
"""

from tasks.mgmt_ip import ManagementIpTask
from tasks.ports import PortsTask

REGISTRY = {
    PortsTask.name: PortsTask,
    ManagementIpTask.name: ManagementIpTask,
}

# Selected by default in the interactive picker.
DEFAULT_TASKS = [PortsTask.name, ManagementIpTask.name]


def choices():
    """[(name, description), ...] in registry order, for the picker."""
    return [(name, cls.description) for name, cls in REGISTRY.items()]


def build(names):
    """Instantiates the named tasks in registry order."""
    unknown = [n for n in names if n not in REGISTRY]
    if unknown:
        raise SystemExit(
            f"Unknown task(s): {', '.join(unknown)}. "
            f"Available: {', '.join(REGISTRY)}"
        )
    return [REGISTRY[name]() for name in REGISTRY if name in names]
