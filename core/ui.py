"""Console output and operator prompts.

Every module prints through here. Nothing calls print() or input() directly,
so the look of the tool can change in one place.
"""

from typing import Any, Dict, List

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.util import sort_port_ids

console = Console()


# ------------------------------------------------------------- output


def section(title: str) -> None:
    console.rule(f"[bold cyan]{title}")


def info(message: str) -> None:
    console.print(f"[cyan]INFO[/cyan]  {message}")


def warn(message: str) -> None:
    console.print(f"[yellow]WARN[/yellow]  {message}")


def ok(message: str) -> None:
    console.print(f"[bold green]PASS[/bold green]  {message}")


def fail(message: str) -> None:
    console.print(f"[bold red]FAIL[/bold red]  {message}")


def print_diff_report(diffs: Dict[str, Dict[str, Any]], unit_label: str = "Port") -> None:
    """Renders a diff map as a table.

    diffs is {unit_id: {field: {"source": ..., "target": ...}}}
    """
    if not diffs:
        ok("No differences found")
        return

    table = Table(show_lines=False, header_style="bold")
    table.add_column(unit_label, justify="right", style="bold yellow", no_wrap=True)
    table.add_column("Field", style="cyan")
    table.add_column("Source", style="green")
    table.add_column("Target", style="red")

    for unit_id in sort_port_ids(diffs):
        first = True
        for field, values in diffs[unit_id].items():
            table.add_row(
                unit_id if first else "",
                field,
                _short(values["source"]),
                _short(values["target"]),
            )
            first = False

    console.print(table)

    fields = sum(len(changes) for changes in diffs.values())
    console.print(
        f"[dim]{len(diffs)} {unit_label.lower()}(s) differ, "
        f"{fields} field difference(s)[/dim]"
    )


def report_conditioned(dropped_by_unit: Dict[str, Dict[str, str]]) -> None:
    """Explains which fields were dropped from the plan, and why."""
    if not dropped_by_unit:
        return

    table = Table(title="Skipped as not applicable", header_style="bold", title_style="")
    table.add_column("Port", justify="right", style="bold yellow")
    table.add_column("Field", style="cyan")
    table.add_column("Reason", style="dim")

    for unit_id in sort_port_ids(dropped_by_unit):
        for field, reason in dropped_by_unit[unit_id].items():
            table.add_row(unit_id, field, reason)

    console.print(table)


def summary_panel(source: str, target: str, tasks: List[str], dry_run: bool) -> None:
    """Shows what is about to happen before the operator confirms."""
    mode = "[yellow]DRY RUN (read-only)[/yellow]" if dry_run else "[bold red]APPLY[/bold red]"
    body = (
        f"Source : [green]{source}[/green]\n"
        f"Target : [red]{target}[/red]\n"
        f"Tasks  : {', '.join(tasks)}\n"
        f"Mode   : {mode}"
    )
    console.print(Panel(body, title="Meraki Refresh", border_style="cyan"))


def _short(value: Any, limit: int = 28) -> str:
    if value is None:
        return "<not set>"
    if value == "":
        return '""'
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ------------------------------------------------------------ prompts


def confirm_target(target: str, task_count: int, yes: bool = False) -> None:
    """Requires the operator to type the TARGET serial before anything is written.

    Typing a fixed word proves only that someone is present. Typing the
    serial that is about to be overwritten proves they know which device it
    is, which is the mistake that actually costs an outage.
    """
    if yes:
        info(f"--yes supplied. Writing to {target} without confirmation.")
        return

    console.print(
        f"\n[bold red]About to write {task_count} task(s) to {target}.[/bold red]\n"
        "[dim]Nothing is written to the source device.[/dim]"
    )
    answer = questionary.text(
        f"Type the TARGET serial ({target}) to continue:"
    ).ask()

    if answer is None or answer.strip() != target:
        raise SystemExit("Serial did not match. Aborted. No changes applied.")


def ask_serial(label: str) -> str:
    """Prompts for a switch serial and rejects an empty answer."""
    answer = questionary.text(
        f"{label} switch serial:",
        validate=lambda text: True if text.strip() else "Serial cannot be empty",
    ).ask()
    if answer is None:
        raise SystemExit("Cancelled.")
    return answer.strip()


def ask_tasks(choices: List[tuple], default: List[str]) -> List[str]:
    """Checkbox picker. choices is [(name, description), ...]."""
    selected = questionary.checkbox(
        "Select the tasks to run:",
        choices=[
            questionary.Choice(
                title=f"{name} — {description}",
                value=name,
                checked=name in default,
            )
            for name, description in choices
        ],
    ).ask()
    if not selected:
        raise SystemExit("No tasks selected. Nothing to do.")
    return selected


def ask_dry_run() -> bool:
    """Defaults to the safe option."""
    answer = questionary.select(
        "Run mode:",
        choices=[
            questionary.Choice("Dry run — show changes, write nothing", value=True),
            questionary.Choice("Apply — write changes to the target", value=False),
        ],
    ).ask()
    if answer is None:
        raise SystemExit("Cancelled.")
    return answer
