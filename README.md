# Meraki Network Refresh Tool

[#meraki-network-refresh-tool](#meraki-network-refresh-tool)

![Python Check](https://github.com/kishorekumar45/meraki-switch-refresh/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/Python-3.13-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)
![Cisco Meraki](https://img.shields.io/badge/Cisco-Meraki-67B346)
![Tasks](https://img.shields.io/badge/Tasks-ports%20%7C%20mgmt--ip-blue)
![API](https://img.shields.io/badge/Meraki-Dashboard_API-orange)
![Status](https://img.shields.io/badge/Status-Production-brightgreen)

This is the production tool for refreshing Cisco Meraki network hardware. It
currently migrates switch port configuration and the management IPv4
interface from an existing Meraki MS120-48LP switch to a replacement
MS130-48X switch, as two independently selectable tasks.

This tool **does** connect to Meraki Dashboard.
This tool **does** use the Meraki API.
This tool **does** require a `.env` file with a valid Meraki API key.

The tool reads from the source device and writes only to the target device.
No code path writes to the source.

Run with no arguments for an interactive wizard, or pass `--source` and
`--target` for a scripted, non-interactive run.

---

## What This Tool Does

[#what-this-tool-does](#what-this-tool-does)

The tool uses real Meraki Dashboard API calls to:

- Validate the device pair before anything else happens
- Read configuration from the source device
- Read configuration from the target device
- Build a change plan of only what differs
- Back up source and target configuration
- Apply the change plan to the target
- Re-read the target
- Verify that the target matches the source for migrated fields

Two tasks are available today:

| Task      | What it migrates                                                        |
| --------- | ------------------------------------------------------------------------ |
| `ports`   | Per-port config: VLAN, PoE, STP, port security, tags, and more           |
| `mgmt-ip` | The WAN1 management interface: static/DHCP, address, mask, gateway, DNS  |

Both are selected by default. More tasks (access points, firewall rules,
DHCP reservations) are designed to plug in the same way. See
[Adding a New Task](#adding-a-new-task).

---

## Device Protection

[#device-protection](#device-protection)

The switch being replaced is still in production. Five separate layers
prevent the tool from writing to it:

1. Every write call hardcodes the target serial. No code path writes to the
   source device.
2. A direction check refuses to run if the target is an MS120-48LP, the
   model being replaced. **This check cannot be skipped with `--force`.**
3. A reversed-pair check detects a source/target swap and names both devices
   so the mistake is obvious.
4. A network check refuses to run if the two devices are in different Meraki
   networks, or if either network cannot be read.
5. Confirmation requires typing the **target serial**, not a fixed word.
   Typing the source serial is rejected.

Example of a blocked reversed run:

```text
[DEVICE] Source Q3LV-JRJY-4EW3: MS130-48X (NEW-SW-IDF1)
[DEVICE] Target Q2GX-B3FM-HBTM: MS120-48LP (OLD-SW-IDF1)

Source and target look reversed.
Target Q2GX-B3FM-HBTM is a MS120-48LP (the switch in production).
This would overwrite the production switch. Swap the serials.
This check cannot be skipped with --force.
```

---

## Files and Folders

[#files-and-folders](#files-and-folders)

```text
main.py
.env
requirements.txt
core/
tasks/
backups/
reports/
```

### File Purpose

[#file-purpose](#file-purpose)

**main.py**
Entry point. Parses arguments, runs the interactive wizard if `--source` or
`--target` is missing, validates the device pair, then hands off to the
runner.

**.env**
Stores the Meraki API key.

**requirements.txt**
Lists required Python packages.

**core/**
Shared machinery every task uses: dashboard connection and retry
(`client.py`), device pair validation (`validate.py`), backups and reports
(`io.py`), console output and prompts (`ui.py`), the task contract
(`task.py`), the phase runner (`runner.py`), and small shared helpers
(`util.py`).

**tasks/**
One file per task, plus `__init__.py` as the task registry. This is the
only file you edit to add or remove a task.

**backups/**
Stores source and target configuration backups taken before any change.

**reports/**
Stores diff reports, change plans, and verification failure reports.

---

## Setup

[#setup](#setup)

Install dependencies:
powershell: pip install -r requirements.txt

Create a `.env` file in the project root:
MERAKI_API_KEY=your_meraki_api_key_here

Confirm the `.env` file is named exactly `.env`.

---

## Recommended Command

[#recommended-command](#recommended-command)

For most refreshes, run the tool with no arguments and follow the prompts:

powershell: python main.py

This asks for the source serial, the target serial, which tasks to run, and
whether to dry-run or apply.

### What this does

[#what-this-does](#what-this-does)

1. Prompts for the source and target device serials.
2. Validates the pair immediately: same network, correct direction, expected
   models. A wrong pair stops here, before any config is read.
3. Prompts for which tasks to run (checkbox list).
4. Prompts for dry-run or apply.
5. Runs preflight checks for every selected task.
6. Builds and displays the change plan for every selected task.
7. Requires the **target serial** to be typed before writing.
8. Applies changes.
9. Rolls back every task that wrote if any task fails or fails verification.
10. Re-reads the target and verifies every selected task.

Expected successful final output:

```text
COMPLETE
----------------------------------------------------------------------
PASS  All selected tasks finished and verified.
```

---

## Non-Interactive Command

[#non-interactive-command](#non-interactive-command)

For scripting or automation:

powershell: python main.py --source OLD_SERIAL --target NEW_SERIAL --tasks ports,mgmt-ip --yes

Example:
powershell: python main.py --source Q2GX-B3FM-HBTM --target Q3LV-JRJY-4EW3 --tasks ports,mgmt-ip --yes

Use `--yes` only after you are confident the plan output would be correct.
Run the same command with `--dry-run` first to preview it.

---

## Flags

[#flags](#flags)

### Dry run — preview without writing

[#dry-run-preview-without-writing](#dry-run-preview-without-writing)

powershell: python main.py --source OLD_SERIAL --target NEW_SERIAL --dry-run

What this does:
Validates the pair, runs preflight, and builds the change plan for the
selected tasks. Makes **no** write API calls.

---

### Choose which tasks run

[#choose-which-tasks-run](#choose-which-tasks-run)

powershell: --tasks ports
powershell: --tasks mgmt-ip
powershell: --tasks ports,mgmt-ip

Comma-separated, no spaces. Omit `--tasks` in non-interactive mode to run
the default set (`ports,mgmt-ip`). Omit it in interactive mode to get the
checkbox picker instead.

---

### Skip the target-serial confirmation

[#skip-the-target-serial-confirmation](#skip-the-target-serial-confirmation)

powershell: --yes

Skips the prompt that requires typing the target serial. Use only in
scripted runs where the plan has already been reviewed. All device
validation still runs.

---

### Skip model validation

[#skip-model-validation](#skip-model-validation)

powershell: --force

Skips checking that the source and target are the expected switch models.

**`--force` does not skip the direction check.** The tool will still refuse
to write to an MS120-48LP target, and will still refuse a reversed
source/target pair. Those checks cannot be disabled.

---

## Important Notes

[#important-notes](#important-notes)

- The tool makes real Meraki Dashboard API calls.
- Only the target device is ever written to.
- Always review the plan output before typing the target serial.
- Keep the generated backup and report files for change records.
- A failure in any task rolls back every task that already wrote, in reverse
  order. Verification failure counts as failure.
- Reads are retried on rate limits, timeouts and 5xx. Writes are retried
  only on a rate-limit rejection, because a timed-out write may already have
  landed.
- Port mirroring is reported as unsupported/read-only and is not migrated.
- Pressing Ctrl+C during the apply phase does not trigger rollback. Let a
  failing run finish so rollback can complete.

---

## Adding a New Task

[#adding-a-new-task](#adding-a-new-task)

Every task in `tasks/` implements the same contract (`core/task.py`):
`preflight`, `plan`, `show_plan`, `apply`, `verify`, `rollback`.
`core/runner.py` drives every task through the same sequence, so a new task
never requires changing `main.py`.

To add one:

1. Write `tasks/your_task.py`, implementing the `Task` contract.
2. Add one line to the registry in `tasks/__init__.py`.

It then appears in the interactive picker and works with `--tasks`
automatically.

---

## Safe Production Flow

[#safe-production-flow](#safe-production-flow)

Best practice sequence:

```text
powershell:
    python main.py --source OLD_SERIAL --target NEW_SERIAL --dry-run
    python main.py --source OLD_SERIAL --target NEW_SERIAL --tasks ports,mgmt-ip
```

Run the dry run first and read the plan table. Then run the apply command
without `--yes` so the target serial must be typed before anything is
written.

Expected final output:

```text
COMPLETE
----------------------------------------------------------------------
PASS  All selected tasks finished and verified.
```

---

## Known Limitations

[#known-limitations](#known-limitations)

- Pressing Ctrl+C mid-apply leaves the target partially migrated with no
  automatic rollback. Restore from the backup in `backups/`.
- Rollback cannot restore a field whose original value was null.
- The tool does not verify that the target is unconfigured. Any MS130-48X in
  the same network is accepted as a valid target.
- Backup files are written during preflight, including on a dry run. No
  Meraki writes occur on a dry run.
