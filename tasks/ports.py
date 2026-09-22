"""Switch port configuration migration."""

from typing import Any, Dict, List, Tuple

from core import io, ui
from core.client import with_retry, write_once
from core.task import Context, Task
from core.util import canonical, sort_port_ids

PORT_FIELDS = [
    "name", "tags", "enabled", "profile", "linkNegotiation", "poeEnabled",
    "vlan", "allowedVlans", "portScheduleId", "type", "accessPolicyType",
    "accessPolicyNumber", "voiceVlan", "adaptivePolicyGroupId", "rstpEnabled",
    "stpGuard", "stpPortFastTrunk", "peerSgtCapable", "stormControlEnabled",
    "isolationEnabled", "daiTrusted", "udld", "macAllowList",
    "macWhitelistLimit", "stickyMacAllowList", "stickyMacAllowListLimit",
]
READ_ONLY_OR_UNSUPPORTED = [
    "mirror", "schedule", "adaptivePolicyGroup",
    "linkNegotiationCapabilities", "module", "portId",
]
TRUNK_ONLY_FIELDS = {"allowedVlans", "peerSgtCapable"}
ACCESS_ONLY_FIELDS = {
    "voiceVlan", "accessPolicyType", "accessPolicyNumber", "macAllowList",
    "macWhitelistLimit", "stickyMacAllowList", "stickyMacAllowListLimit",
}
ACCESS_POLICY_DEPENDENT = {
    "accessPolicyNumber": "Custom access policy",
    "macAllowList": "MAC allow list",
    "macWhitelistLimit": "MAC allow list",
    "stickyMacAllowList": "Sticky MAC allow list",
    "stickyMacAllowListLimit": "Sticky MAC allow list",
}
PortMap = Dict[str, Dict[str, Any]]


def get_ports(dashboard, serial: str) -> PortMap:
    ports = with_retry(dashboard.switch.getDeviceSwitchPorts, serial)
    return {str(port["portId"]): port for port in ports}


def normalize(ports: PortMap) -> PortMap:
    return {
        pid: {field: canonical(port[field]) for field in PORT_FIELDS if field in port}
        for pid, port in ports.items()
    }


def incompatible_reason(field: str, port_type: Any, access_policy_type: Any) -> Any:
    if port_type == "access" and field in TRUNK_ONLY_FIELDS:
        return "trunk-only field on an access port"
    if port_type == "trunk" and field in ACCESS_ONLY_FIELDS:
        return "access-only field on a trunk port"
    required = ACCESS_POLICY_DEPENDENT.get(field)
    if required is not None and access_policy_type != required:
        return f"requires accessPolicyType '{required}' (port has '{access_policy_type}')"
    return None


def condition(payload: Dict[str, Any], port: Dict[str, Any]) -> Tuple[Dict, Dict]:
    keep, dropped = {}, {}
    for field, value in payload.items():
        reason = incompatible_reason(field, port.get("type"), port.get("accessPolicyType"))
        if reason is None:
            keep[field] = value
        else:
            dropped[field] = reason
    return keep, dropped


def build_plan(source: PortMap, target: PortMap, dropped_out: Dict = None) -> PortMap:
    changes: PortMap = {}
    for pid in sort_port_ids(source):
        payload = {
            field: value
            for field, value in source[pid].items()
            if value is not None
            and canonical(value) != canonical(target.get(pid, {}).get(field))
        }
        payload, dropped = condition(payload, source[pid])
        if dropped and dropped_out is not None:
            dropped_out[pid] = dropped
        if payload:
            changes[pid] = payload
    return changes


def diff(source: PortMap, target: PortMap) -> Dict[str, Dict[str, Dict[str, Any]]]:
    out = {}
    for pid in sort_port_ids(source):
        src, dst = source[pid], target.get(pid, {})
        changed = {
            field: {"source": src.get(field), "target": dst.get(field)}
            for field in sorted(set(src) | set(dst))
            if canonical(src.get(field)) != canonical(dst.get(field))
        }
        if changed:
            out[pid] = changed
    return out


class PortsTask(Task):
    name = "ports"
    description = "Switch port configuration"

    def __init__(self):
        self.source_norm: PortMap = {}
        self.target_norm: PortMap = {}
        self.target_backup: PortMap = {}

    def preflight(self, ctx: Context) -> None:
        source_raw = get_ports(ctx.dashboard, ctx.source)
        target_raw = get_ports(ctx.dashboard, ctx.target)
        if set(source_raw) != set(target_raw):
            raise SystemExit(
                "Port ID mismatch.\n"
                f"Missing on target: {sort_port_ids(set(source_raw) - set(target_raw))}\n"
                f"Extra on target: {sort_port_ids(set(target_raw) - set(source_raw))}"
            )
        self.source_norm = normalize(source_raw)
        self.target_norm = normalize(target_raw)
        self.target_backup = self.target_norm
        io.save_backup(ctx.source, source_raw, "source_ports_before")
        io.save_backup(ctx.target, target_raw, "target_ports_before")
        unsupported = sorted({
            field for port in source_raw.values()
            for field in READ_ONLY_OR_UNSUPPORTED if field in port
        })
        if unsupported:
            ui.review("Present in GET output but not migrated: " + ", ".join(unsupported))
        ui.safe(f"{len(source_raw)} matching ports found on both switches.")

    def plan(self, ctx: Context) -> PortMap:
        dropped: Dict[str, Dict[str, str]] = {}
        changes = build_plan(self.source_norm, self.target_norm, dropped_out=dropped)
        self._dropped = dropped
        return changes

    def show_plan(self, ctx: Context, plan: PortMap) -> None:
        all_diffs = diff(self.source_norm, self.target_norm)
        ui.report_conditioned(getattr(self, "_dropped", {}))
        if not plan:
            ui.ok("Port configuration already matches source")
            return

        report_path = io.save_report(f"{ctx.source}_to_{ctx.target}_ports_plan", plan)
        ui.port_plan_summary(plan, report_path)
        if ui.ask_view_port_details():
            ui.print_diff_report(all_diffs)

    def apply(self, ctx: Context, plan: PortMap):
        applied: List[str] = []
        failures: List[Tuple[str, str]] = []
        for pid, payload in plan.items():
            try:
                write_once(
                    ctx.dashboard.switch.updateDeviceSwitchPort,
                    serial=ctx.target,
                    portId=pid,
                    **payload,
                )
                applied.append(pid)
                ui.write(f"Updated target port {pid}")
            except Exception as exc:
                failures.append((pid, str(exc)))
                ui.fail(f"Target port {pid}: {exc}")
                break
        return applied, failures

    def verify(self, ctx: Context) -> bool:
        current = normalize(get_ports(ctx.dashboard, ctx.target))
        residual = build_plan(self.source_norm, current)
        if residual:
            ui.fail("Ports: writable differences still exist after apply")
            ui.print_diff_report(diff(self.source_norm, current))
            io.save_report(f"{ctx.source}_to_{ctx.target}_ports_verify_fail", residual)
            return False
        if diff(self.source_norm, current):
            ui.ok("Ports match source for all writable fields")
            ui.review("Remaining differences are non-writable or type-incompatible.")
        else:
            ui.ok("Ports match source for migrated fields")
        return True

    def rollback(self, ctx: Context, applied: List[str]) -> None:
        if not applied:
            ui.safe("No ports were changed.")
            return
        ui.warning(f"Restoring {len(applied)} target port(s) on {ctx.target}.")
        failures = []
        for pid in applied:
            original = self.target_backup.get(pid, {})
            payload = {field: value for field, value in original.items() if value is not None}
            payload, _ = condition(payload, original)
            if not payload:
                continue
            try:
                write_once(
                    ctx.dashboard.switch.updateDeviceSwitchPort,
                    serial=ctx.target,
                    portId=pid,
                    **payload,
                )
            except Exception as exc:
                failures.append((pid, str(exc)))
        if failures:
            path = io.save_report(f"{ctx.target}_ports_rollback_failures", failures)
            ui.warning(f"Some target ports could not be restored. See {path}")
        else:
            ui.ok("Port rollback requests completed.")
