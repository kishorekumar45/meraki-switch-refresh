"""Filesystem side of the tool: backup and report paths, JSON writing.

Task modules should never build paths themselves. They ask for a report or
backup path here so every artifact lands in the same place with the same
timestamped naming.
"""

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict

BACKUP_DIR = Path("backups")
REPORT_DIR = Path("reports")


def now_stamp() -> str:
    """Timestamp for filenames, so artifacts never overwrite each other."""
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dirs() -> None:
    """Creates backups/ and reports/ if they do not exist."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


def save_json(path: Path, data: Any) -> None:
    """Writes data as readable, stable-ordered JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(data, file_handle, indent=2, sort_keys=True)


def report_path(name: str) -> Path:
    """Builds a timestamped path under reports/."""
    return REPORT_DIR / f"{now_stamp()}_{name}.json"


def backup_path(serial: str, label: str) -> Path:
    """Builds a timestamped path under backups/."""
    return BACKUP_DIR / f"{now_stamp()}_{serial}_{label}.json"


def save_report(name: str, data: Any) -> Path:
    """Saves a report and prints where it went."""
    path = report_path(name)
    save_json(path, data)
    print(f"[REPORT] {path}")
    return path


def save_backup(serial: str, data: Dict[str, Any], label: str) -> Path:
    """Backs up a device's current raw config before anything is changed."""
    path = backup_path(serial, label)
    save_json(path, data)
    print(f"[BACKUP] {path}")
    return path
