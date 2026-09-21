"""Meraki network refresh runner.

Run with no arguments for the interactive picker, or pass --source/--target
for automation.

Device validation runs as soon as both serials are known, before any task is
chosen or any config is read.
"""

import argparse

import tasks
from core import io, runner, ui, validate
from core.client import load_dashboard
from core.task import Context


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate Meraki config from a source device to a replacement."
    )
    parser.add_argument("--source", help="Source switch serial")
    parser.add_argument("--target", help="Target switch serial")
    parser.add_argument(
        "--tasks",
        help=f"Comma-separated task names. Available: {', '.join(tasks.REGISTRY)}",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show the plan and write nothing")
    parser.add_argument("--yes", action="store_true",
                        help="Skip the target-serial confirmation")
    parser.add_argument("--force", action="store_true",
                        help="Skip model validation. Does NOT skip the direction check")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    interactive = not args.source or not args.target

    source = args.source or ui.ask_serial("Source")
    target = args.target or ui.ask_serial("Target")

    io.ensure_dirs()
    ctx = Context(
        dashboard=load_dashboard(),
        source=source,
        target=target,
        yes=args.yes,
        force=args.force,
    )

    # Runs before task selection: a wrong pair should stop here, not after
    # the operator has picked tasks and waited through a config read.
    ui.section("DEVICE VALIDATION")
    validate.devices(ctx)

    if args.tasks:
        names = [name.strip() for name in args.tasks.split(",") if name.strip()]
    elif interactive:
        names = ui.ask_tasks(tasks.choices(), tasks.DEFAULT_TASKS)
    else:
        names = tasks.DEFAULT_TASKS

    if args.dry_run:
        dry_run = True
    elif interactive:
        dry_run = ui.ask_dry_run()
    else:
        dry_run = False

    ui.summary_panel(source, target, names, dry_run)

    passed = runner.run(tasks.build(names), ctx, dry_run)

    if not passed:
        raise SystemExit("Refresh did not complete. Review the reports in reports/.")

    ui.section("COMPLETE")
    ui.ok("All selected tasks finished and verified.")


if __name__ == "__main__":
    main()
