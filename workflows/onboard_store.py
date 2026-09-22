"""Claim replacement switches and APs into an exact store network and rename them."""

import string
import time
from typing import Any, Dict, List

from core import ui
from core.client import with_retry, write_once

STORE_MIN = 1
STORE_MAX = 300
SWITCH_SOURCE_MODEL = "MS120"
SWITCH_TARGET_MODEL = "MS130"
AP_TARGET_MODEL = "CW9176I"
DEVICE_WAIT_SECONDS = 180
DEVICE_POLL_SECONDS = 10


def _single_organization(dashboard) -> Dict[str, Any]:
    organizations = with_retry(dashboard.organizations.getOrganizations)
    if len(organizations) != 1:
        raise SystemExit(
            f"Expected access to exactly one Meraki organization; found {len(organizations)}."
        )
    return organizations[0]


def _store_network(dashboard, organization_id: str, store: str) -> Dict[str, Any]:
    prefix = f"Store {store} - "
    networks = with_retry(
        dashboard.organizations.getOrganizationNetworks,
        organization_id,
        total_pages="all",
    )
    matches = [network for network in networks if network.get("name", "").startswith(prefix)]
    if not matches:
        raise SystemExit(f"No Meraki network found for Store {store}.")
    if len(matches) > 1:
        names = ", ".join(network.get("name", "") for network in matches)
        raise SystemExit(
            f"Multiple Meraki networks found for Store {store}: {names}. Review manually."
        )
    return matches[0]


def _replacement_switch_name(existing_name: str, store: str) -> str:
    if "MS120" in existing_name:
        return existing_name.replace("MS120", "MS130", 1)
    raise SystemExit(
        f"Existing switch name '{existing_name}' does not contain MS120. Rename manually."
    )


def _inventory_by_serial(dashboard, organization_id: str) -> Dict[str, Dict[str, Any]]:
    inventory = with_retry(
        dashboard.organizations.getOrganizationInventoryDevices,
        organization_id,
        total_pages="all",
    )
    return {str(device.get("serial", "")).upper(): device for device in inventory}


def _wait_for_device(dashboard, serial: str) -> Dict[str, Any]:
    deadline = time.time() + DEVICE_WAIT_SECONDS
    last_error = None
    while time.time() < deadline:
        try:
            return dashboard.devices.getDevice(serial)
        except Exception as exc:
            last_error = exc
            time.sleep(DEVICE_POLL_SECONDS)
    raise SystemExit(
        f"Device {serial} did not become available in Dashboard within "
        f"{DEVICE_WAIT_SECONDS} seconds: {last_error}"
    )


def _check_model(device: Dict[str, Any], expected: str, label: str) -> None:
    model = str(device.get("model", ""))
    if expected not in model:
        raise SystemExit(
            f"{label} {device.get('serial', '')} has model '{model}', expected '{expected}'."
        )


def _collect_replacements(existing_switches, ap_count: int, store: str):
    replacements = []
    for index, switch in enumerate(existing_switches, start=1):
        serial = ui.ask_cloud_id(f"Replacement switch {index}")
        replacements.append({
            "serial": serial,
            "kind": "switch",
            "expected_model": SWITCH_TARGET_MODEL,
            "name": _replacement_switch_name(str(switch.get("name", "")), store),
        })

    if ap_count > len(string.ascii_uppercase):
        raise SystemExit("More than 26 access points found. Review the store manually.")

    for index in range(ap_count):
        letter = string.ascii_uppercase[index]
        serial = ui.ask_cloud_id(f"Replacement AP {letter}")
        replacements.append({
            "serial": serial,
            "kind": "access point",
            "expected_model": AP_TARGET_MODEL,
            "name": f"CW9176I-S{store}{letter}",
        })

    serials = [item["serial"] for item in replacements]
    if len(serials) != len(set(serials)):
        raise SystemExit("The same Cloud ID was entered more than once.")
    return replacements


def run(dashboard, store_input: str | None = None) -> None:
    """Runs the interactive store onboarding workflow."""
    store = store_input or ui.ask_store_number()
    if not store.isdigit() or len(store) != 3:
        raise SystemExit("Store number must be exactly three digits, for example 072.")
    if not STORE_MIN <= int(store) <= STORE_MAX:
        raise SystemExit("Store number must be between 001 and 300.")

    organization = _single_organization(dashboard)
    network = _store_network(dashboard, organization["id"], store)

    if not ui.confirm_store_network(organization.get("name", ""), network.get("name", "")):
        raise SystemExit("Cancelled. No devices were claimed, moved, or renamed.")

    devices = with_retry(dashboard.networks.getNetworkDevices, network["id"])
    existing_switches = sorted(
        [device for device in devices if SWITCH_SOURCE_MODEL in str(device.get("model", ""))],
        key=lambda device: str(device.get("name", "")),
    )
    existing_aps = [device for device in devices if device.get("productType") == "wireless"]

    ui.store_device_counts(store, len(existing_switches), len(existing_aps))
    if not existing_switches:
        raise SystemExit(f"No {SWITCH_SOURCE_MODEL} switch found in {network.get('name', '')}.")

    replacements = _collect_replacements(existing_switches, len(existing_aps), store)
    inventory = _inventory_by_serial(dashboard, organization["id"])

    to_claim = []
    for item in replacements:
        inventory_device = inventory.get(item["serial"])
        if inventory_device:
            assigned_network = inventory_device.get("networkId")
            if assigned_network and assigned_network != network["id"]:
                raise SystemExit(
                    f"{item['serial']} is assigned to a different network. Review manually."
                )
            _check_model(inventory_device, item["expected_model"], item["kind"].title())
            item["status"] = "already in network" if assigned_network == network["id"] else "claimed, add to network"
            if not assigned_network:
                to_claim.append(item["serial"])
        else:
            item["status"] = "unclaimed, claim into network"
            to_claim.append(item["serial"])

    ui.show_onboarding_plan(network.get("name", ""), replacements)
    if not ui.confirm_onboarding(store):
        raise SystemExit("Cancelled. No devices were claimed, moved, or renamed.")

    if to_claim:
        write_once(
            dashboard.networks.claimNetworkDevices,
            network["id"],
            serials=to_claim,
            addAtomically=True,
        )
        ui.info(f"Claimed/added {len(to_claim)} device(s) to {network.get('name', '')}.")

    for item in replacements:
        device = _wait_for_device(dashboard, item["serial"])
        _check_model(device, item["expected_model"], item["kind"].title())
        if device.get("networkId") != network["id"]:
            raise SystemExit(f"{item['serial']} is not in the expected store network after onboarding.")
        write_once(dashboard.devices.updateDevice, item["serial"], name=item["name"])
        ui.ok(f"{item['serial']} renamed to {item['name']}")

    for item in replacements:
        device = with_retry(dashboard.devices.getDevice, item["serial"])
        if device.get("networkId") != network["id"] or device.get("name") != item["name"]:
            raise SystemExit(f"Verification failed for {item['serial']}.")

    ui.section("ONBOARDING COMPLETE")
    ui.ok(f"Store {store} replacement devices are in {network.get('name', '')} and correctly named.")
    ui.info("Cloud IDs from onboarding are not passed to the ports migration workflow.")
