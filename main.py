"""Meraki network refresh and store onboarding entry point."""

import argparse

import tasks
from core import io, runner, ui, validate
from core.client import load_dashboard
from core.task import Context
from workflows import onboard_store


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Onboard replacement devices or migrate Meraki switch configuration."
    )
    parser.add_argument(
        "workflow",
        nargs="?",
        choices=("refresh", "onboard-store"),
        default="refresh",
        help="Workflow to run. Default: refresh",
    )
    parser.add_argument("--store", help="Exactly three digits, for example 072")
    parser.add_argument("--source", help="Source switch serial")
    parser.add_argument("--target", help="Target switch serial")
    parser.add_argument(
        "--tasks",
        help=f"Comma-separated task names. Available: {', '.join(tasks.REGISTRY)}",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show the plan and write nothing")
    parser.add_argument("--yes", action="store_true", help="Skip the target-serial confirmation")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip model validation. Does NOT skip the direction check",
    )
    return parser.parse_args()


def run_refresh(args: argparse.Namespace, dashboard) -> None:
    interactive = not args.source or not args.target
    source = args.source or ui.ask_serial("Source")
    target = args.target or ui.ask_serial("Target")

    ctx = Context(
        dashboard=dashboard,
        source=source,
        target=target,
        yes=args.yes,
        force=args.force,
    )

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


def main() -> None:
    args = parse_args()
    io.ensure_dirs()
    dashboard = load_dashboard()

    if args.workflow == "onboard-store":
        onboard_store.run(dashboard, args.store)
        return

    if args.store:
        raise SystemExit("--store is only valid with the onboard-store workflow.")
    run_refresh(args, dashboard)


if __name__ == "__main__":
    main()
