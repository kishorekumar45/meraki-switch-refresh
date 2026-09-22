"""Drives tasks through preflight, plan, confirmation, apply, and verify."""

from typing import Dict, List

from core import io, ui
from core.task import Context, Task

TOTAL_STEPS = 5


def _rollback_all(applied_by_task: Dict[Task, List[str]], ctx: Context) -> None:
    for task in reversed(list(applied_by_task)):
        ui.section(f"ROLLING BACK: {task.description}")
        task.rollback(ctx, applied_by_task[task])


def run(tasks: List[Task], ctx: Context, dry_run: bool) -> bool:
    ui.progress(1, TOTAL_STEPS, "Preflight checks", "CURRENT")
    for task in tasks:
        ui.section(f"PREFLIGHT: {task.description}")
        task.preflight(ctx)
    ui.progress(1, TOTAL_STEPS, "Preflight checks", "PASS")

    ui.progress(2, TOTAL_STEPS, "Build change plans", "CURRENT")
    plans = {}
    for task in tasks:
        ui.section(f"PLAN: {task.description}")
        plan = task.plan(ctx)
        task.show_plan(ctx, plan)
        plans[task.name] = plan
    ui.progress(2, TOTAL_STEPS, "Build change plans", "PASS")

    pending = [task for task in tasks if plans[task.name]]
    if not pending:
        ui.ok("Nothing to do. Target already matches source.")
        return True

    if dry_run:
        ui.safe("Dry run complete. No Meraki configuration changes were made.")
        return True

    ui.progress(3, TOTAL_STEPS, "Final operator review", "CURRENT")
    management_task = next((task for task in pending if task.name == "mgmt-ip"), None)
    if management_task:
        ui.confirm_management_ip(plans[management_task.name])
    ui.final_change_review(ctx.target, pending, plans)
    ui.confirm_target(ctx.target, len(pending), yes=ctx.yes)
    ui.progress(3, TOTAL_STEPS, "Final operator review", "PASS")

    applied_by_task: Dict[Task, List[str]] = {}
    ui.progress(4, TOTAL_STEPS, "Apply configuration", "CURRENT")
    for task in pending:
        ui.section(f"APPLYING: {task.description}")
        applied, failures = task.apply(ctx, plans[task.name])
        applied_by_task[task] = applied

        if failures:
            io.save_report(f"{ctx.target}_{task.name}_failures", failures)
            ui.fail(f"{task.description} failed on {len(failures)} item(s).")
            _rollback_all(applied_by_task, ctx)
            ui.deployment_failure(task.description, ctx.target, rollback_attempted=True)
            return False
    ui.progress(4, TOTAL_STEPS, "Apply configuration", "PASS")

    ui.progress(5, TOTAL_STEPS, "Verify target", "CURRENT")
    unverified = [task for task in pending if not task.verify(ctx)]
    if unverified:
        names = ", ".join(task.description for task in unverified)
        ui.fail("Verification failed for: " + names)
        _rollback_all(applied_by_task, ctx)
        ui.deployment_failure(f"Verification: {names}", ctx.target, rollback_attempted=True)
        return False

    ui.progress(5, TOTAL_STEPS, "Verify target", "PASS")
    ui.deployment_success(ctx.target, [task.name for task in pending])
    return True
