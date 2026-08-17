# Cursor Usage Menu Bar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a local macOS menu-bar app that shows live Cursor plan spend/% from the signed-in session, with a native Auto-accordion model breakdown, without ever storing tokens.

**Architecture:** `auth.py` reads Cursor's `state.vscdb` read-only and builds a session cookie from JWT `sub` + access token, then drops the token. `client.py` merges unofficial usage APIs into a token-free `UsageSnapshot`. `app.py` (rumps) shows INFO + ACTIONS and polls every 5 minutes. `breakdown.py` is one reusable AppKit window.

**Tech Stack:** Python 3, rumps, certifi, PyObjC/AppKit, stdlib unittest, urllib, sqlite3.

**Spec:** `docs/superpowers/specs/2026-08-17-cursor-usage-menubar-design.md`

## Global Constraints

- macOS only.
- Python 3 + rumps + PyObjC (Cocoa / AppKit).
- Use certifi for SSL (system Python often fails certificate verification).
- Never prompt for an API key.
- Never persist tokens (files, Keychain, logs, env files, in-memory caches across polls).
- Never write back to Cursor's `state.vscdb`.
- Do not call `POST https://api2.cursor.sh/oauth/token`.
- Do not put hierarchical model lists in the rumps menu.
- Unofficial Cursor APIs can change or break without notice; isolate parsing; document the risk in README.
- No secrets in the repository.
- Title format: `Cursor · $<spend> · <percent>%` or `Cursor · —` when spend or percent is unknown.
- Poll every 5 minutes.
- LaunchAgent label: `com.cursor-usage.menubar`.
- Project path: `~/Projects/cursor-usage-menubar`.

## File structure

| File | Responsibility |
|---|---|
| `.gitignore` | Ignore `.venv/`, `__pycache__/`, `.DS_Store`, logs |
| `requirements.txt` | `rumps`, `certifi`, `pyobjc-framework-Cocoa` |
| `run.py` | Entry: `CursorUsageApp().run()` |
| `install.sh` | `run` / `install` / `uninstall` / `status` |
| `README.md` | Usage, unofficial API warning, no-token policy |
| `cursor_usage_menubar/__init__.py` | Package marker |
| `cursor_usage_menubar/formatters.py` | Dollars, percent, menu title, display labels |
| `cursor_usage_menubar/auth.py` | JWT `sub`, cookie, read-only session |
| `cursor_usage_menubar/models.py` | `Session`, `ModelSpend`, `UsageSnapshot` |
| `cursor_usage_menubar/merge.py` | Merge rules + Auto child scaling (pure) |
| `cursor_usage_menubar/client.py` | HTTPS fetch + `fetch_usage()` |
| `cursor_usage_menubar/app.py` | rumps menu bar |
| `cursor_usage_menubar/breakdown.py` | Native AppKit window |
| `cursor_usage_menubar/verify.py` | Redacted live snapshot print (no tokens) |
| `tests/test_formatters.py` | Title / cents / percent / Auto event matching |
| `tests/test_auth.py` | Cookie, JWT, sqlite read-only, no refresh token |
| `tests/test_merge.py` | Enterprise-first merge, Auto scaling |
| `tests/test_client.py` | HTTP merge with mocked urlopen |

`models.py` and `merge.py` are split out of `client.py` so merge logic is testable without HTTPS. `client.py` remains the public fetch façade specified in the design.

---

### Task 1: Formatters (title, cents, percent, Auto matching)

**Files:**
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `cursor_usage_menubar/__init__.py`
- Create: `cursor_usage_menubar/formatters.py`
- Test: `tests/test_formatters.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `dollars(cents: int) -> str` (example: `23734` → `"$237.34"`)
  - `percent_used(used: int, limit: int) -> int | None` (integer percent; `None` if limit <= 0)
  - `menu_title(spent_cents: int | None, percent: int | None) -> str`
  - `is_auto_event(model_name: str) -> bool`
  - `is_auto_intent(model_intent: str) -> bool`
  - `child_label(model_name: str) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_formatters.py`:

```python
import unittest

from cursor_usage_menubar.formatters import (
    child_label,
    dollars,
    is_auto_event,
    is_auto_intent,
    menu_title,
    percent_used,
)


class FormattersTest(unittest.TestCase):
    def test_dollars_two_places(self):
        self.assertEqual(dollars(23734), "$237.34")
        self.assertEqual(dollars(0), "$0.00")

    def test_percent_integer_and_none_without_limit(self):
        self.assertEqual(percent_used(23734, 50000), 47)
        self.assertIsNone(percent_used(100, 0))
        self.assertIsNone(percent_used(100, -1))

    def test_menu_title_live_and_unknown(self):
        self.assertEqual(menu_title(23734, 48), "Cursor · $237.34 · 48%")
        self.assertEqual(menu_title(None, None), "Cursor · —")
        self.assertEqual(menu_title(100, None), "Cursor · —")
        self.assertEqual(menu_title(None, 10), "Cursor · —")

    def test_auto_event_matching(self):
        self.assertTrue(is_auto_event("Cursor Grok 4.5 (Auto Balanced)"))
        self.assertTrue(is_auto_event("Composer (default)"))
        self.assertFalse(is_auto_event("Cursor Grok 4.5"))

    def test_auto_intent(self):
        self.assertTrue(is_auto_intent("auto-smart"))
        self.assertTrue(is_auto_intent("auto"))
        self.assertFalse(is_auto_intent("claude-4.6-sonnet"))

    def test_child_label_strips_auto_suffix(self):
        self.assertEqual(
            child_label("Cursor Grok 4.5 (Auto Balanced)"),
            "Grok 4.5",
        )


if __name__ == "__main__":
    unittest.main()
```

Create empty `cursor_usage_menubar/__init__.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_formatters -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'cursor_usage_menubar.formatters'`

- [ ] **Step 3: Write minimal implementation**

`.gitignore`:

```
.venv/
__pycache__/
*.pyc
.DS_Store
*.log
```

`requirements.txt`:

```
rumps
certifi
pyobjc-framework-Cocoa
```

`cursor_usage_menubar/formatters.py`:

```python
from __future__ import annotations

import re

_AUTO_INTENTS = frozenset({"auto", "auto-smart", "default", "composer-auto"})
_AUTO_EVENT_RE = re.compile(r"\(auto|\bdefault\b", re.IGNORECASE)
_CURSOR_PREFIX_RE = re.compile(r"^Cursor\s+", re.IGNORECASE)
_AUTO_SUFFIX_RE = re.compile(r"\s*\((?:Auto|Default)[^)]*\)\s*$", re.IGNORECASE)


def dollars(cents: int) -> str:
    return f"${cents / 100.0:.2f}"


def percent_used(used: int, limit: int) -> int | None:
    if limit <= 0:
        return None
    return int((used / limit) * 100)


def menu_title(spent_cents: int | None, percent: int | None) -> str:
    if spent_cents is None or percent is None:
        return "Cursor · —"
    return f"Cursor · {dollars(spent_cents)} · {percent}%"


def is_auto_event(model_name: str) -> bool:
    return bool(_AUTO_EVENT_RE.search(model_name or ""))


def is_auto_intent(model_intent: str) -> bool:
    mi = (model_intent or "").strip().lower()
    return mi in _AUTO_INTENTS or "auto" in mi


def child_label(model_name: str) -> str:
    label = _AUTO_SUFFIX_RE.sub("", model_name or "").strip()
    label = _CURSOR_PREFIX_RE.sub("", label).strip()
    return label or model_name
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_formatters -v`

Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add .gitignore requirements.txt cursor_usage_menubar/__init__.py cursor_usage_menubar/formatters.py tests/test_formatters.py
git commit -m "$(cat <<'EOF'
Add money, title, and Auto-matching formatters.

EOF
)"
```

---

### Task 2: Read-only Cursor session (no token retention)

**Files:**
- Create: `cursor_usage_menubar/models.py` (Session only for now; later tasks append)
- Create: `cursor_usage_menubar/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `formatters` unused; stdlib sqlite3 / json / base64
- Produces:
  - `@dataclass(frozen=True) class Session` with fields `email: str | None`, `team_id: int | None`, `team_name: str | None`, `plan_hint: str | None`, `access_token: str`, `sub: str`
  - `jwt_sub(access_token: str) -> str | None`
  - `session_cookie(sub: str, access_token: str) -> str`
  - `DEFAULT_DB: Path`
  - `read_session(db_path: Path | None = None) -> Session | None`
  - Session has **no** `refresh_token` field
  - SQL in `read_session` must not mention `refreshToken`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_auth.py`:

```python
from __future__ import annotations

import base64
import inspect
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cursor_usage_menubar.auth import jwt_sub, read_session, session_cookie
from cursor_usage_menubar.models import Session


def _jwt(sub: str) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload = (
        base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode())
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{payload}.sig"


def _write_db(values: dict[str, str]) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".vscdb", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
    conn.executemany(
        "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
        list(values.items()),
    )
    conn.commit()
    conn.close()
    return path


class AuthTest(unittest.TestCase):
    def test_cookie_encodes_double_colon(self):
        token = "abc.def.ghi"
        cookie = session_cookie("user_1", token)
        self.assertTrue(cookie.startswith("WorkosCursorSessionToken="))
        self.assertIn("%3A%3A", cookie)
        self.assertNotIn("::", cookie.split("=", 1)[1])

    def test_jwt_sub(self):
        self.assertEqual(jwt_sub(_jwt("user_99")), "user_99")
        self.assertIsNone(jwt_sub("not-a-jwt"))

    def test_read_session_from_sqlite(self):
        token = _jwt("auth0|abc")
        path = _write_db(
            {
                "cursorAuth/accessToken": token,
                "cursorAuth/cachedEmail": "ada@example.com",
                "cursorAuth/stripeMembershipType": "enterprise",
                "cursorAuth/cachedTeam": json.dumps(
                    {"teamId": 42, "name": "Acme"}
                ),
                "cursorAuth/refreshToken": "SHOULD_NEVER_BE_READ",
            }
        )
        try:
            sess = read_session(path)
            self.assertIsNotNone(sess)
            assert sess is not None
            self.assertEqual(sess.email, "ada@example.com")
            self.assertEqual(sess.team_id, 42)
            self.assertEqual(sess.team_name, "Acme")
            self.assertEqual(sess.plan_hint, "enterprise")
            self.assertEqual(sess.sub, "auth0|abc")
            self.assertEqual(sess.access_token, token)
            self.assertFalse(hasattr(sess, "refresh_token"))
        finally:
            path.unlink(missing_ok=True)

    def test_missing_db_returns_none(self):
        self.assertIsNone(read_session(Path("/tmp/does-not-exist-cursor.vscdb")))

    def test_session_dataclass_has_no_refresh_field(self):
        self.assertNotIn("refresh_token", Session.__dataclass_fields__)

    def test_read_session_sql_ignores_refresh_token(self):
        source = inspect.getsource(read_session)
        self.assertNotIn("refreshToken", source)
        self.assertNotIn("refresh_token", source)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_auth -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'cursor_usage_menubar.auth'`

- [ ] **Step 3: Write minimal implementation**

`cursor_usage_menubar/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Session:
    access_token: str
    sub: str
    email: str | None = None
    team_id: int | None = None
    team_name: str | None = None
    plan_hint: str | None = None
```

`cursor_usage_menubar/auth.py`:

```python
from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

from cursor_usage_menubar.models import Session

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
    raw_team = values.get("cursorAuth/cachedTeam")
    if raw_team:
        try:
            team = json.loads(raw_team)
            team_id = team.get("teamId") or team.get("id")
            if team_id is not None:
                team_id = int(team_id)
            team_name = team.get("name")
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    return Session(
        access_token=token,
        sub=sub,
        email=values.get("cursorAuth/cachedEmail") or None,
        team_id=team_id,
        team_name=team_name,
        plan_hint=values.get("cursorAuth/stripeMembershipType") or None,
    )
```

Do not import or select `cursorAuth/refreshToken`. Do not log tokens.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_auth -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cursor_usage_menubar/models.py cursor_usage_menubar/auth.py tests/test_auth.py
git commit -m "$(cat <<'EOF'
Add read-only Cursor session loading without token storage.

EOF
)"
```

---

### Task 3: Usage models and merge rules (Enterprise first, Auto scaling)

**Files:**
- Modify: `cursor_usage_menubar/models.py` (add `ModelSpend`, `UsageSnapshot`)
- Create: `cursor_usage_menubar/merge.py`
- Test: `tests/test_merge.py`

**Interfaces:**
- Consumes: `is_auto_event`, `is_auto_intent`, `child_label`, `percent_used` from `formatters.py`; `Session` from `models.py`
- Produces:
  - `@dataclass(frozen=True) class ModelSpend` with `label: str`, `model_intent: str`, `total_cents: int`, `input_tokens: int`, `output_tokens: int`, `request_count: int`, `is_auto: bool`, `children: tuple[ModelSpend, ...]`
  - `@dataclass(frozen=True) class UsageSnapshot` with `email`, `team_name`, `plan_name`, `spent_cents`, `limit_cents`, `remaining_cents`, `percent`, `cycle_start`, `cycle_end`, `models`, `status`, `top_model`
  - `UsageSnapshot.empty(status: str) -> UsageSnapshot`
  - `scale_auto_children(auto_total: int, children: list[ModelSpend]) -> tuple[ModelSpend, ...]`
  - `merge_snapshot(session, usage_summary, period_usage, aggregated, filtered, plan_info) -> UsageSnapshot`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_merge.py`:

```python
from __future__ import annotations

import unittest

from cursor_usage_menubar.merge import merge_snapshot, scale_auto_children
from cursor_usage_menubar.models import ModelSpend, Session


def _session() -> Session:
    return Session(
        access_token="t",
        sub="u",
        email="ada@example.com",
        team_id=42,
        team_name="Acme",
        plan_hint="enterprise",
    )


class MergeTest(unittest.TestCase):
    def test_usage_summary_overall_wins_when_limit_positive(self):
        snap = merge_snapshot(
            session=_session(),
            usage_summary={
                "individualUsage": {
                    "overall": {"used": 23734, "limit": 50000, "remaining": 26266}
                },
                "billingCycleStart": "2026-08-01",
                "billingCycleEnd": "2026-08-31",
            },
            period_usage={"planUsage": {"used": 1, "limit": 2}},
            aggregated={
                "totalCostCents": 999,
                "aggregations": [
                    {
                        "modelIntent": "auto-smart",
                        "totalCents": 10000,
                        "inputTokens": 10,
                        "outputTokens": 5,
                    }
                ],
            },
            filtered={"usageEvents": []},
            plan_info={"planName": "Enterprise"},
        )
        self.assertEqual(snap.spent_cents, 23734)
        self.assertEqual(snap.limit_cents, 50000)
        self.assertEqual(snap.remaining_cents, 26266)
        self.assertEqual(snap.percent, 47)
        self.assertEqual(snap.plan_name, "Enterprise")
        self.assertEqual(snap.email, "ada@example.com")
        self.assertEqual(snap.team_name, "Acme")
        self.assertEqual(snap.cycle_start, "2026-08-01")
        self.assertIsNotNone(snap.top_model)
        self.assertEqual(snap.top_model.label, "Auto")

    def test_falls_back_to_period_usage_without_summary_limit(self):
        snap = merge_snapshot(
            session=_session(),
            usage_summary={},
            period_usage={
                "planUsage": {"used": 1200, "limit": 4000, "remaining": 2800},
                "startDate": "2026-08-01",
                "endDate": "2026-08-31",
            },
            aggregated=None,
            filtered=None,
            plan_info=None,
        )
        self.assertEqual(snap.spent_cents, 1200)
        self.assertEqual(snap.limit_cents, 4000)
        self.assertEqual(snap.percent, 30)
        self.assertEqual(snap.plan_name, "enterprise")

    def test_auto_children_scale_to_auto_total(self):
        children = [
            ModelSpend(
                label="Grok 4.5",
                model_intent="grok",
                total_cents=80,
                input_tokens=1,
                output_tokens=1,
                request_count=2,
                is_auto=False,
                children=(),
            ),
            ModelSpend(
                label="Opus 5",
                model_intent="opus",
                total_cents=20,
                input_tokens=1,
                output_tokens=1,
                request_count=1,
                is_auto=False,
                children=(),
            ),
        ]
        scaled = scale_auto_children(1000, children)
        self.assertEqual(sum(c.total_cents for c in scaled), 1000)
        self.assertEqual(scaled[0].total_cents, 800)
        self.assertEqual(scaled[1].total_cents, 200)

    def test_filtered_auto_events_become_children(self):
        snap = merge_snapshot(
            session=_session(),
            usage_summary={
                "individualUsage": {"overall": {"used": 1000, "limit": 2000, "remaining": 1000}}
            },
            period_usage=None,
            aggregated={
                "totalCostCents": 1000,
                "aggregations": [
                    {"modelIntent": "auto-smart", "totalCents": 1000, "inputTokens": 8, "outputTokens": 2}
                ],
            },
            filtered={
                "usageEvents": [
                    {
                        "model": "Cursor Grok 4.5 (Auto Balanced)",
                        "chargedCents": 75,
                        "tokenUsage": {"inputTokens": 4, "outputTokens": 1},
                    },
                    {
                        "model": "Cursor Grok 4.5 (Auto Balanced)",
                        "chargedCents": 25,
                        "tokenUsage": {"inputTokens": 4, "outputTokens": 1},
                    },
                    {
                        "model": "GPT-5.6 Sol",
                        "chargedCents": 9999,
                        "tokenUsage": {},
                    },
                ]
            },
            plan_info=None,
        )
        auto = snap.models[0]
        self.assertTrue(auto.is_auto)
        self.assertEqual(len(auto.children), 1)
        self.assertEqual(auto.children[0].label, "Grok 4.5")
        self.assertEqual(auto.children[0].total_cents, 1000)
        self.assertEqual(auto.children[0].request_count, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_merge -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'cursor_usage_menubar.merge'`

- [ ] **Step 3: Write minimal implementation**

Append to `cursor_usage_menubar/models.py` (keep `Session` as already defined):

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Session:
    access_token: str
    sub: str
    email: str | None = None
    team_id: int | None = None
    team_name: str | None = None
    plan_hint: str | None = None


@dataclass(frozen=True)
class ModelSpend:
    label: str
    model_intent: str
    total_cents: int
    input_tokens: int
    output_tokens: int
    request_count: int
    is_auto: bool
    children: tuple["ModelSpend", ...] = ()


@dataclass(frozen=True)
class UsageSnapshot:
    email: str | None
    team_name: str | None
    plan_name: str
    spent_cents: int | None
    limit_cents: int | None
    remaining_cents: int | None
    percent: int | None
    cycle_start: str | None
    cycle_end: str | None
    models: tuple[ModelSpend, ...]
    status: str | None
    top_model: ModelSpend | None

    @staticmethod
    def empty(status: str) -> "UsageSnapshot":
        return UsageSnapshot(
            email=None,
            team_name=None,
            plan_name="Cursor",
            spent_cents=None,
            limit_cents=None,
            remaining_cents=None,
            percent=None,
            cycle_start=None,
            cycle_end=None,
            models=(),
            status=status,
            top_model=None,
        )
```

Create `cursor_usage_menubar/merge.py`:

```python
from __future__ import annotations

from collections import defaultdict

from cursor_usage_menubar.formatters import (
    child_label,
    is_auto_event,
    is_auto_intent,
    percent_used,
)
from cursor_usage_menubar.models import ModelSpend, Session, UsageSnapshot


def scale_auto_children(
    auto_total: int, children: list[ModelSpend]
) -> tuple[ModelSpend, ...]:
    if not children:
        return ()
    child_sum = sum(c.total_cents for c in children)
    if child_sum <= 0 or auto_total <= 0:
        return tuple(children)
    scaled: list[ModelSpend] = []
    allocated = 0
    for i, child in enumerate(children):
        if i == len(children) - 1:
            cents = auto_total - allocated
        else:
            cents = int(round(auto_total * (child.total_cents / child_sum)))
            allocated += cents
        scaled.append(
            ModelSpend(
                label=child.label,
                model_intent=child.model_intent,
                total_cents=cents,
                input_tokens=child.input_tokens,
                output_tokens=child.output_tokens,
                request_count=child.request_count,
                is_auto=False,
                children=(),
            )
        )
    return tuple(scaled)


def _nested(d: object, *keys: str) -> object:
    cur = d
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _as_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _as_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _auto_label(intent: str) -> str:
    return "Auto"


def _human_label(intent: str) -> str:
    if is_auto_intent(intent):
        return "Auto"
    cleaned = (intent or "").replace("-", " ").replace("_", " ").strip()
    return cleaned.title() if cleaned else "Unknown"


def _tokens(block: object) -> tuple[int, int]:
    if not isinstance(block, dict):
        return 0, 0
    inp = _as_int(block.get("inputTokens") or block.get("input_tokens")) or 0
    out = _as_int(block.get("outputTokens") or block.get("output_tokens")) or 0
    return inp, out


def merge_snapshot(
    session: Session | None,
    usage_summary: dict | None,
    period_usage: dict | None,
    aggregated: dict | None,
    filtered: dict | None,
    plan_info: dict | None,
) -> UsageSnapshot:
    usage_summary = usage_summary or {}
    period_usage = period_usage or {}
    aggregated = aggregated or {}
    filtered = filtered or {}
    plan_info = plan_info or {}

    overall = _nested(usage_summary, "individualUsage", "overall") or {}
    plan_usage = period_usage.get("planUsage") or period_usage.get("usage") or {}
    if not isinstance(overall, dict):
        overall = {}
    if not isinstance(plan_usage, dict):
        plan_usage = {}

    spent = _as_int(overall.get("used"))
    limit = _as_int(overall.get("limit"))
    remaining = _as_int(overall.get("remaining"))
    if limit is None or limit <= 0:
        spent = _as_int(plan_usage.get("used")) if spent is None else spent
        limit = _as_int(plan_usage.get("limit"))
        remaining = _as_int(plan_usage.get("remaining"))
    if spent is None:
        spent = _as_int(aggregated.get("totalCostCents"))
        remaining = None if limit is None else (limit - spent if spent is not None else None)

    pct = percent_used(spent, limit) if spent is not None and limit is not None else None
    if remaining is None and spent is not None and limit is not None:
        remaining = limit - spent

    plan_name = (
        _as_str(plan_info.get("planName") or plan_info.get("name"))
        or (session.plan_hint if session else None)
        or "Cursor"
    )
    cycle_start = _as_str(
        usage_summary.get("billingCycleStart")
        or usage_summary.get("startDate")
        or period_usage.get("startDate")
        or period_usage.get("periodStart")
    )
    cycle_end = _as_str(
        usage_summary.get("billingCycleEnd")
        or usage_summary.get("endDate")
        or period_usage.get("endDate")
        or period_usage.get("periodEnd")
    )

    children_by_label: dict[str, dict[str, int]] = defaultdict(
        lambda: {"cents": 0, "in": 0, "out": 0, "n": 0}
    )
    for event in filtered.get("usageEvents") or filtered.get("events") or []:
        if not isinstance(event, dict):
            continue
        model_name = str(event.get("model") or "")
        if not is_auto_event(model_name):
            continue
        label = child_label(model_name)
        bucket = children_by_label[label]
        bucket["cents"] += _as_int(event.get("chargedCents")) or 0
        inp, out = _tokens(event.get("tokenUsage") or event)
        bucket["in"] += inp
        bucket["out"] += out
        bucket["n"] += 1

    raw_children = [
        ModelSpend(
            label=label,
            model_intent=label.lower(),
            total_cents=vals["cents"],
            input_tokens=vals["in"],
            output_tokens=vals["out"],
            request_count=vals["n"],
            is_auto=False,
            children=(),
        )
        for label, vals in children_by_label.items()
    ]

    models: list[ModelSpend] = []
    for row in aggregated.get("aggregations") or []:
        if not isinstance(row, dict):
            continue
        intent = str(row.get("modelIntent") or row.get("model") or "")
        cents = _as_int(row.get("totalCents")) or 0
        inp, out = _tokens(row)
        auto = is_auto_intent(intent)
        kids = scale_auto_children(cents, raw_children) if auto else ()
        models.append(
            ModelSpend(
                label=_auto_label(intent) if auto else _human_label(intent),
                model_intent=intent,
                total_cents=cents,
                input_tokens=inp,
                output_tokens=out,
                request_count=sum(k.request_count for k in kids) if kids else 0,
                is_auto=auto,
                children=kids,
            )
        )
    models.sort(key=lambda m: m.total_cents, reverse=True)
    top = models[0] if models else None

    return UsageSnapshot(
        email=session.email if session else None,
        team_name=session.team_name if session else None,
        plan_name=plan_name,
        spent_cents=spent,
        limit_cents=limit if limit and limit > 0 else None,
        remaining_cents=remaining,
        percent=pct,
        cycle_start=cycle_start,
        cycle_end=cycle_end,
        models=tuple(models),
        status=None,
        top_model=top,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_merge tests.test_formatters tests.test_auth -v`

Expected: PASS. If `percent_used(23734, 50000)` is 47 not 48, keep 47 (integer truncation). Spec example `48%` is illustrative.

- [ ] **Step 5: Commit**

```bash
git add cursor_usage_menubar/models.py cursor_usage_menubar/merge.py tests/test_merge.py
git commit -m "$(cat <<'EOF'
Add usage merge with enterprise caps and scaled Auto children.

EOF
)"
```

---

### Task 4: HTTPS client with certifi (no token cache)

**Files:**
- Create: `cursor_usage_menubar/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: `read_session`, `session_cookie`, `merge_snapshot`, `UsageSnapshot`, `Session`
- Produces:
  - `USAGE_SUMMARY_URL = "https://cursor.com/api/usage-summary"`
  - `API2 = "https://api2.cursor.sh/aiserver.v1.DashboardService"`
  - `json_request(method: str, url: str, *, token: str | None = None, cookie: str | None = None, body: dict | None = None) -> dict | None`
  - `fetch_usage() -> UsageSnapshot` — reads a fresh session, calls APIs, returns snapshot, does not store the session/token on the module
  - Must not call `/oauth/token`
  - Must use `ssl.create_default_context(cafile=certifi.where())`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_client.py`:

```python
from __future__ import annotations

import inspect
import io
import json
import unittest
from unittest.mock import patch

from cursor_usage_menubar.client import fetch_usage, json_request
from cursor_usage_menubar.models import Session


class _Resp:
    def __init__(self, payload: dict, status: int = 200):
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ClientTest(unittest.TestCase):
    def test_json_request_sets_connect_and_certifi(self):
        captured = {}

        def fake_urlopen(req, context=None, timeout=None):
            captured["url"] = req.full_url
            captured["headers"] = {k.lower(): v for k, v in req.header_items()}
            captured["context"] = context
            return _Resp({"ok": True})

        with patch("urllib.request.urlopen", fake_urlopen):
            data = json_request(
                "POST",
                "https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage",
                token="secret-token",
                body={},
            )
        self.assertEqual(data, {"ok": True})
        self.assertEqual(captured["headers"]["authorization"], "Bearer secret-token")
        self.assertEqual(captured["headers"]["connect-protocol-version"], "1")
        self.assertIsNotNone(captured["context"])

    def test_fetch_usage_merges_mocked_apis_and_drops_session(self):
        session = Session(
            access_token="tok",
            sub="user",
            email="ada@example.com",
            team_id=7,
            team_name="Acme",
            plan_hint="enterprise",
        )
        calls = []

        def fake_json_request(method, url, *, token=None, cookie=None, body=None):
            calls.append(url)
            if url.endswith("usage-summary"):
                return {
                    "individualUsage": {
                        "overall": {"used": 500, "limit": 1000, "remaining": 500}
                    }
                }
            if url.endswith("GetAggregatedUsageEvents"):
                self.assertEqual(body, {"teamId": 7})
                return {
                    "aggregations": [
                        {"modelIntent": "auto-smart", "totalCents": 500, "inputTokens": 1, "outputTokens": 1}
                    ],
                    "totalCostCents": 500,
                }
            if url.endswith("GetFilteredUsageEvents"):
                return {"usageEvents": []}
            if url.endswith("GetPlanInfo"):
                return {"planName": "Enterprise"}
            if url.endswith("GetCurrentPeriodUsage"):
                return {}
            return {}

        with (
            patch("cursor_usage_menubar.client.read_session", return_value=session),
            patch("cursor_usage_menubar.client.json_request", fake_json_request),
        ):
            snap = fetch_usage()
        self.assertEqual(snap.spent_cents, 500)
        self.assertEqual(snap.percent, 50)
        self.assertEqual(snap.plan_name, "Enterprise")
        self.assertTrue(any("usage-summary" in u for u in calls))
        self.assertFalse(hasattr(fetch_usage, "session"))
        import cursor_usage_menubar.client as client_mod

        self.assertFalse(hasattr(client_mod, "_SESSION"))
        self.assertFalse(hasattr(client_mod, "access_token"))

    def test_no_session_returns_status(self):
        with patch("cursor_usage_menubar.client.read_session", return_value=None):
            snap = fetch_usage()
        self.assertEqual(snap.status, "Open Cursor to refresh your session")
        self.assertIsNone(snap.spent_cents)

    def test_source_never_refreshes_oauth(self):
        import cursor_usage_menubar.client as client_mod

        source = inspect.getsource(client_mod)
        self.assertNotIn("/oauth/token", source)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_client -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'cursor_usage_menubar.client'`

- [ ] **Step 3: Write minimal implementation**

`cursor_usage_menubar/client.py`:

```python
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request

import certifi

from cursor_usage_menubar.auth import read_session, session_cookie
from cursor_usage_menubar.merge import merge_snapshot
from cursor_usage_menubar.models import UsageSnapshot

USAGE_SUMMARY_URL = "https://cursor.com/api/usage-summary"
API2 = "https://api2.cursor.sh/aiserver.v1.DashboardService"
_TIMEOUT = 20


def json_request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    cookie: str | None = None,
    body: dict | None = None,
) -> dict | None:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Connect-Protocol-Version", "1")
    if cookie:
        req.add_header("Cookie", cookie)
    ctx = ssl.create_default_context(cafile=certifi.where())
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=_TIMEOUT) as resp:
            raw = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def fetch_usage() -> UsageSnapshot:
    session = read_session()
    if session is None:
        return UsageSnapshot.empty("Open Cursor to refresh your session")
    cookie = session_cookie(session.sub, session.access_token)
    token = session.access_token
    team_body: dict = {}
    if session.team_id is not None:
        team_body["teamId"] = session.team_id
    usage_summary = json_request(
        "GET", USAGE_SUMMARY_URL, cookie=cookie
    )
    period = json_request(
        "POST", f"{API2}/GetCurrentPeriodUsage", token=token, body={}
    )
    aggregated = json_request(
        "POST", f"{API2}/GetAggregatedUsageEvents", token=token, body=team_body
    )
    filtered_body = {"page": 1, "pageSize": 1000, **team_body}
    filtered = json_request(
        "POST", f"{API2}/GetFilteredUsageEvents", token=token, body=filtered_body
    )
    plan_info = json_request(
        "POST", f"{API2}/GetPlanInfo", token=token, body={}
    )
    if usage_summary is None and period is None and aggregated is None:
        return UsageSnapshot.empty("Open Cursor to refresh your session")
    return merge_snapshot(
        session=session,
        usage_summary=usage_summary,
        period_usage=period,
        aggregated=aggregated,
        filtered=filtered,
        plan_info=plan_info,
    )
```

`fetch_usage` must not assign `session` or `token` to a module global. Locals fall out of scope when the function returns.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_client tests.test_merge -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cursor_usage_menubar/client.py tests/test_client.py
git commit -m "$(cat <<'EOF'
Add unofficial Cursor usage client using certifi and no token cache.

EOF
)"
```

---

### Task 5: rumps menu bar (INFO + ACTIONS)

**Files:**
- Create: `cursor_usage_menubar/app.py`
- Create: `run.py`
- Modify: `tests/test_formatters.py` only if extra menu-row helpers are added; otherwise add `tests/test_app_rows.py`

**Interfaces:**
- Consumes: `fetch_usage() -> UsageSnapshot`, `menu_title`, `dollars`, `show_breakdown(snapshot)` (stubbed until Task 6)
- Produces:
  - `info_rows(snapshot: UsageSnapshot) -> list[str]`
  - `class CursorUsageApp(rumps.App)`
  - Menu actions: View Model Breakdown…, Refresh Now, Open Cursor Dashboard, Quit
  - Timer 300 seconds
  - App stores `UsageSnapshot` only — never `Session` or tokens

- [ ] **Step 1: Write the failing tests**

Create `tests/test_app_rows.py`:

```python
import unittest

from cursor_usage_menubar.app import info_rows
from cursor_usage_menubar.models import ModelSpend, UsageSnapshot


class InfoRowsTest(unittest.TestCase):
    def test_rows_include_account_plan_spend_not_models_tree(self):
        snap = UsageSnapshot(
            email="ada@example.com",
            team_name="Acme",
            plan_name="Enterprise",
            spent_cents=23734,
            limit_cents=50000,
            remaining_cents=26266,
            percent=47,
            cycle_start="2026-08-01",
            cycle_end="2026-08-31",
            models=(
                ModelSpend("Auto", "auto-smart", 100, 1, 1, 3, True, ()),
            ),
            status=None,
            top_model=ModelSpend("Auto", "auto-smart", 100, 1, 1, 3, True, ()),
        )
        rows = info_rows(snap)
        joined = "\n".join(rows)
        self.assertIn("ada@example.com", joined)
        self.assertIn("Acme", joined)
        self.assertIn("Enterprise", joined)
        self.assertIn("$237.34", joined)
        self.assertIn("47%", joined)
        self.assertTrue(any(r.startswith("Top model:") for r in rows))
        self.assertFalse(any("Grok" in r for r in rows))

    def test_status_row_when_signed_out(self):
        snap = UsageSnapshot.empty("Open Cursor to refresh your session")
        rows = info_rows(snap)
        self.assertEqual(rows[0], "Open Cursor to refresh your session")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_app_rows -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'cursor_usage_menubar.app'`

- [ ] **Step 3: Write minimal implementation**

`cursor_usage_menubar/app.py`:

```python
from __future__ import annotations

import webbrowser

import rumps
from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

from cursor_usage_menubar.breakdown import show_breakdown
from cursor_usage_menubar.client import fetch_usage
from cursor_usage_menubar.formatters import dollars, menu_title
from cursor_usage_menubar.models import UsageSnapshot

DASHBOARD_URL = "https://cursor.com/dashboard/usage"


def info_rows(snapshot: UsageSnapshot) -> list[str]:
    if snapshot.status and snapshot.spent_cents is None:
        return [snapshot.status]
    account = snapshot.email or "Unknown"
    if snapshot.team_name:
        account = f"{account} · {snapshot.team_name}"
    spent = dollars(snapshot.spent_cents) if snapshot.spent_cents is not None else "—"
    if snapshot.limit_cents:
        allowance = (
            f"{dollars(snapshot.spent_cents or 0)} / {dollars(snapshot.limit_cents)}"
            + (f" ({snapshot.percent}%)" if snapshot.percent is not None else "")
        )
        remaining = (
            dollars(snapshot.remaining_cents)
            if snapshot.remaining_cents is not None
            else "—"
        )
    else:
        allowance = "— (no cap reported)"
        remaining = "—"
    cycle = "—"
    if snapshot.cycle_start or snapshot.cycle_end:
        cycle = f"{snapshot.cycle_start or '?'} → {snapshot.cycle_end or '?'}"
    top = "—"
    if snapshot.top_model is not None and snapshot.spent_cents:
        share = int(round(100 * snapshot.top_model.total_cents / snapshot.spent_cents))
        top = f"{snapshot.top_model.label} · {dollars(snapshot.top_model.total_cents)} · {share}%"
    elif snapshot.top_model is not None:
        top = f"{snapshot.top_model.label} · {dollars(snapshot.top_model.total_cents)}"
    return [
        f"Account: {account}",
        f"Plan: {snapshot.plan_name}",
        f"Spent: {spent}",
        f"Allowance: {allowance}",
        f"Remaining: {remaining}",
        f"Cycle: {cycle}",
        f"Top model: {top}",
    ]


class CursorUsageApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("Cursor · —", quit_button=None)
        self._snapshot: UsageSnapshot | None = None
        self._info_items: list[rumps.MenuItem] = []
        self.menu = [
            rumps.separator,
            rumps.MenuItem("View Model Breakdown…", callback=self.view_breakdown),
            rumps.MenuItem("Refresh Now", callback=self.refresh_now),
            rumps.MenuItem("Open Cursor Dashboard", callback=self.open_dashboard),
            rumps.separator,
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]

    def _rebuild_info(self, snapshot: UsageSnapshot) -> None:
        for item in self._info_items:
            try:
                del self.menu[item.title]
            except Exception:
                pass
        self._info_items = []
        for row in reversed(info_rows(snapshot)):
            item = rumps.MenuItem(row)
            item.set_callback(None)
            self.menu.insert(0, item)
            self._info_items.append(item)

    def _apply(self, snapshot: UsageSnapshot) -> None:
        self._snapshot = snapshot
        self.title = menu_title(snapshot.spent_cents, snapshot.percent)
        self._rebuild_info(snapshot)

    @rumps.timer(300)
    def poll(self, _sender=None) -> None:
        self._apply(fetch_usage())

    def refresh_now(self, _sender=None) -> None:
        self._apply(fetch_usage())

    def view_breakdown(self, _sender=None) -> None:
        snap = self._snapshot or fetch_usage()
        self._snapshot = snap
        show_breakdown(snap)

    def open_dashboard(self, _sender=None) -> None:
        webbrowser.open(DASHBOARD_URL)

    def quit_app(self, _sender=None) -> None:
        rumps.quit_application()

    def run(self, **kwargs):
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
        self.refresh_now()
        super().run(**kwargs)
```

Until Task 6, `cursor_usage_menubar/breakdown.py` must exist so app imports work:

```python
from cursor_usage_menubar.models import UsageSnapshot


def show_breakdown(snapshot: UsageSnapshot) -> None:
    return
```

`run.py`:

```python
from cursor_usage_menubar.app import CursorUsageApp

if __name__ == "__main__":
    CursorUsageApp().run()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_app_rows tests.test_formatters -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cursor_usage_menubar/app.py cursor_usage_menubar/breakdown.py run.py tests/test_app_rows.py
git commit -m "$(cat <<'EOF'
Add rumps menu bar with info rows and refresh actions.

EOF
)"
```

---

### Task 6: Native AppKit breakdown window (Auto accordion)

**Files:**
- Modify: `cursor_usage_menubar/breakdown.py` (replace stub)
- Test: `tests/test_breakdown_layout.py`

**Interfaces:**
- Consumes: `UsageSnapshot`, `ModelSpend`, `dollars`, `percent_used`
- Produces:
  - `show_breakdown(snapshot: UsageSnapshot) -> None` — single window, no duplicates
  - `layout_height(snapshot: UsageSnapshot, auto_expanded: bool) -> int` (pure; used by tests)
  - Window width 580, flipped document view, system colors, unofficial-API footer
  - Auto row uses `NSDisclosureBezelStyle` / `NSBezelStyleDisclosure`
  - No WebKit imports

- [ ] **Step 1: Write the failing tests**

Create `tests/test_breakdown_layout.py`:

```python
import inspect
import unittest

from cursor_usage_menubar.breakdown import layout_height, show_breakdown
from cursor_usage_menubar.models import ModelSpend, UsageSnapshot


def _snap() -> UsageSnapshot:
    child = ModelSpend("Grok 4.5", "grok", 800, 10, 4, 3, False, ())
    auto = ModelSpend("Auto", "auto-smart", 1000, 12, 5, 3, True, (child,))
    return UsageSnapshot(
        email="a@b.c",
        team_name="Acme",
        plan_name="Enterprise",
        spent_cents=1000,
        limit_cents=2000,
        remaining_cents=1000,
        percent=50,
        cycle_start="2026-08-01",
        cycle_end="2026-08-31",
        models=(auto,),
        status=None,
        top_model=auto,
    )


class BreakdownLayoutTest(unittest.TestCase):
    def test_expanded_auto_is_taller(self):
        snap = _snap()
        self.assertGreater(layout_height(snap, True), layout_height(snap, False))

    def test_no_webkit(self):
        import cursor_usage_menubar.breakdown as mod

        source = inspect.getsource(mod)
        self.assertNotIn("WebKit", source)
        self.assertNotIn("WKWebView", source)
        self.assertIn("NSDisclosureBezelStyle", source)

    def test_show_breakdown_is_callable(self):
        self.assertTrue(callable(show_breakdown))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_breakdown_layout -v`

Expected: FAIL (`layout_height` not defined / stub has no `NSDisclosureBezelStyle`)

- [ ] **Step 3: Write the native window**

Replace `cursor_usage_menubar/breakdown.py` with:

```python
from __future__ import annotations

import hashlib

from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSButton,
    NSColor,
    NSFont,
    NSMakeRect,
    NSScrollView,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject
from objc import super as objc_super

from cursor_usage_menubar.formatters import dollars
from cursor_usage_menubar.models import ModelSpend, UsageSnapshot

WINDOW_WIDTH = 580
HEADER_H = 64
SUMMARY_H = 118
ROW_H = 72
CHILD_H = 58
FOOTER_H = 48
PAD = 20

try:
    DISCLOSURE = __import__("AppKit").NSDisclosureBezelStyle
except AttributeError:
    DISCLOSURE = 5

_PALETTE = (
    NSColor.systemBlueColor(),
    NSColor.systemPurpleColor(),
    NSColor.systemPinkColor(),
    NSColor.systemOrangeColor(),
    NSColor.systemTealColor(),
    NSColor.systemIndigoColor(),
    NSColor.systemGreenColor(),
    NSColor.systemBrownColor(),
)


def layout_height(snapshot: UsageSnapshot, auto_expanded: bool) -> int:
    height = PAD + HEADER_H + SUMMARY_H + 36
    for model in snapshot.models:
        height += ROW_H
        if model.is_auto and auto_expanded:
            height += CHILD_H * max(1, len(model.children))
        elif model.is_auto:
            height += 22
    return height + FOOTER_H + PAD


def _color_for(name: str):
    digest = hashlib.md5(name.encode()).hexdigest()
    return _PALETTE[int(digest, 16) % len(_PALETTE)]


class FlippedView(NSView):
    def isFlipped(self):
        return True


class BarView(NSView):
    def initWithFrame_fraction_color_(self, frame, fraction, color):
        self = objc_super(BarView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.fraction = max(0.0, min(1.0, float(fraction)))
        self.barColor = color
        return self

    def drawRect_(self, _rect):
        NSColor.separatorColor().colorWithAlphaComponent_(0.35).set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            self.bounds(), 6, 6
        ).fill()
        width = self.bounds().size.width * self.fraction
        if width <= 0:
            return
        self.barColor.set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(0, 0, width, self.bounds().size.height), 6, 6
        ).fill()


class BreakdownController(NSObject):
    _instance = None

    def init(self):
        self = objc_super(BreakdownController, self).init()
        self.window = None
        self.auto_expanded = False
        self.snapshot = None
        return self

    @classmethod
    def shared(cls):
        if cls._instance is None:
            cls._instance = cls.alloc().init()
        return cls._instance

    def show_(self, snapshot: UsageSnapshot):
        self.snapshot = snapshot
        if self.window is None:
            self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(0, 0, WINDOW_WIDTH, 640),
                NSWindowStyleMaskTitled
                | NSWindowStyleMaskClosable
                | NSWindowStyleMaskMiniaturizable,
                NSBackingStoreBuffered,
                False,
            )
            self.window.setTitle_("Cursor Usage")
            self.window.center()
        self.render()
        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def toggleAuto_(self, _sender):
        self.auto_expanded = not self.auto_expanded
        self.render()

    def render(self):
        snap = self.snapshot
        height = max(640, layout_height(snap, self.auto_expanded))
        scroll = NSScrollView.alloc().initWithFrame_(self.window.contentView().bounds())
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(0)
        scroll.setDrawsBackground_(False)
        scroll.setAutoresizingMask_(18)
        doc = FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, WINDOW_WIDTH, height))
        doc.setWantsLayer_(True)
        NSColor.controlBackgroundColor().set()
        y = PAD
        y = self._header(doc, snap, y)
        y = self._summary(doc, snap, y)
        y = self._models(doc, snap, y)
        self._footer(doc, y)
        scroll.setDocumentView_(doc)
        self.window.setContentView_(scroll)

    def _label(self, parent, text, x, y, w, h, size=13, bold=False, color=None, secondary=False):
        field = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
        field.setBezeled_(False)
        field.setDrawsBackground_(False)
        field.setEditable_(False)
        field.setSelectable_(False)
        field.setStringValue_(text)
        font = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
        field.setFont_(font)
        if secondary:
            field.setTextColor_(NSColor.secondaryLabelColor())
        elif color is not None:
            field.setTextColor_(color)
        else:
            field.setTextColor_(NSColor.labelColor())
        parent.addSubview_(field)
        return field

    def _header(self, doc, snap, y):
        self._label(doc, "Cursor Usage", PAD, y, 400, 28, size=22, bold=True)
        cycle = "—"
        if snap.cycle_start or snap.cycle_end:
            cycle = f"{snap.cycle_start or '?'} → {snap.cycle_end or '?'}"
        self._label(doc, cycle, PAD, y + 32, 400, 18, size=12, secondary=True)
        return y + HEADER_H

    def _summary(self, doc, snap, y):
        card = FlippedView.alloc().initWithFrame_(
            NSMakeRect(PAD, y, WINDOW_WIDTH - PAD * 2, SUMMARY_H - 16)
        )
        card.setWantsLayer_(True)
        card.layer().setCornerRadius_(12)
        card.layer().setBackgroundColor_(
            NSColor.separatorColor().colorWithAlphaComponent_(0.18).CGColor()
        )
        spent = dollars(snap.spent_cents) if snap.spent_cents is not None else "—"
        pct_text = f"{snap.percent}%" if snap.percent is not None else "—"
        self._label(card, spent, 16, 12, 300, 36, size=28, bold=True)
        self._label(card, f"{pct_text} of limit", 16, 50, 300, 18, size=12, secondary=True)
        fraction = 0.0
        if snap.percent is not None:
            fraction = min(1.0, snap.percent / 100.0)
        if snap.percent is not None and snap.percent >= 90:
            color = NSColor.systemRedColor()
        elif snap.percent is not None and snap.percent >= 75:
            color = NSColor.systemOrangeColor()
        else:
            color = NSColor.systemGreenColor()
        bar = BarView.alloc().initWithFrame_fraction_color_(
            NSMakeRect(16, 78, WINDOW_WIDTH - PAD * 2 - 48, 14), fraction, color
        )
        card.addSubview_(bar)
        doc.addSubview_(card)
        return y + SUMMARY_H

    def _models(self, doc, snap, y):
        self._label(doc, "BY MODEL", PAD, y, 200, 18, size=11, bold=True, secondary=True)
        y += 28
        total = snap.spent_cents or sum(m.total_cents for m in snap.models) or 1
        for model in snap.models:
            y = self._model_row(doc, model, total, y, nested=False)
            if model.is_auto:
                if self.auto_expanded:
                    for child in model.children:
                        y = self._model_row(doc, child, total, y, nested=True)
                    if not model.children:
                        self._label(
                            doc,
                            "No Auto-routed models in this period",
                            PAD + 28,
                            y,
                            400,
                            18,
                            size=11,
                            secondary=True,
                        )
                        y += 22
                else:
                    n = len(model.children)
                    self._label(
                        doc,
                        f"{n} models routed by Auto",
                        PAD + 28,
                        y,
                        400,
                        18,
                        size=11,
                        secondary=True,
                    )
                    y += 22
        return y

    def _model_row(self, doc, model: ModelSpend, total: int, y, nested: bool):
        indent = 36 if nested else 0
        x = PAD + indent
        width = WINDOW_WIDTH - PAD * 2 - indent
        if model.is_auto and not nested:
            btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, y + 4, 16, 16))
            btn.setBezelStyle_(DISCLOSURE)
            btn.setButtonType_(1)
            btn.setTitle_("")
            btn.setState_(1 if self.auto_expanded else 0)
            btn.setTarget_(self)
            btn.setAction_("toggleAuto:")
            doc.addSubview_(btn)
            x += 22
            width -= 22
        frac = model.total_cents / total if total else 0
        pct = int(round(100 * frac))
        self._label(doc, model.label, x, y, 280, 18, size=13, bold=True)
        self._label(
            doc,
            f"{dollars(model.total_cents)} · {pct}%",
            x + width - 160,
            y,
            160,
            18,
            size=12,
            secondary=True,
        )
        color = _color_for(model.label)
        bar = BarView.alloc().initWithFrame_fraction_color_(
            NSMakeRect(x, y + 24, width, 14), frac, color
        )
        doc.addSubview_(bar)
        tokens = f"{model.input_tokens:,} in / {model.output_tokens:,} out"
        if nested or model.request_count:
            tokens = f"{model.request_count} requests · {tokens}"
        self._label(doc, tokens, x, y + 42, width, 16, size=11, secondary=True)
        return y + (CHILD_H if nested else ROW_H)

    def _footer(self, doc, y):
        self._label(
            doc,
            "Unofficial Cursor APIs — they can change or break without notice.",
            PAD,
            y + 8,
            WINDOW_WIDTH - PAD * 2,
            32,
            size=11,
            secondary=True,
        )


def show_breakdown(snapshot: UsageSnapshot) -> None:
    BreakdownController.shared().show_(snapshot)
```

Fix NSButton type: use `NSButtonTypeOnOff` if available (`NSButtonTypePushOnPushOff` is 1). Keep `setButtonType_(1)`.

If `card.layer()` is None, call `card.setWantsLayer_(True)` before using it (already set).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_breakdown_layout tests.test_app_rows -v`

Expected: PASS. Importing AppKit requires macOS; this machine is macOS.

- [ ] **Step 5: Commit**

```bash
git add cursor_usage_menubar/breakdown.py tests/test_breakdown_layout.py
git commit -m "$(cat <<'EOF'
Add native AppKit model breakdown with Auto disclosure accordion.

EOF
)"
```

---

### Task 7: install.sh, README, verify helper

**Files:**
- Create: `install.sh`
- Create: `README.md`
- Create: `cursor_usage_menubar/verify.py`

**Interfaces:**
- Consumes: `fetch_usage()`, project paths
- Produces: LaunchAgent `com.cursor-usage.menubar`; `python3 -m cursor_usage_menubar.verify` prints redacted snapshot (email domain only, no tokens)

- [ ] **Step 1: Write the failing test for redaction**

Create `tests/test_verify.py`:

```python
import unittest
from unittest.mock import patch

from cursor_usage_menubar.models import ModelSpend, UsageSnapshot
from cursor_usage_menubar.verify import redact, render


class VerifyTest(unittest.TestCase):
    def test_redact_email_domain_only(self):
        self.assertEqual(redact("ada@example.com"), "a***@example.com")
        self.assertEqual(redact(None), "—")

    def test_render_omits_token_words(self):
        snap = UsageSnapshot(
            email="ada@example.com",
            team_name="Acme",
            plan_name="Enterprise",
            spent_cents=100,
            limit_cents=200,
            remaining_cents=100,
            percent=50,
            cycle_start="2026-08-01",
            cycle_end="2026-08-31",
            models=(ModelSpend("Auto", "auto-smart", 100, 1, 1, 1, True, ()),),
            status=None,
            top_model=None,
        )
        text = render(snap)
        self.assertIn("example.com", text)
        self.assertNotIn("ada@", text)
        lowered = text.lower()
        self.assertNotIn("bearer", lowered)
        self.assertNotIn("access_token", lowered)
        self.assertNotIn("workoscursorsessiontoken", lowered)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_verify -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'cursor_usage_menubar.verify'`

- [ ] **Step 3: Implement verify, install.sh, README**

`cursor_usage_menubar/verify.py`:

```python
from __future__ import annotations

from cursor_usage_menubar.client import fetch_usage
from cursor_usage_menubar.formatters import dollars
from cursor_usage_menubar.models import UsageSnapshot


def redact(email: str | None) -> str:
    if not email or "@" not in email:
        return "—"
    name, domain = email.split("@", 1)
    return f"{name[:1]}***@{domain}"


def render(snapshot: UsageSnapshot) -> str:
    lines = [
        f"account: {redact(snapshot.email)}",
        f"team: {snapshot.team_name or '—'}",
        f"plan: {snapshot.plan_name}",
        f"spent: {dollars(snapshot.spent_cents) if snapshot.spent_cents is not None else '—'}",
        f"limit: {dollars(snapshot.limit_cents) if snapshot.limit_cents is not None else '—'}",
        f"percent: {snapshot.percent if snapshot.percent is not None else '—'}",
        f"cycle: {snapshot.cycle_start or '—'} → {snapshot.cycle_end or '—'}",
        f"status: {snapshot.status or 'ok'}",
        "models:",
    ]
    for model in snapshot.models:
        lines.append(f"  - {model.label}: {dollars(model.total_cents)}")
        for child in model.children:
            lines.append(f"      {child.label}: {dollars(child.total_cents)} ({child.request_count} req)")
    return "\n".join(lines)


def main() -> None:
    print(render(fetch_usage()))


if __name__ == "__main__":
    main()
```

`install.sh` (executable):

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"
LABEL="com.cursor-usage.menubar"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG="$HOME/Library/Logs/cursor-usage-menubar.log"
ERR="$HOME/Library/Logs/cursor-usage-menubar.err.log"

ensure_venv() {
  if [[ ! -x "$PY" ]]; then
    python3 -m venv "$VENV"
  fi
  "$PY" -m pip install -q -r "$ROOT/requirements.txt"
}

cmd="${1:-run}"

case "$cmd" in
  run)
    ensure_venv
    exec "$PY" "$ROOT/run.py"
    ;;
  install)
    ensure_venv
    mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PY}</string>
    <string>${ROOT}/run.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${LOG}</string>
  <key>StandardErrorPath</key>
  <string>${ERR}</string>
</dict>
</plist>
EOF
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST"
    echo "Installed $PLIST"
    ;;
  uninstall)
    if [[ -f "$PLIST" ]]; then
      launchctl unload "$PLIST" 2>/dev/null || true
      rm -f "$PLIST"
    fi
    pkill -f "$ROOT/run.py" 2>/dev/null || true
    echo "Uninstalled $LABEL"
    ;;
  status)
    echo "plist: $PLIST"
    if [[ -f "$PLIST" ]]; then echo "plist_exists: yes"; else echo "plist_exists: no"; fi
    if launchctl list "$LABEL" >/dev/null 2>&1; then echo "loaded: yes"; else echo "loaded: no"; fi
    if pgrep -f "$ROOT/run.py" >/dev/null 2>&1; then echo "running: yes"; else echo "running: no"; fi
    ;;
  *)
    echo "usage: $0 {run|install|uninstall|status}"
    exit 1
    ;;
esac
```

`README.md`:

```markdown
# Cursor Usage (macOS menu bar)

Shows your signed-in Cursor plan spend in the Mac menu bar.

**This uses unofficial Cursor APIs. They can change or break without notice.**

## Requirements

- macOS
- Python 3
- Cursor desktop app signed in on this Mac

## Auth (no tokens stored)

The app reads Cursor's local SQLite state DB **read-only**:

`~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`

It never writes that DB, never saves access/refresh tokens to disk or Keychain, never logs cookies, and never calls Cursor's OAuth refresh endpoint (refreshing here could break your Cursor login). If the session is expired, open Cursor so it can refresh itself.

## Install (local only)

```bash
chmod +x install.sh
./install.sh run       # start once
./install.sh install   # LaunchAgent (RunAtLoad + KeepAlive)
./install.sh status
./install.sh uninstall
```

Menu title looks like `Cursor · $237.34 · 48%`. Click it for account/plan/spend/allowance/remaining/cycle/top model, then:

- View Model Breakdown… (native window, Auto accordion)
- Refresh Now
- Open Cursor Dashboard
- Quit

## Verify

```bash
.venv/bin/python -m cursor_usage_menubar.verify
```

Prints a redacted snapshot (email domain, plan, spend, model names). No tokens.

## License

Private local utility. Do not commit secrets.
```

`chmod +x install.sh`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_verify -v`

Expected: PASS

Then: `bash -n install.sh`

Expected: no output, exit 0

- [ ] **Step 5: Commit**

```bash
git add install.sh README.md cursor_usage_menubar/verify.py tests/test_verify.py
git commit -m "$(cat <<'EOF'
Add local install scripts, README, and redacted live verify helper.

EOF
)"
```

---

### Task 8: Live verification against this Mac's Cursor session

**Files:**
- None new unless parsers need a small robustness fix after seeing real JSON

**Interfaces:**
- Consumes: live `state.vscdb` + unofficial APIs
- Produces: passing unit tests + a redacted live snapshot + a running menu-bar app

- [ ] **Step 1: Run the full unit suite**

Run: `python3 -m unittest discover -s tests -v`

Expected: all PASS

- [ ] **Step 2: Create venv and install deps**

Run:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Expected: rumps, certifi, pyobjc-framework-Cocoa installed

- [ ] **Step 3: Print a redacted live snapshot**

Run: `.venv/bin/python -m cursor_usage_menubar.verify`

Expected: account domain, plan, spent/limit/percent, model list. Auto children present if this account used Auto. **Must not print JWTs, cookies, or Bearer tokens.**

If usage-summary JSON uses different key names than the spec, add those keys to `_nested` / cycle parsing in `merge.py` and re-run tests + verify. Do not log raw responses that contain tokens.

- [ ] **Step 4: Launch the menu bar app and check acceptance**

Run: `./install.sh run` (background is OK)

Acceptance:

1. Menu title shows live spend/% (or `Cursor · —` only if Cursor is signed out — this machine should be signed in).
2. Click **Refresh Now**; numbers update (same or new).
3. **View Model Breakdown…** opens one window with bars; Auto triangle expands/collapses; a second click does not stack a second window.
4. Auto children show resolved names (Grok / Opus / GPT, etc.) when events exist.
5. Enterprise overall cap used if present; otherwise period usage.
6. `git grep -i 'refresh_token\|sk-\|WorkosCursorSessionToken='` in the repo shows only documentation/code builders, not live secrets. Logs in `~/Library/Logs/cursor-usage-menubar*.log` contain no cookies.

- [ ] **Step 5: Commit only if live JSON required parser fixes**

If merge/client changed:

```bash
git add cursor_usage_menubar/merge.py cursor_usage_menubar/client.py tests
git commit -m "$(cat <<'EOF'
Harden usage parsers against the live unofficial API shapes.

EOF
)"
```

If nothing changed, do not create an empty commit.

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|---|---|
| Menu title `Cursor · $<spend> · <% >` | 1, 5 |
| INFO + ACTIONS, no nested model menu | 5 |
| Native AppKit window, Auto disclosure | 6 |
| Read-only `state.vscdb`, cookie from `sub` + token | 2 |
| No OAuth refresh, no token persistence | 2, 4, 5 |
| certifi SSL | 4 |
| usage-summary → period usage → aggregated → filtered → plan info | 3, 4 |
| Enterprise overall cents first; Pro/Ultra fallback | 3 |
| Auto children scaled to aggregated Auto total | 3 |
| Poll 5 minutes | 5 |
| install.sh run/install/uninstall/status | 7 |
| README unofficial API + no secrets | 7 |
| Live verify before done | 8 |
| LaunchAgent `com.cursor-usage.menubar` | 7 |
| Single reusable window | 6 |

No TBD/TODO placeholders. Types are consistent: `Session`, `ModelSpend`, `UsageSnapshot`, `fetch_usage()`, `show_breakdown(snapshot)`, `info_rows(snapshot)`.
