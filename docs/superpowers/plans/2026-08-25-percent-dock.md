# Percent-only menu bar + Dock badge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show only the usage percent in the menu bar (`18%` / `—`), put Cursor Usage in the Dock with a matching badge, and open the status-item menu when the Dock icon is clicked.

**Architecture:** `menu_title` and `dock_badge` in `formatters.py` are the only string rules. `app.py` applies both on every refresh, switches to the regular (Dock) activation policy, and installs an `NSApp` reopen handler that clicks the status item. The PyInstaller spec drops `LSUIElement`.

**Tech Stack:** Python 3, rumps 0.4.0, PyObjC AppKit, unittest.

## Global Constraints

- macOS only. Python 3 + rumps + PyObjC.
- Badge uses `NSDockTile.setBadgeLabel_`, not a custom overlay view.
- Packaged `.app` Info.plist must not set `LSUIElement` to true.
- Runtime activation policy is regular (Dock), not accessory.
- Keep existing graceful degradation: fetch errors still use `UsageSnapshot.empty(...)`.
- `spent_cents` stays an argument to `menu_title` so call sites stay unchanged; it no longer affects the title.
- Missing percent always yields menu `—` and badge `""`, even if spend is present.
- Percent alone is enough for a live title (`menu_title(None, 10) == "10%"`).
- rumps 0.4.0 has no `showMenu`; open the menu with `nsstatusitem.button().performClick_(None)`.
- Do not change fetch/auth/merge, View menus, breakdown/users windows, poll interval, or prefs.
- Tests: `.venv/bin/python -m unittest …` (this repo does not use pytest).
- Do not rebuild the `.pkg` unless the user asks after implementation.

## File map

| File | Responsibility |
|---|---|
| `cursor_usage_menubar/formatters.py` | `menu_title`, new `dock_badge` |
| `tests/test_formatters.py` | Formatter expectations |
| `cursor_usage_menubar/app.py` | Apply title + badge, Dock policy, reopen → menu, pin status-item title |
| `tests/test_dock.py` | Badge + reopen helpers with mocks (no rumps run loop) |
| `packaging/Cursor Usage.spec` | Drop `LSUIElement` |
| `README.md` | Document `18%` title, Dock icon, badge |

---

### Task 1: Percent-only title and dock badge strings

**Files:**
- Modify: `tests/test_formatters.py`
- Modify: `cursor_usage_menubar/formatters.py`
- Test: `tests/test_formatters.py`

**Interfaces:**
- Consumes: existing `menu_title(spent_cents: int | None, percent: int | None) -> str`
- Produces: `menu_title(spent_cents: int | None, percent: int | None) -> str` (`"{percent}%"` or `"—"`); `dock_badge(percent: int | None) -> str` (`"{percent}%"` or `""`)

- [ ] **Step 1: Write the failing tests**

In `tests/test_formatters.py`, add `dock_badge` to the import list and replace `test_menu_title_live_and_unknown` plus add `test_dock_badge`:

```python
from cursor_usage_menubar.formatters import (
    child_label,
    dock_badge,
    dollars,
    is_auto_event,
    is_auto_intent,
    menu_title,
    percent_used,
)

    def test_menu_title_live_and_unknown(self):
        self.assertEqual(menu_title(23734, 48), "48%")
        self.assertEqual(menu_title(None, None), "—")
        self.assertEqual(menu_title(100, None), "—")
        self.assertEqual(menu_title(None, 10), "10%")

    def test_dock_badge(self):
        self.assertEqual(dock_badge(48), "48%")
        self.assertEqual(dock_badge(None), "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m unittest tests.test_formatters.FormattersTest.test_menu_title_live_and_unknown tests.test_formatters.FormattersTest.test_dock_badge -v`

Expected: FAIL (`48%` assertion on current `Cursor · $237.34 · 48%`; `dock_badge` ImportError or AttributeError)

- [ ] **Step 3: Write minimal implementation**

Replace `menu_title` in `cursor_usage_menubar/formatters.py` and add `dock_badge` immediately after it:

```python
def menu_title(spent_cents: int | None, percent: int | None) -> str:
    if percent is None:
        return "—"
    return f"{percent}%"


def dock_badge(percent: int | None) -> str:
    if percent is None:
        return ""
    return f"{percent}%"
```

Leave `spent_cents` unused on purpose (call-site compatibility). Do not add a lint ignore unless the file already uses one.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest tests.test_formatters -v`

Expected: PASS (all FormattersTest cases)

- [ ] **Step 5: Commit**

```bash
git add tests/test_formatters.py cursor_usage_menubar/formatters.py
git commit -m "$(cat <<'EOF'
Show only usage percent in the menu-bar title helper.

EOF
)"
```

---

### Task 2: Apply Dock badge, show in Dock, open menu on Dock click

**Files:**
- Create: `tests/test_dock.py`
- Modify: `cursor_usage_menubar/app.py`
- Test: `tests/test_dock.py`

**Interfaces:**
- Consumes: `dock_badge(percent: int | None) -> str`, `menu_title(spent_cents: int | None, percent: int | None) -> str`
- Produces: `set_dock_badge(percent: int | None) -> None`; `pin_status_item_title(nsapp, title: str) -> None`; `handle_dock_reopen(nsapp) -> bool`; `install_dock_reopen() -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dock.py`:

```python
import unittest
from unittest.mock import Mock, patch

from cursor_usage_menubar.app import (
    handle_dock_reopen,
    pin_status_item_title,
    set_dock_badge,
)


class SetDockBadgeTest(unittest.TestCase):
    def test_sets_percent_badge(self):
        tile = Mock()
        app = Mock()
        app.dockTile.return_value = tile
        with patch("cursor_usage_menubar.app.NSApplication") as ns:
            ns.sharedApplication.return_value = app
            set_dock_badge(18)
        tile.setBadgeLabel_.assert_called_once_with("18%")

    def test_clears_badge_when_unknown(self):
        tile = Mock()
        app = Mock()
        app.dockTile.return_value = tile
        with patch("cursor_usage_menubar.app.NSApplication") as ns:
            ns.sharedApplication.return_value = app
            set_dock_badge(None)
        tile.setBadgeLabel_.assert_called_once_with("")

    def test_swallows_appkit_errors(self):
        with patch("cursor_usage_menubar.app.NSApplication") as ns:
            ns.sharedApplication.side_effect = RuntimeError("no app")
            set_dock_badge(18)


class PinStatusItemTitleTest(unittest.TestCase):
    def test_sets_button_title_and_visible(self):
        button = Mock()
        item = Mock()
        item.button.return_value = button
        nsapp = Mock(nsstatusitem=item)
        pin_status_item_title(nsapp, "18%")
        item.setVisible_.assert_called_once_with(True)
        button.setTitle_.assert_called_once_with("18%")

    def test_missing_item_is_noop(self):
        pin_status_item_title(Mock(spec=[]), "18%")


class HandleDockReopenTest(unittest.TestCase):
    def test_clicks_status_item_button(self):
        button = Mock()
        item = Mock()
        item.button.return_value = button
        nsapp = Mock(nsstatusitem=item)
        self.assertTrue(handle_dock_reopen(nsapp))
        button.performClick_.assert_called_once_with(None)

    def test_missing_item_still_returns_true(self):
        self.assertTrue(handle_dock_reopen(Mock(spec=[])))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m unittest tests.test_dock -v`

Expected: FAIL with ImportError (`set_dock_badge` / `handle_dock_reopen` / `pin_status_item_title` not defined)

- [ ] **Step 3: Write minimal implementation**

In `cursor_usage_menubar/app.py`:

1. Change the AppKit import to:

```python
from AppKit import NSApplication, NSApplicationActivationPolicyRegular
```

2. Change the formatters import to:

```python
from cursor_usage_menubar.formatters import dock_badge, dollars, menu_title
```

3. Add these module-level helpers after `_FETCH_ERROR_STATUS` / `_safe_fetch_usage` (before `info_rows`):

```python
def set_dock_badge(percent: int | None) -> None:
    try:
        NSApplication.sharedApplication().dockTile().setBadgeLabel_(dock_badge(percent))
    except Exception:
        return


def pin_status_item_title(nsapp, title: str) -> None:
    item = getattr(nsapp, "nsstatusitem", None)
    if item is None:
        return
    try:
        item.setVisible_(True)
    except Exception:
        pass
    try:
        button = item.button()
    except Exception:
        return
    if button is None:
        return
    try:
        button.setTitle_(title)
    except Exception:
        return


def handle_dock_reopen(nsapp) -> bool:
    item = getattr(nsapp, "nsstatusitem", None)
    if item is None:
        return True
    try:
        button = item.button()
    except Exception:
        return True
    if button is None:
        return True
    try:
        button.performClick_(None)
    except Exception:
        pass
    return True


def install_dock_reopen() -> None:
    from rumps.rumps import NSApp

    def applicationShouldHandleReopen_hasVisibleWindows_(self, app, flag):
        return handle_dock_reopen(self)

    NSApp.applicationShouldHandleReopen_hasVisibleWindows_ = (
        applicationShouldHandleReopen_hasVisibleWindows_
    )
```

4. In `CursorUsageApp.__init__`, change the initial title:

```python
super().__init__("—", quit_button=None)
```

5. Replace `_apply` with:

```python
    def _apply(self, snapshot: UsageSnapshot) -> None:
        self._snapshot = snapshot
        self.title = menu_title(snapshot.spent_cents, snapshot.percent)
        set_dock_badge(snapshot.percent)
        pin_status_item_title(getattr(self, "_nsapp", None), self.title or "—")
        self._rebuild_info(snapshot)
        refresh_if_visible(snapshot)
        refresh_users_if_visible(snapshot)
```

6. Replace `run` with:

```python
    def run(self, **kwargs):
        install_dock_reopen()
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyRegular
        )
        self.refresh_now()
        super().run(**kwargs)
```

Do not add dummy windows. Do not change poll interval, fetch, or menu actions.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest tests.test_dock tests.test_formatters tests.test_app_rows -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_dock.py cursor_usage_menubar/app.py
git commit -m "$(cat <<'EOF'
Show Cursor Usage in the Dock and badge it with usage percent.

EOF
)"
```

---

### Task 3: Packaged app is a Dock app; README matches

**Files:**
- Modify: `packaging/Cursor Usage.spec`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 2 runtime policy (regular / Dock)
- Produces: Info.plist without `LSUIElement`; README copy for `18%` title, Dock icon, and badge

- [ ] **Step 1: Drop LSUIElement from the bundle spec**

In `packaging/Cursor Usage.spec`, change `info_plist` to:

```python
    info_plist={
        "CFBundleName": "Cursor Usage",
        "CFBundleDisplayName": "Cursor Usage",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
        "NSAppleEventsUsageDescription": "Opens the Cursor dashboard in your browser.",
    },
```

Do not set `"LSUIElement": False` either — omit the key. Leave `icon=None` and `bundle_identifier="com.cursor-usage.menubar"`.

- [ ] **Step 2: Update README title/Dock copy**

In `README.md`, replace the paragraph that starts `Menu title looks like` with:

```markdown
Menu title looks like `18%` (or `—` if usage is unknown). The same percent appears as a Dock badge. Click the menu-bar title or the Dock icon for account/plan/view/spend/allowance/remaining/cycle/top model, then:
```

Keep the bullet list and the rest of the README unchanged. Do not rebuild the `.pkg` in this task.

- [ ] **Step 3: Run the existing test suite**

Run: `.venv/bin/python -m unittest discover -s tests -v`

Expected: PASS (all tests)

- [ ] **Step 4: Commit**

```bash
git add "packaging/Cursor Usage.spec" README.md
git commit -m "$(cat <<'EOF'
Let the packaged app appear in the Dock like a normal Mac app.

EOF
)"
```

---

## Spec coverage

| Spec requirement | Task |
|---|---|
| Menu title `18%` / `—` | 1 |
| `dock_badge` `18%` / `""` | 1 |
| `_apply` sets title + badge together | 2 |
| Pin status-item button title | 2 |
| Regular activation policy (Dock) | 2 |
| Dock click / reopen opens status menu | 2 |
| No dummy window | 2 |
| Guard missing dockTile / AppKit | 2 |
| Drop `LSUIElement` from packaged Info.plist | 3 |
| README documents title, Dock, badge | 3 |
| Spend stays in dropdown rows | unchanged (`info_rows`) |
| No fetch/auth/prefs/poll changes | unchanged |
| No `.pkg` rebuild unless asked | 3 explicitly skips |
