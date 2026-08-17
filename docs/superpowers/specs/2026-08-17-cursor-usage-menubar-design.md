# Cursor Usage Menu Bar — Design

Date: 2026-08-17  
Status: approved in conversation; awaiting user review of this file  
Project: `~/Projects/cursor-usage-menubar`  
Platform: macOS only

A small always-visible macOS menu-bar app that shows the signed-in Cursor user's plan usage. It is a standalone Python + rumps + PyObjC utility, not a Cursor or VS Code extension.

This document is the implementation contract. Unofficial Cursor APIs can change or break without notice.

## Goals

- Menu title like `Cursor · $237.34 · 48%`.
- Dropdown is INFO + ACTIONS only (no nested model lists).
- One native AppKit window shows a colorful model spend breakdown, with Auto as a real disclosure accordion.
- Authenticate from the local Cursor login already on the machine. Never prompt for an API key.
- Never persist tokens anywhere this app controls.
- Local install via LaunchAgent scripts. Do not publish from this repo as part of implementation.
- Verify against the machine's live Cursor session before calling the work done.

## Non-goals

- No Cursor/VS Code extension.
- No WebKit / HTML UI.
- No API-key auth flow.
- No OAuth refresh performed by this app.
- No token storage (files, Keychain, logs, env files, in-memory caches across polls).
- No writing back to Cursor's `state.vscdb`.
- No hierarchical model lists in the rumps menu.
- No shipping / notarizing / App Store / Homebrew publish step in this project.

## Constraints

- macOS only.
- Python 3 + rumps + PyObjC (Cocoa / AppKit).
- Use certifi for SSL (system Python often fails certificate verification).
- Read Cursor's SQLite state DB read-only.
- Document unofficial API risk in the README.
- No secrets in the repository.

## Architecture

Four modules, one job each. `run.py` starts the rumps app.

| Module | Responsibility | Depends on |
|---|---|---|
| `auth.py` | Read-only session from Cursor's local DB | sqlite3, JWT `sub` parse |
| `client.py` | Unofficial API fetch + merge into `UsageSnapshot` | `auth.py`, urllib + certifi |
| `app.py` | rumps menu bar, 5-minute poll, actions | `client.py`, `breakdown.py` |
| `breakdown.py` | Single reusable native AppKit window | AppKit / PyObjC, `UsageSnapshot` |

### Data flow

1. Timer (5 minutes) or **Refresh Now** calls `client.fetch_usage()`.
2. `fetch_usage()` calls `auth.read_session()` (fresh every time), then hits APIs, then returns a `UsageSnapshot`.
3. `app.py` updates the menu title and disabled info rows from that snapshot.
4. **View Model Breakdown…** shows the latest snapshot from the last poll. If no snapshot exists yet, fetch once, then show the window.

Tokens exist only for the duration of one `fetch_usage()` call, then are dropped.

### Error handling

- Missing DB, missing keys, or expired/rejected access token: title `Cursor · —`; menu shows a short status such as `Open Cursor to refresh your session`. App does not crash.
- Partial API failure: merge whatever succeeded; if no spend/limit can be computed, show `—`.
- Never log access tokens, refresh tokens, cookies, or raw JWT payloads.

## Auth (no token retention)

Read-only path:

`~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`

`ItemTable` keys:

- `cursorAuth/accessToken`
- `cursorAuth/cachedEmail`
- `cursorAuth/stripeMembershipType`
- `cursorAuth/cachedTeam` (JSON with `teamId`, `name`)
- `cursorAuth/cachedScopedProfile` (optional, for display/plan hints)

`cursorAuth/refreshToken` may exist in the DB. This app must not read it for refresh, must not copy it, and must not log it.

Cookie for `cursor.com` APIs:

```
WorkosCursorSessionToken=<url-encoded sub>::<access_token>
```

- JWT `sub` comes from the access token payload (base64url decode of the payload segment only; no signature verification required for local display use).
- Encode `::` as `%3A%3A` (URL-encode the `sub::token` value).

**Hard rules:**

- Open the DB read-only (`mode=ro`). Never `UPDATE`/`INSERT`/`DELETE`.
- Do not write tokens to disk, Keychain, environment files, or logs.
- Do not keep tokens in module globals or on the app object across polls.
- Do not call `POST https://api2.cursor.sh/oauth/token`. Refreshing would either store a new token or rotate Cursor's refresh token and break the user's Cursor login.
- If the access token is missing or the APIs return 401/403, tell the user to open Cursor so Cursor can refresh its own session.

## Data sources

Try in this order and merge. All HTTPS calls use certifi's CA bundle.

### 1. GET `https://cursor.com/api/usage-summary`

- Cookie: `WorkosCursorSessionToken=...`
- Best for Enterprise/team dollar caps.
- Use `individualUsage.overall` `{ used, limit, remaining }` (values are cents for enterprise).
- Also take billing-cycle dates if present.

### 2. POST `https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage`

- Headers: `Authorization: Bearer <access_token>`, `Content-Type: application/json`, `Connect-Protocol-Version: 1`
- Body: `{}`
- Best for Pro/Ultra `planUsage` (cents).
- Use when usage-summary has no usable dollar cap, or to fill plan/cycle fields.

### 3. POST `.../GetAggregatedUsageEvents`

- Same auth headers as (2).
- Body: `{ "teamId": <id> }` when `cachedTeam.teamId` is available; otherwise `{}` or omit teamId if the API rejects it.
- Returns `aggregations[{ modelIntent, totalCents, inputTokens, outputTokens }]` and `totalCostCents`.
- This is the source of truth for per-model totals and the Auto (auto-smart) bucket.

### 4. POST `.../GetFilteredUsageEvents`

- Body: `{ "teamId": <id>?, "page": 1, "pageSize": 1000 }`
- Each event has `model` (e.g. `"Cursor Grok 4.5 (Auto Balanced)"`), `chargedCents`, `tokenUsage`.
- Events whose model name contains `(Auto` (or default/auto) resolve what Auto actually routed to.
- Scale those child costs so they sum to the aggregated Auto (`auto-smart` / Auto) `totalCents`. UI totals stay consistent with aggregation.

### 5. Optional: `GetPlanInfo`

- Use for a human plan name when membership type is not enough.

### Merge rules (explicit)

- **Spend / limit / remaining / percent:** prefer usage-summary `individualUsage.overall` when `limit` is present and > 0. Else use GetCurrentPeriodUsage `planUsage` cents. Else fall back to aggregated `totalCostCents` as spend with unknown limit (`—` for % if no limit).
- **Plan name:** GetPlanInfo, else `stripeMembershipType`, else `"Cursor"`.
- **Account:** `cachedEmail` · `cachedTeam.name` when present.
- **Cycle dates:** first available from usage-summary or period usage.
- **Top model:** highest `totalCents` among aggregated models (Auto counts as one model for this row).
- **Auto children:** only models resolved from filtered events attributed to Auto; scale `chargedCents` by `auto_total / sum(child_cents)` when `sum(child_cents) > 0`. If Auto total is 0 or no children, show Auto with no children.
- Cents → dollars: `cents / 100.0`. Display spend as `$237.34` (2 decimal places). Percent is integer (`48%`).

## Menu bar UI (rumps)

Keep the dropdown as INFO + ACTIONS, not nested analytics.

**Title:** `Cursor · $<spend> · <percent>%`  
If spend or percent is unknown: `Cursor · —` (do not invent 0%).

**Info rows (disabled / non-clickable):**

- Account (email · team name)
- Plan
- Spent
- Allowance used/limit (+ %)
- Remaining
- Cycle dates
- Top model (highest spend, with $ and %)

**Actions:**

- View Model Breakdown… → opens/focuses the native window
- Refresh Now
- Open Cursor Dashboard → `https://cursor.com/dashboard/usage`
- Quit

Poll every 5 minutes. Do not put hierarchical model lists in the menu.

## Breakdown window (native AppKit)

- Reusable single window. A second "View Model Breakdown…" brings the existing window forward; it must not stack duplicates.
- Not WebKit.
- Fixed width ~580px, scrollable height, flipped document view (top-down layout).
- System colors: label, secondaryLabel, separator, controlBackground (light/dark).

Layout:

1. Header: "Cursor Usage" + billing cycle dates.
2. Summary card: large spent amount, % of limit, overall progress bar.
   - Bar orange at ≥75%, red at ≥90%, otherwise the default accent/system blue-green.
3. "BY MODEL" section with colorful rounded gradient pill bars (system palette colors, stable per model name).
4. Each model row: label, $, %, bar, token summary (input/output when known).
5. Auto row has a real `NSDisclosureBezelStyle` triangle accordion:
   - Expanded: routed child models with their own colored bars, request counts, tokens.
   - Collapsed: short hint `N models routed by Auto`.
6. Footer note that APIs are unofficial and may break.

## Project layout

```
~/Projects/cursor-usage-menubar/
  requirements.txt          # rumps, certifi, pyobjc-framework-Cocoa
  run.py
  install.sh                # run | install | uninstall | status
  README.md
  .gitignore                # venv, __pycache__, .DS_Store, logs
  docs/superpowers/specs/   # this design
  cursor_usage_menubar/
    __init__.py
    auth.py
    client.py
    app.py
    breakdown.py
```

## install.sh

- `run`: create `.venv` if needed, install requirements, start the app.
- `install`: LaunchAgent at `~/Library/LaunchAgents/com.cursor-usage.menubar.plist` with `RunAtLoad` + `KeepAlive`; log to `~/Library/Logs/cursor-usage-menubar.log` (and error log). The LaunchAgent must not embed tokens.
- `uninstall`: unload, remove plist, `pkill` the app process.
- `status`: show load/process state.

## Testing / acceptance

Verify against the local Cursor session (this machine is signed in):

1. Menu shows live spend/% for this user.
2. Refresh Now updates numbers.
3. Breakdown window shows model bars; Auto expands/collapses via the disclosure triangle.
4. Auto children reflect resolved models from filtered usage events (e.g. Grok 4.5, Opus 5, GPT-5.6 Sol).
5. Works for Enterprise team caps; still falls back for Pro/Ultra period usage.
6. No secrets committed; README documents unofficial API risk and the no-token-storage policy.
7. After a successful refresh/poll, `ps`/`lsof`/project files contain no token files; logs contain no cookies or JWTs.

Automated tests (no live token required):

- Cookie builder: `sub` + token → URL-encoded `WorkosCursorSessionToken` with `%3A%3A`.
- Cents formatting and percent integer rounding.
- Merge preference: usage-summary overall wins when limit > 0.
- Auto child scaling: children sum to Auto `totalCents`.
- Auto event matching: model names containing `(Auto` are attributed to Auto.

Live verification is a script or `run.py` path that prints a redacted snapshot (email domain, plan, spend, model names, no tokens).

## Risks

- Unofficial endpoints and JSON shapes can change. Isolate parsing so one endpoint failure does not take down the menu.
- Cursor may move the state DB or key names. Surface a clear "Cursor login not found" status.
- Publishing later must keep the no-token-storage rules. This implementation does not include a publish pipeline.
