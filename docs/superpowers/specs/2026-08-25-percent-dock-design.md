# Percent-only menu bar + Dock badge — Design

Date: 2026-08-25  
Status: approved in conversation; awaiting user review of this file  
Project: `~/Projects/cursor-usage-menubar`  
Platform: macOS only

Make the menu-bar extra shorter and easier to find: show **usage percent only** in the menu bar, put **Cursor Usage in the Dock**, and show the **same percent as a Dock badge**. Clicking the Dock icon opens the existing status-item menu.

This document is the implementation contract for this change only. Unofficial Cursor APIs and token rules from the 2026-08-17 design still apply.

## Goals

- Menu-bar title is `18%` when percent is known.
- Menu-bar title is `—` when percent is unknown (signed out, fetch failure, no cap).
- Cursor Usage appears in the Dock (not background-only).
- Dock badge shows `18%` when known, and is empty when unknown.
- Clicking the Dock icon (or reactivating the running app) opens the same menu as the menu-bar title.
- Spend dollars stay in the dropdown info rows (`Spent`, `Allowance`). They are not in the menu-bar title.

## Non-goals

- No custom drawn Dock artwork.
- No percentage drawn as a status-item image (plain text title only).
- No change to fetch/auth/merge, View menus, breakdown/users windows, or poll interval.
- No new prefs keys.
- No token storage or OAuth refresh.

## Constraints

- macOS only. Python 3 + rumps + PyObjC.
- Badge uses `NSDockTile.setBadgeLabel_`, not a custom overlay view.
- Packaged `.app` Info.plist must not set `LSUIElement` to true.
- Runtime activation policy is regular (Dock), not accessory.
- Keep existing graceful degradation: fetch errors still use `UsageSnapshot.empty(...)`.

## Architecture

Two formatters, one apply path.

| Unit | Responsibility |
|---|---|
| `menu_title(spent_cents, percent)` | Menu-bar string: `f"{percent}%"` or `"—"` |
| `dock_badge(percent)` | Dock badge string: `f"{percent}%"` or `""` |
| `app.py` `_apply` | Sets rumps title, pins status item, sets dock badge |
| Packaging spec | Drop `LSUIElement`; keep bundle id `com.cursor-usage.menubar` |
| rumps `NSApp` reopen | `applicationShouldHandleReopen_hasVisibleWindows_` clicks the status item |

`spent_cents` remains an argument to `menu_title` so call sites stay unchanged. It no longer affects the title. Title is percent-only; missing percent always yields `—`, even if spend is present.

### Data flow

1. Poll / Refresh Now → `fetch_usage()` → `UsageSnapshot` (unchanged).
2. `_apply` sets `self.title = menu_title(...)`.
3. `_apply` sets `NSApplication.sharedApplication().dockTile().setBadgeLabel_(dock_badge(snapshot.percent))`.
4. Status-item pin (`button.setTitle_` / `setVisible_`) still runs so macOS 26 menu-bar extras keep the new short title.

### Dock click

When the app is already running, a Dock click should open the status-item menu via rumps `NSApp.showMenu()` (`button.performClick_`). Return `True` from the reopen handler. Do not open a new dummy window.

### Error handling

- Unknown percent: menu `—`, badge `""`.
- Missing `dockTile` / AppKit during tests: setting the badge must not crash (guard in `app.py`).
- Existing fetch/auth failures unchanged.

## Testing

Update `tests/test_formatters.py`:

- `menu_title(23734, 48) == "48%"`
- `menu_title(None, None) == "—"`
- `menu_title(100, None) == "—"`
- `menu_title(None, 10) == "10%"` — percent alone is enough; spend is not required

Add:

- `dock_badge(48) == "48%"`
- `dock_badge(None) == ""`

No live API test for this change. README: document the new title (`18%`), Dock icon, and badge.

## Out of scope follow-ups

- Rebuilding/installing the `.pkg` happens after implementation if the user asks.
- Removing leftover `build/pkg-payload` copies is not part of this spec.
