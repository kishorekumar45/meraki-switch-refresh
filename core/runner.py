"""Drives tasks through preflight -> plan -> confirm -> apply -> verify.

Rollback is automatic on failure. There is no opt-in flag for it; a
half-migrated device is never the desired outcome.

A failure in any task rolls back every task that already wrote, in reverse
order. Verification failure is treated as failure, not just a bad exit code.
"""

from typing import Dict, List

from core import io, ui
from core.task import Context, Task


def _rollback_all(applied_by_task: Dict[Task, List[str]], ctx: Context) -> None:
    """Undoes every task that wrote, most recent first."""
    for task in reversed(list(applied_by_task)):
        ui.section(f"ROLLING BACK: {task.description}")
        task.rollback(ctx, applied_by_task[task])


def run(tasks: List[Task], ctx: Context, dry_run: bool) -> bool:
    """Runs every task in order. Returns True on success."""

    for task in tasks:
        ui.section(f"PREFLIGHT: {task.description}")
        task.preflight(ctx)

    plans = {}
    for task in tasks:
        ui.section(f"PLAN: {task.description}")
        plan = task.plan(ctx)
        task.show_plan(ctx, plan)
        plans[task.name] = plan

    pending = [task for task in tasks if plans[task.name]]

    if not pending:
        ui.ok("Nothing to do. Target already matches source.")
        return True

    if dry_run:
        ui.info("Dry run. No changes were made.")
        return True

    ui.section("APPLY")
    ui.confirm_target(ctx.target, len(pending), yes=ctx.yes)

    applied_by_task: Dict[Task, List[str]] = {}

    for task in pending:
        ui.section(f"APPLYING: {task.description}")
        applied, failures = task.apply(ctx, plans[task.name])
        applied_by_task[task] = applied

        if failures:
            io.save_report(f"{ctx.target}_{task.name}_failures", failures)
            ui.fail(f"{task.description} failed on {len(failures)} item(s).")
            _rollback_all(applied_by_task, ctx)
            return False

    ui.section("VERIFY")
    unverified = [task for task in pending if not task.verify(ctx)]

    if unverified:
        ui.fail(
            "Verification failed for: "
            + ", ".join(task.description for task in unverified)
        )
        _rollback_all(applied_by_task, ctx)
        return False

    return True
