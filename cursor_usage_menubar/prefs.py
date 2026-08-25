from __future__ import annotations

import json
from pathlib import Path

from cursor_usage_menubar.theme import as_theme

PREFS_DIR = Path.home() / "Library/Application Support/cursor-usage-menubar"
PREFS_PATH = PREFS_DIR / "prefs.json"
SCOPES = ("self", "group", "team")
REFRESH_SECONDS = (60, 120, 300, 600)
DEFAULT_REFRESH_SECONDS = 300


def _defaults() -> dict:
    return {
        "scope": "self",
        "group_id": None,
        "theme": "dark",
        "refresh_seconds": DEFAULT_REFRESH_SECONDS,
        "dock_badge": True,
    }


def load_prefs(path: Path | None = None) -> dict:
    target = path or PREFS_PATH
    if not target.exists():
        return _defaults()
    try:
        data = json.loads(target.read_text())
    except (OSError, ValueError):
        return _defaults()
    if not isinstance(data, dict):
        return _defaults()
    group_id = _as_group_id(data.get("group_id"))
    scope = _as_scope(data.get("scope"))
    if data.get("scope") is None and group_id is not None:
        scope = "group"
    return {
        "scope": scope,
        "group_id": group_id,
        "theme": as_theme(data.get("theme")),
        "refresh_seconds": _as_refresh(data.get("refresh_seconds")),
        "dock_badge": _as_bool(data.get("dock_badge"), True),
    }


def save_prefs(prefs: dict, path: Path | None = None) -> None:
    target = path or PREFS_PATH
    current = load_prefs(target) if target.exists() else _defaults()
    current.update(prefs)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scope": _as_scope(current.get("scope")),
        "group_id": _as_group_id(current.get("group_id")),
        "theme": as_theme(current.get("theme")),
        "refresh_seconds": _as_refresh(current.get("refresh_seconds")),
        "dock_badge": _as_bool(current.get("dock_badge"), True),
    }
    target.write_text(json.dumps(payload) + "\n")


def _as_group_id(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_scope(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in SCOPES else "self"


def _as_refresh(value: object) -> int:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return DEFAULT_REFRESH_SECONDS
    return seconds if seconds in REFRESH_SECONDS else DEFAULT_REFRESH_SECONDS


def _as_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value in (1, "1", "true", "True", "yes"):
        return True
    if value in (0, "0", "false", "False", "no"):
        return False
    return default
