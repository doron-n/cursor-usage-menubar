import inspect
import unittest

from cursor_usage_menubar.models import (
    BillingGroup,
    GroupMember,
    ModelSpend,
    UsageEvent,
    UsageSnapshot,
)
from cursor_usage_menubar.workspace import TABS, WorkspaceController, show_workspace


def _snap() -> UsageSnapshot:
    ada = GroupMember(7, "ada@x.com", "Ada", 1200, 10000)
    return UsageSnapshot(
        email="a@b.c",
        team_name="Acme",
        plan_name="Enterprise",
        spent_cents=1000,
        limit_cents=5000,
        remaining_cents=4000,
        percent=20,
        cycle_start="2026-08-01",
        cycle_end="2026-08-31",
        models=(),
        status=None,
        top_model=None,
        groups=(BillingGroup(1, "Eng", 1200, 10000, (ada,)),),
        events=(UsageEvent(1_777_000_000_000, 400, "ada@x.com", 7, "grok-4.5", 10, 4),),
    )


class WorkspaceTest(unittest.TestCase):
    def tearDown(self):
        WorkspaceController._instance = None

    def _controller(self):
        ctrl = WorkspaceController.alloc().init()
        ctrl.snapshot = _snap()
        return ctrl

    def test_no_webkit(self):
        import cursor_usage_menubar.ui as ui
        import cursor_usage_menubar.workspace as mod

        for source in (inspect.getsource(mod), inspect.getsource(ui)):
            self.assertNotIn("WebKit", source)
            self.assertNotIn("WKWebView", source)
        self.assertIn("Overview", inspect.getsource(mod))
        self.assertIn("Settings", inspect.getsource(mod))
        self.assertIn("Dark mode", inspect.getsource(mod))
        self.assertIn("GaugeView", inspect.getsource(mod))
        self.assertIn("AvatarView", inspect.getsource(mod))

    def test_show_workspace_is_callable(self):
        self.assertTrue(callable(show_workspace))

    def test_default_tab_and_dark_theme(self):
        ctrl = self._controller()
        self.assertEqual(ctrl.tab, "overview")
        self.assertIn(ctrl.theme, ("dark", "light"))
        self.assertEqual(TABS, ("overview", "models", "users", "settings"))

    def test_window_not_released_when_closed(self):
        ctrl = self._controller()
        ctrl._ensure_window()
        self.assertFalse(ctrl.window.isReleasedWhenClosed())

    def test_non_admin_sees_permission_message_not_usage(self):
        from cursor_usage_menubar.roles import NO_ADMIN_STATUS

        ctrl = self._controller()
        ctrl.snapshot = UsageSnapshot.empty(NO_ADMIN_STATUS)
        ctrl._ensure_window()
        ctrl.render()
        texts = []

        def walk(view):
            for sub in view.subviews():
                getter = getattr(sub, "stringValue", None)
                if callable(getter):
                    texts.append(str(getter()))
                walk(sub)

        walk(ctrl.window.contentView())
        joined = "\n".join(texts)
        self.assertIn("No permission", joined)
        self.assertIn("admin role is required", joined)
        self.assertNotIn("$10.00", joined)

    def test_settings_tab_shows_configuration(self):
        from cursor_usage_menubar.roles import NO_ADMIN_STATUS

        ctrl = self._controller()
        ctrl.tab = "settings"
        ctrl._ensure_window()
        ctrl.render()
        texts = []

        def walk(view):
            for sub in view.subviews():
                getter = getattr(sub, "stringValue", None)
                if callable(getter):
                    texts.append(str(getter()))
                title = getattr(sub, "title", None)
                if callable(title):
                    texts.append(str(title()))
                walk(sub)

        walk(ctrl.window.contentView())
        joined = "\n".join(texts)
        self.assertIn("DATA VIEW", joined)
        self.assertIn("APPEARANCE", joined)
        self.assertIn("REFRESH", joined)
        self.assertIn("Dark mode", joined)
        self.assertIn("Version", joined)
        ctrl.snapshot = UsageSnapshot.empty(NO_ADMIN_STATUS)
        ctrl.render()
        texts = []
        walk(ctrl.window.contentView())
        joined = "\n".join(texts)
        self.assertIn("DATA VIEW", joined)
        self.assertNotIn("No permission", joined)

    def test_window_shows_app_version(self):
        from cursor_usage_menubar.app_version import current_version

        ctrl = self._controller()
        ctrl._ensure_window()
        ctrl.render()
        version = current_version()
        self.assertEqual(ctrl.window.title(), f"Cursor Usage {version}")
        texts = []

        def walk(view):
            for sub in view.subviews():
                getter = getattr(sub, "stringValue", None)
                if callable(getter):
                    texts.append(str(getter()))
                walk(sub)

        walk(ctrl.window.contentView())
        joined = "\n".join(texts)
        self.assertIn(f"v{version}", joined)

    def test_tabs_and_theme_actions(self):
        from unittest.mock import Mock, patch

        ctrl = self._controller()
        ctrl._ensure_window()
        sender = Mock()
        sender.selectedSegment.return_value = 1
        ctrl.tabChanged_(sender)
        self.assertEqual(ctrl.tab, "models")
        toggle = Mock()
        toggle.state.return_value = 0
        with patch("cursor_usage_menubar.workspace.save_prefs"):
            ctrl.themeChanged_(toggle)
        self.assertEqual(ctrl.theme, "light")

    def test_open_user_then_back(self):
        ctrl = self._controller()
        ctrl._ensure_window()
        ctrl.openUser_(7)
        self.assertEqual(ctrl.tab, "users")
        self.assertEqual(ctrl.selected_user_id, 7)
        self.assertEqual(ctrl._selected_member(ctrl.snapshot).name, "Ada")
        ctrl.closeUser_(None)
        self.assertIsNone(ctrl.selected_user_id)

    def test_user_detail_shows_top_three_models(self):
        from dataclasses import replace

        ctrl = self._controller()
        ctrl.snapshot = replace(
            ctrl.snapshot,
            events=(
                UsageEvent(1_777_000_000_000, 900, "ada@x.com", 7, "composer-1", 1, 1),
                UsageEvent(1_777_000_000_100, 400, "ada@x.com", 7, "grok-4.5", 1, 1),
                UsageEvent(1_777_000_000_200, 250, "ada@x.com", 7, "sonnet", 1, 1),
                UsageEvent(1_777_000_000_300, 50, "ada@x.com", 7, "opus", 1, 1),
            ),
        )
        ctrl._ensure_window()
        ctrl.openUser_(7)
        texts = []

        def walk(view):
            for sub in view.subviews():
                getter = getattr(sub, "stringValue", None)
                if callable(getter):
                    texts.append(str(getter()))
                walk(sub)

        walk(ctrl.window.contentView())
        joined = "\n".join(texts)
        self.assertIn("TOP 3 MODELS", joined)
        self.assertIn("composer-1", joined)
        self.assertIn("grok-4.5", joined)
        self.assertIn("sonnet", joined)
        self.assertIn("CURSOR VS OTHER", joined)
        self.assertIn("Cursor models", joined)
        self.assertIn("Other models", joined)
        self.assertIn("$9.75 · 81%", joined)
        self.assertIn("$2.25 · 19%", joined)

    def test_user_detail_loads_events_when_team_window_missed_user(self):
        from dataclasses import replace
        from unittest.mock import patch

        ctrl = self._controller()
        ctrl.snapshot = replace(ctrl.snapshot, events=())
        fetched = (
            UsageEvent(1_777_000_000_000, 900, None, 7, "composer-2", 1, 1),
            UsageEvent(1_777_000_000_100, 400, None, 7, "grok-4.5", 1, 1),
        )
        ctrl._ensure_window()
        with patch(
            "cursor_usage_menubar.workspace.load_member_events", return_value=fetched
        ) as mocked:
            ctrl.openUser_(7)
        mocked.assert_called()
        texts = []

        def walk(view):
            for sub in view.subviews():
                getter = getattr(sub, "stringValue", None)
                if callable(getter):
                    texts.append(str(getter()))
                walk(sub)

        walk(ctrl.window.contentView())
        joined = "\n".join(texts)
        self.assertIn("composer-2", joined)
        self.assertIn("grok-4.5", joined)
        self.assertIn("$9.00", joined)

    def test_users_list_splits_bar_and_can_sort_by_cursor(self):
        from dataclasses import replace

        ada = GroupMember(1, "ada@x.com", "Ada", 4000, 50000)
        bob = GroupMember(2, "bob@x.com", "Bob", 8000, 50000)
        ctrl = self._controller()
        ctrl.snapshot = replace(
            ctrl.snapshot,
            groups=(BillingGroup(1, "Eng", 12000, 100000, (ada, bob)),),
            events=(
                UsageEvent(1_777_000_000_000, 400, "ada@x.com", 1, "composer-1", 1, 1),
                UsageEvent(1_777_000_000_100, 100, "ada@x.com", 1, "sonnet", 1, 1),
                UsageEvent(1_777_000_000_200, 600, "bob@x.com", 2, "composer-1", 1, 1),
                UsageEvent(1_777_000_000_300, 2400, "bob@x.com", 2, "sonnet", 1, 1),
            ),
        )
        ctrl.tab = "users"
        ctrl.user_sort = "cursor"
        ctrl._ensure_window()
        ctrl.render()
        names = [m.name for m in ctrl._visible_users(ctrl.snapshot)]
        self.assertEqual(names, ["Ada", "Bob"])
        bars = []

        def walk(view):
            for sub in view.subviews():
                if sub.__class__.__name__ == "SplitBarView":
                    bars.append(sub)
                walk(sub)

        walk(ctrl.window.contentView())
        self.assertGreaterEqual(len(bars), 2)
        by_cursor = {bar.cursor_cents: bar.other_cents for bar in bars}
        self.assertEqual(by_cursor.get(400), 100)
        self.assertEqual(by_cursor.get(600), 2400)

    def test_users_list_shows_cursor_vs_other_pie(self):
        from dataclasses import replace

        ctrl = self._controller()
        ctrl.snapshot = replace(
            ctrl.snapshot,
            spent_cents=10000,
            events=(
                UsageEvent(1_777_000_000_000, 700, "ada@x.com", 7, "composer-1", 1, 1),
                UsageEvent(1_777_000_000_100, 300, "ada@x.com", 7, "sonnet", 1, 1),
            ),
        )
        ctrl.tab = "users"
        ctrl._ensure_window()
        ctrl.render()
        texts = []
        pies = []

        def walk(view):
            for sub in view.subviews():
                if sub.__class__.__name__ == "PieView":
                    pies.append(sub)
                getter = getattr(sub, "stringValue", None)
                if callable(getter):
                    texts.append(str(getter()))
                walk(sub)

        walk(ctrl.window.contentView())
        joined = "\n".join(texts)
        self.assertIn("CURSOR VS OTHER", joined)
        self.assertIn("Cursor models", joined)
        self.assertIn("Other models", joined)
        self.assertIn("$70.00 · 70%", joined)
        self.assertIn("$30.00 · 30%", joined)
        self.assertGreaterEqual(len(pies), 1)
        self.assertEqual(pies[0].cursor_cents, 7000)
        self.assertEqual(pies[0].other_cents, 3000)

    def test_users_list_pie_uses_aggregated_models_when_events_empty(self):
        from dataclasses import replace

        ctrl = self._controller()
        ctrl.snapshot = replace(
            ctrl.snapshot,
            spent_cents=10000,
            events=(),
            models=(
                ModelSpend("composer-1", "composer-1", 700, 1, 1, 1, False),
                ModelSpend("sonnet", "sonnet", 300, 1, 1, 1, False),
            ),
        )
        ctrl.tab = "users"
        ctrl._ensure_window()
        ctrl.render()
        texts = []

        def walk(view):
            for sub in view.subviews():
                getter = getattr(sub, "stringValue", None)
                if callable(getter):
                    texts.append(str(getter()))
                walk(sub)

        walk(ctrl.window.contentView())
        joined = "\n".join(texts)
        self.assertIn("$70.00 · 70%", joined)
        self.assertIn("$30.00 · 30%", joined)

    def test_overview_shows_month_daily_spend_and_top_week_spenders(self):
        import time
        from dataclasses import replace

        now_ms = int(time.time() * 1000)
        day = 24 * 60 * 60 * 1000
        ada = GroupMember(1, "ada@x.com", "Ada", 4000, 50000)
        bob = GroupMember(2, "bob@x.com", "Bob", 8000, 50000)
        cam = GroupMember(3, "cam@x.com", "Cam", 1000, 50000)
        dan = GroupMember(4, "dan@x.com", "Dan", 9000, 50000)
        ctrl = self._controller()
        ctrl.snapshot = replace(
            ctrl.snapshot,
            groups=(BillingGroup(1, "Eng", 1200, 10000, (ada, bob, cam, dan)),),
            events=(
                UsageEvent(now_ms - day, 300, "ada@x.com", 1),
                UsageEvent(now_ms - 2 * day, 900, "bob@x.com", 2),
                UsageEvent(now_ms - 3 * day, 500, "cam@x.com", 3),
                UsageEvent(now_ms - 10 * day, 8000, "dan@x.com", 4),
            ),
        )
        ctrl._ensure_window()
        ctrl.render()
        texts = []

        def walk(view):
            for sub in view.subviews():
                getter = getattr(sub, "stringValue", None)
                if callable(getter):
                    texts.append(str(getter()))
                walk(sub)

        walk(ctrl.window.contentView())
        joined = "\n".join(texts)
        self.assertIn("SPEND THIS MONTH", joined)
        self.assertIn("per day", joined)
        self.assertIn("SPEND SPIKES · LAST 7 DAYS", joined)
        self.assertIn("Ada", joined)
        self.assertIn("Bob", joined)
        self.assertIn("Cam", joined)
        self.assertNotIn("Dan", joined)
        self.assertIn("$9.00 · 7 days", joined)
        self.assertIn("$5.00 · 7 days", joined)
        self.assertIn("$3.00 · 7 days", joined)
        self.assertNotIn("SPEND THIS CYCLE", joined)
        self.assertNotIn("burning budget unusually fast", joined)

    def test_overview_shows_cursor_vs_other_beside_budget(self):
        from dataclasses import replace

        ada = GroupMember(1, "ada@x.com", "Ada", 1000, 10000)
        ctrl = self._controller()
        ctrl.snapshot = replace(
            ctrl.snapshot,
            spent_cents=10000,
            groups=(BillingGroup(1, "Eng", 1000, 10000, (ada,)),),
            events=(
                UsageEvent(1_777_000_000_000, 700, "ada@x.com", 1, "composer-1", 1, 1),
                UsageEvent(1_777_000_000_100, 300, "ada@x.com", 1, "sonnet", 1, 1),
            ),
        )
        ctrl._ensure_window()
        ctrl.render()
        texts = []
        pies = []

        def walk(view):
            for sub in view.subviews():
                if sub.__class__.__name__ == "PieView":
                    pies.append(sub)
                getter = getattr(sub, "stringValue", None)
                if callable(getter):
                    texts.append(str(getter()))
                walk(sub)

        walk(ctrl.window.contentView())
        joined = "\n".join(texts)
        self.assertIn("CURSOR VS OTHER", joined)
        self.assertIn("Cursor models", joined)
        self.assertIn("Other models", joined)
        self.assertIn("$70.00 · 70%", joined)
        self.assertIn("$30.00 · 30%", joined)
        self.assertGreaterEqual(len(pies), 1)
        self.assertEqual(pies[0].cursor_cents, 7000)
        self.assertEqual(pies[0].other_cents, 3000)

    def test_filter_keeps_full_query_and_search_field(self):
        from unittest.mock import Mock

        ctrl = self._controller()
        ctrl.tab = "users"
        ctrl._ensure_window()
        ctrl.render()
        field = ctrl._search
        self.assertIsNotNone(field)
        field.setStringValue_("y")
        note = Mock()
        note.object.return_value = field
        ctrl.controlTextDidChange_(note)
        self.assertEqual(ctrl.user_query, "y")
        self.assertIs(ctrl._search, field)
        field.setStringValue_("ya")
        note.object.return_value = field
        ctrl.controlTextDidChange_(note)
        self.assertEqual(ctrl.user_query, "ya")
        self.assertEqual(ctrl._search.stringValue(), "ya")
        self.assertIs(ctrl._search, field)


if __name__ == "__main__":
    unittest.main()
