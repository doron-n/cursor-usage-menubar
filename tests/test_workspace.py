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
        self.assertIn("Dark mode", inspect.getsource(mod))
        self.assertIn("GaugeView", inspect.getsource(mod))
        self.assertIn("AvatarView", inspect.getsource(mod))

    def test_show_workspace_is_callable(self):
        self.assertTrue(callable(show_workspace))

    def test_default_tab_and_dark_theme(self):
        ctrl = self._controller()
        self.assertEqual(ctrl.tab, "overview")
        self.assertIn(ctrl.theme, ("dark", "light"))
        self.assertEqual(TABS, ("overview", "models", "users"))

    def test_window_not_released_when_closed(self):
        ctrl = self._controller()
        ctrl._ensure_window()
        self.assertFalse(ctrl.window.isReleasedWhenClosed())

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

    def test_users_list_shows_cursor_vs_other_pie(self):
        from dataclasses import replace

        ctrl = self._controller()
        ctrl.snapshot = replace(
            ctrl.snapshot,
            events=(
                UsageEvent(1_777_000_000_000, 700, "ada@x.com", 7, "composer-1", 1, 1),
                UsageEvent(1_777_000_000_100, 300, "ada@x.com", 7, "sonnet", 1, 1),
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
        self.assertIn("CURSOR VS OTHER", joined)
        self.assertIn("Cursor models", joined)
        self.assertIn("Other models", joined)

    def test_users_list_pie_uses_aggregated_models_when_events_empty(self):
        from dataclasses import replace

        ctrl = self._controller()
        ctrl.snapshot = replace(
            ctrl.snapshot,
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
        self.assertIn("$7.00 · 70%", joined)
        self.assertIn("$3.00 · 30%", joined)

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
