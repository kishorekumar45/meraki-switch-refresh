"""Management IPv4 migration.

Copies the WAN1 management interface config from the source switch to the
target: static or DHCP, VLAN, address, mask, gateway and DNS.
"""

from typing import Any, Dict, List, Tuple

from core import io, ui
from core.client import with_retry, write_once
from core.task import Context, Task

STATIC_FIELDS = ("staticIp", "staticSubnetMask", "staticGatewayIp")

# The GET response contains read-only fields the PUT endpoint rejects, so a
# rollback must push back only what is writable.
WRITABLE_FIELDS = (
    "usingStaticIp", "vlan", "staticIp", "staticSubnetMask",
    "staticGatewayIp", "staticDns",
)


def build_payload(source_settings: Dict[str, Any]) -> Dict[str, Any]:
    """Builds the wan1 payload from the source's management settings."""
    wan1 = source_settings.get("wan1", {})
    using_static = wan1.get("usingStaticIp", False)

    payload: Dict[str, Any] = {"usingStaticIp": using_static}

    if wan1.get("vlan") is not None:
        payload["vlan"] = wan1["vlan"]

    if using_static:
        missing = [f for f in STATIC_FIELDS if not wan1.get(f)]
        if missing:
            raise SystemExit(
                "Source management interface is missing: " + ", ".join(missing)
            )
        for field in STATIC_FIELDS:
            payload[field] = wan1[field]
        payload["staticDns"] = wan1.get("staticDns", [])

    return payload


def matches(payload: Dict[str, Any], current: Dict[str, Any]) -> bool:
    """True when the target already has the settings this task would push."""
    wan1 = current.get("wan1", {})
    return all(wan1.get(field) == value for field, value in payload.items())


class ManagementIpTask(Task):
    name = "mgmt-ip"
    description = "Management IPv4 interface"

    def __init__(self):
        self.payload: Dict[str, Any] = {}
        self.target_backup: Dict[str, Any] = {}

    def preflight(self, ctx: Context) -> None:
        source_settings = with_retry(
            ctx.dashboard.devices.getDeviceManagementInterface, ctx.source
        )
        self.target_backup = with_retry(
            ctx.dashboard.devices.getDeviceManagementInterface, ctx.target
        )

        io.save_backup(ctx.target, self.target_backup, "target_mgmt_before")
        self.payload = build_payload(source_settings)

    def plan(self, ctx: Context) -> Dict[str, Any]:
        if matches(self.payload, self.target_backup):
            return {}
        return self.payload

    def show_plan(self, ctx: Context, plan: Dict[str, Any]) -> None:
        if not plan:
            ui.ok("Management IPv4 already matches source")
            return

        dns = plan.get("staticDns", [])
        print(f"  Type          : {'Static' if plan['usingStaticIp'] else 'DHCP'}")
        print(f"  LAN IPv4      : {plan.get('staticIp', 'DHCP')}")
        print(f"  VLAN          : {plan.get('vlan', 'Not configured')}")
        print(f"  Subnet mask   : {plan.get('staticSubnetMask', 'DHCP')}")
        print(f"  Gateway       : {plan.get('staticGatewayIp', 'DHCP')}")
        print(f"  Primary DNS   : {dns[0] if len(dns) >= 1 else 'Not configured'}")
        print(f"  Secondary DNS : {dns[1] if len(dns) >= 2 else 'Not configured'}")

    def apply(self, ctx: Context, plan: Dict[str, Any]):
        applied: List[str] = []
        failures: List[Tuple[str, str]] = []
        try:
            write_once(
                ctx.dashboard.devices.updateDeviceManagementInterface,
                serial=ctx.target, wan1=plan,
            )
            applied.append("wan1")
            print("[UPDATED] Management IPv4")
        except Exception as exc:
            failures.append(("wan1", str(exc)))
            print(f"[FAILED] Management IPv4: {exc}")
        return applied, failures

    def verify(self, ctx: Context) -> bool:
        current = with_retry(
            ctx.dashboard.devices.getDeviceManagementInterface, ctx.target
        )
        if matches(self.payload, current):
            ui.ok("Management IPv4 matches source")
            return True

        ui.fail("Management IPv4 does not match source after apply")
        io.save_report(f"{ctx.target}_mgmt_verify_fail",
                       {"expected": self.payload, "actual": current})
        return False

    def rollback(self, ctx: Context, applied: List[str]) -> None:
        if not applied:
            print("[ROLLBACK] Management IPv4 was not changed.")
            return
        original = self.target_backup.get("wan1", {})
        payload = {f: original[f] for f in WRITABLE_FIELDS if f in original}
        try:
            write_once(
                ctx.dashboard.devices.updateDeviceManagementInterface,
                serial=ctx.target, wan1=payload,
            )
            print("[ROLLBACK] Management IPv4 restored.")
        except Exception as exc:
            ui.warn(f"Could not restore management IPv4: {exc}")
