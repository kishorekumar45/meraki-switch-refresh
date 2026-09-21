"""The contract every task module implements.

A task is one unit of refresh work: switch ports, management IP, APs,
firewall rules, DHCP reservations. core/runner.py drives all of them
through the same sequence, so adding a task never means editing main.py.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class Context:
    """Everything a task needs to do its work."""
    dashboard: Any
    source: str
    target: str
    yes: bool = False
    force: bool = False


class Task:
    """Subclass this and override what you need.

    plan() returns something truthy when there is work to do, falsy when the
    target already matches. The runner uses that to decide whether to prompt.
    """

    name = ""
    description = ""

    def preflight(self, ctx: Context) -> None:
        """Validate. Raise SystemExit to stop the whole run."""

    def plan(self, ctx: Context) -> Any:
        """Return the changes this task would make. Read-only."""
        return {}

    def show_plan(self, ctx: Context, plan: Any) -> None:
        """Print the plan for the operator."""

    def apply(self, ctx: Context, plan: Any) -> Tuple[List[str], List[Tuple[str, str]]]:
        """Write the plan. Returns (applied_ids, failures)."""
        return [], []

    def verify(self, ctx: Context) -> bool:
        """Re-read the target and confirm the task's work landed."""
        return True

    def rollback(self, ctx: Context, applied: List[str]) -> None:
        """Best-effort undo of only what apply() actually changed."""
