from __future__ import annotations

import json
from pathlib import Path

PREFS_DIR = Path.home() / "Library/Application Support/cursor-usage-menubar"
PREFS_PATH = PREFS_DIR / "prefs.json"
SCOPES = ("self", "group", "team")


def load_prefs(path: Path | None = None) -> dict:
    target = path or PREFS_PATH
    if not target.exists():
        return {"scope": "self", "group_id": None}
    try:
        data = json.loads(target.read_text())
    except (OSError, ValueError):
        return {"scope": "self", "group_id": None}
    if not isinstance(data, dict):
        return {"scope": "self", "group_id": None}
    group_id = _as_group_id(data.get("group_id"))
    scope = _as_scope(data.get("scope"))
    if data.get("scope") is None and group_id is not None:
        scope = "group"
    return {"scope": scope, "group_id": group_id}


def save_prefs(prefs: dict, path: Path | None = None) -> None:
    target = path or PREFS_PATH
    current = load_prefs(target) if target.exists() else {"scope": "self", "group_id": None}
    current.update(prefs)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scope": _as_scope(current.get("scope")),
        "group_id": _as_group_id(current.get("group_id")),
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
