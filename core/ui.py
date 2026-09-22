"""Console output and operator prompts."""

import re
from typing import Any, Dict, List

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.util import sort_port_ids

console = Console()


# ------------------------------------------------------------- status/output


def section(title: str) -> None:
    console.rule(f"[bold cyan]{title}")


def safe(message: str) -> None:
    console.print(f"[bold green][SAFE][/bold green]     {message}")


def review(message: str) -> None:
    console.print(f"[bold cyan][REVIEW][/bold cyan]   {message}")


def warning(message: str) -> None:
    console.print(f"[bold yellow][WARNING][/bold yellow]  {message}")


def write(message: str) -> None:
    console.print(f"[bold magenta][WRITE][/bold magenta]    {message}")


def ok(message: str) -> None:
    console.print(f"[bold green][PASS][/bold green]     {message}")


def fail(message: str) -> None:
    console.print(f"[bold red][FAIL][/bold red]     {message}")


# Backward-compatible names used by existing modules.
def info(message: str) -> None:
    review(message)


def warn(message: str) -> None:
    warning(message)


def progress(step: int, total: int, label: str, status: str = "CURRENT") -> None:
    colors = {
        "PASS": "green",
        "CURRENT": "cyan",
        "PENDING": "dim",
        "FAIL": "red",
    }
    color = colors.get(status, "white")
    console.print(f"[{color}][{step}/{total}] {label:<30} {status}[/{color}]")


def print_diff_report(diffs: Dict[str, Dict[str, Any]], unit_label: str = "Port") -> None:
    """Renders a full diff map as a table."""
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


def port_plan_summary(plan: Dict[str, Dict[str, Any]], report_path: Any) -> None:
    """Shows decision-level port counts while the report keeps full detail."""
    field_changes = sum(len(payload) for payload in plan.values())
    vlan_changes = sum("vlan" in payload for payload in plan.values())
    type_changes = sum("type" in payload for payload in plan.values())
    enabled_changes = sum("enabled" in payload for payload in plan.values())
    poe_changes = sum("poeEnabled" in payload for payload in plan.values())

    body = (
        f"Ports changing       : [bold]{len(plan)}[/bold]\n"
        f"Field changes        : {field_changes}\n"
        f"VLAN changes         : {vlan_changes}\n"
        f"Port type changes    : {type_changes}\n"
        f"Enabled-state changes: {enabled_changes}\n"
        f"PoE changes          : {poe_changes}\n\n"
        f"Full report: [cyan]{report_path}[/cyan]"
    )
    console.print(Panel(body, title="Port Migration Summary", border_style="cyan"))


def ask_view_port_details() -> bool:
    answer = questionary.confirm(
        "View the full port-by-port differences?",
        default=False,
    ).ask()
    return bool(answer)


def report_conditioned(dropped_by_unit: Dict[str, Dict[str, str]]) -> None:
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
    mode = "[yellow]DRY RUN (read-only)[/yellow]" if dry_run else "[bold red]APPLY[/bold red]"
    body = (
        f"Source : [green]{source}[/green]\n"
        f"Target : [red]{target}[/red]\n"
        f"Tasks  : {', '.join(tasks)}\n"
        f"Mode   : {mode}"
    )
    console.print(Panel(body, title="Meraki Refresh", border_style="cyan"))


def final_change_review(target: str, pending, plans: Dict[str, Any]) -> None:
    lines = [f"Target switch : [bold red]{target}[/bold red]", "", "Changes:"]
    for task in pending:
        plan = plans[task.name]
        if task.name == "ports":
            lines.append(f"• Update {len(plan)} switch port(s)")
        elif task.name == "mgmt-ip":
            ip_address = plan.get("staticIp", "DHCP")
            lines.append(f"• Copy management IPv4 settings ({ip_address})")
        else:
            lines.append(f"• Apply {task.description}")

    lines.extend([
        "",
        "[bold yellow]This operation changes production network configuration.[/bold yellow]",
    ])
    console.print(Panel("\n".join(lines), title="Final Change Review", border_style="red"))


def confirm_management_ip(plan: Dict[str, Any]) -> None:
    ip_address = plan.get("staticIp", "DHCP")
    vlan = plan.get("vlan", "Not configured")
    gateway = plan.get("staticGatewayIp", "DHCP")

    body = (
        "The new switch will receive:\n"
        f"IP address : [bold]{ip_address}[/bold]\n"
        f"VLAN       : {vlan}\n"
        f"Gateway    : {gateway}\n\n"
        "[bold red]The old switch must not remain connected with the same static IP.[/bold red]"
    )
    console.print(Panel(body, title="WARNING: Management IP Change", border_style="yellow"))

    confirmed = questionary.confirm(
        "Confirm the old switch is disconnected before this IP is applied:",
        default=False,
    ).ask()
    if not confirmed:
        raise SystemExit("Management IP safety confirmation was not accepted.")


def deployment_success(target: str, task_names: List[str]) -> None:
    lines = [f"Target : {target}", ""]
    for name in task_names:
        lines.append(f"{name:<18} PASS")
    lines.extend(["", "Backups and reports were saved."])
    console.print(Panel("\n".join(lines), title="Deployment Complete", border_style="green"))


def deployment_failure(failed_step: str, target: str, rollback_attempted: bool) -> None:
    rollback = "ATTEMPTED" if rollback_attempted else "NOT REQUIRED"
    body = (
        f"Failed step     : {failed_step}\n"
        f"Target          : {target}\n"
        f"Rollback status : {rollback}\n\n"
        "[bold yellow]Review the target in Meraki Dashboard and the saved reports before continuing.[/bold yellow]"
    )
    console.print(Panel(body, title="Deployment Stopped", border_style="red"))


def _short(value: Any, limit: int = 28) -> str:
    if value is None:
        return "<not set>"
    if value == "":
        return '""'
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ------------------------------------------------------------ prompts


def confirm_target(target: str, task_count: int, yes: bool = False) -> None:
    if yes:
        write(f"--yes supplied. Writing {task_count} task(s) to {target}.")
        return

    write(f"Ready to write {task_count} task(s) to target {target}.")
    safe("Nothing is written to the source device.")
    answer = questionary.text(
        f"Type the TARGET serial ({target}) to continue:"
    ).ask()
    if answer is None or answer.strip() != target:
        raise SystemExit("Serial did not match. Aborted. No changes applied.")


def ask_serial(label: str) -> str:
    answer = questionary.text(
        f"{label} switch serial:",
        validate=lambda text: True if text.strip() else "Serial cannot be empty",
    ).ask()
    if answer is None:
        raise SystemExit("Cancelled.")
    return answer.strip()


def ask_tasks(choices: List[tuple], default: List[str]) -> List[str]:
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


def ask_store_number() -> str:
    answer = questionary.text(
        "Store number (exactly three digits, for example 072):",
        validate=lambda text: (
            True
            if re.fullmatch(r"\d{3}", text.strip())
            else "Enter exactly three digits, for example 072"
        ),
    ).ask()
    if answer is None:
        raise SystemExit("Cancelled.")
    return answer.strip()


def confirm_store_network(organization: str, network: str) -> bool:
    console.print(
        Panel(
            f"Organization : [cyan]{organization}[/cyan]\n"
            f"Network      : [bold]{network}[/bold]",
            title="Store Network Check",
            border_style="yellow",
        )
    )
    return bool(questionary.confirm("Is this the correct store network?", default=False).ask())


def store_device_counts(store: str, switches: int, access_points: int) -> None:
    console.print(
        f"Store {store}\n"
        f"Existing MS120 switches: {switches}\n"
        f"Existing access points: {access_points}"
    )


def ask_cloud_id(label: str) -> str:
    answer = questionary.text(
        f"{label} Cloud ID:",
        validate=lambda text: True if text.strip() else "Cloud ID cannot be empty",
    ).ask()
    if answer is None:
        raise SystemExit("Cancelled.")
    return answer.strip().upper()


def show_onboarding_plan(network: str, replacements: List[Dict[str, str]]) -> None:
    table = Table(title=f"Onboarding plan — {network}", header_style="bold")
    table.add_column("Device")
    table.add_column("Cloud ID", style="cyan")
    table.add_column("New name", style="green")
    table.add_column("Action", style="yellow")
    for item in replacements:
        table.add_row(item["kind"], item["serial"], item["name"], item["status"])
    console.print(table)


def confirm_onboarding(store: str) -> bool:
    return bool(
        questionary.confirm(
            f"Proceed with adding and renaming devices for Store {store}?",
            default=False,
        ).ask()
    )


def ask_workflow() -> str:
    console.print("\n[bold cyan]Meraki Network Refresh Tool[/bold cyan]\n")
    answer = questionary.select(
        "Select workflow:",
        choices=[
            questionary.Choice("Onboard store devices", value="onboard-store"),
            questionary.Choice("Refresh switch configuration", value="refresh"),
            questionary.Choice(
                "Onboard devices, then refresh switch",
                value="onboard-refresh",
            ),
            questionary.Choice("Exit", value="exit"),
        ],
        default="onboard-refresh",
    ).ask()
    return answer or "exit"
