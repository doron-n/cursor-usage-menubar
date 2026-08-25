from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

from cursor_usage_menubar.models import Session
from cursor_usage_menubar.roles import extract_role

DEFAULT_DB = Path.home() / "Library/Application Support/Cursor/User/globalStorage/state.vscdb"

_KEYS = (
    "cursorAuth/accessToken",
    "cursorAuth/cachedEmail",
    "cursorAuth/stripeMembershipType",
    "cursorAuth/cachedTeam",
    "cursorAuth/cachedScopedProfile",
)


def jwt_sub(access_token: str) -> str | None:
    parts = (access_token or "").split(".")
    if len(parts) < 2:
        return None
    payload = parts[1]
    pad = "=" * (-len(payload) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload + pad))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    sub = data.get("sub")
    return str(sub) if sub else None


def session_cookie(sub: str, access_token: str) -> str:
    return "WorkosCursorSessionToken=" + quote(f"{sub}::{access_token}", safe="")


def read_session(db_path: Path | None = None) -> Session | None:
    path = db_path or DEFAULT_DB
    if not path.exists():
        return None
    uri = f"file:{path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error:
        return None
    try:
        placeholders = ",".join("?" * len(_KEYS))
        rows = conn.execute(
            f"SELECT key, value FROM ItemTable WHERE key IN ({placeholders})",
            _KEYS,
        ).fetchall()
    except sqlite3.Error:
        return None
    finally:
        conn.close()

    values = {str(k): (v.decode() if isinstance(v, bytes) else v) for k, v in rows}
    token = values.get("cursorAuth/accessToken") or ""
    sub = jwt_sub(token)
    if not token or not sub:
        return None

    team_id = None
    team_name = None
    team_role = None
    raw_team = values.get("cursorAuth/cachedTeam")
    if raw_team:
        try:
            team = json.loads(raw_team)
            if isinstance(team, dict):
                team_id = team.get("teamId") or team.get("id")
                if team_id is not None:
                    team_id = int(team_id)
                team_name = team.get("name")
                team_role = extract_role(team)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    if not team_role:
        raw_profile = values.get("cursorAuth/cachedScopedProfile")
        if raw_profile:
            try:
                profile = json.loads(raw_profile)
            except (TypeError, ValueError, json.JSONDecodeError):
                profile = None
            if isinstance(profile, dict):
                team_role = extract_role(profile)

    return Session(
        access_token=token,
        sub=sub,
        email=values.get("cursorAuth/cachedEmail") or None,
        team_id=team_id,
        team_name=team_name,
        plan_hint=values.get("cursorAuth/stripeMembershipType") or None,
        team_role=team_role,
    )
