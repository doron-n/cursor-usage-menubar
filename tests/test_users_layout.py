import inspect
import unittest

from cursor_usage_menubar.breakdown import (
    BASE_SUMMARY_H,
    FORECAST_SUMMARY_EXTRA,
    FOOTER_H,
    HEADER_H,
    PAD,
    ROW_H,
)
from cursor_usage_menubar.models import BillingGroup, GroupMember, ModelSpend, UsageSnapshot
from cursor_usage_menubar.users import ordered_members, show_users, users_layout_height


def _group_snap(n: int = 2) -> UsageSnapshot:
    members = tuple(
        GroupMember(i, f"u{i}@x.com", f"User {i}", (n - i) * 100, 50000)
        for i in range(n)
    )
    return UsageSnapshot(
        email="ada@example.com",
        team_name="Acme",
        plan_name="Enterprise",
        spent_cents=sum(m.spend_cents for m in members),
        limit_cents=100000,
        remaining_cents=1,
        percent=10,
        cycle_start="2026-08-01",
        cycle_end="2026-08-31",
        models=(),
        status=None,
        top_model=None,
        scope="group",
        group_id=9484,
        group_label="xDome-R&D",
        groups=(BillingGroup(9484, "xDome-R&D", members=members),),
    )


class UsersLayoutTest(unittest.TestCase):
    def test_more_users_is_taller(self):
        self.assertGreater(users_layout_height(_group_snap(8)), users_layout_height(_group_snap(2)))

    def test_ordered_members_highest_spend_first(self):
        names = [m.name for m in ordered_members(_group_snap(3))]
        self.assertEqual(names, ["User 0", "User 1", "User 2"])

    def test_no_webkit(self):
        import cursor_usage_menubar.users as mod

        source = inspect.getsource(mod)
        self.assertNotIn("WebKit", source)
        self.assertNotIn("WKWebView", source)

    def test_show_users_is_callable(self):
        self.assertTrue(callable(show_users))

    def test_summary_always_reserves_forecast_bar(self):
        extra = users_layout_height(_group_snap()) - (
            PAD + HEADER_H + BASE_SUMMARY_H + 36 + ROW_H * 2 + FOOTER_H + PAD
        )
        self.assertEqual(extra, FORECAST_SUMMARY_EXTRA)


class UsersWindowTest(unittest.TestCase):
    def _controller(self):
        from cursor_usage_menubar.users import UsersController

        ctrl = UsersController.alloc().init()
        ctrl.snapshot = _group_snap()
        return ctrl

    def test_window_not_released_when_closed(self):
        ctrl = self._controller()
        ctrl._ensure_window()
        self.assertFalse(ctrl.window.isReleasedWhenClosed())

    def test_ensure_window_reuses_existing_window(self):
        ctrl = self._controller()
        ctrl._ensure_window()
        first = ctrl.window
        ctrl._ensure_window()
        self.assertIs(ctrl.window, first)

    def test_title_is_users_by_usage(self):
        ctrl = self._controller()
        ctrl._ensure_window()
        self.assertEqual(ctrl.window.title(), "Users by Usage")

    def test_summary_draws_actual_and_forecast_bars(self):
        from dataclasses import replace

        ctrl = self._controller()
        claude = ModelSpend(
            "Claude 4.6 Sonnet", "claude-4.6-sonnet", 1800, 1_000_000, 200_000, 10, False
        )
        ctrl.snapshot = replace(_group_snap(), models=(claude,), spent_cents=1800, percent=18)
        ctrl._ensure_window()
        ctrl.render()
        bars = []

        def walk(view):
            for sub in view.subviews():
                if sub.__class__.__name__ == "BarView":
                    bars.append(sub)
                walk(sub)

        walk(ctrl.window.contentView())
        # 2 summary bars (actual + forecast) + 2 per-user bars
        self.assertGreaterEqual(len(bars), 4)

    def test_summary_shows_monthly_budget_and_this_month(self):
        ctrl = self._controller()
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
        self.assertIn("Monthly budget", joined)
        self.assertIn("This month · 10% of monthly budget · 2 users", joined)
        self.assertIn("$1000.00", joined)


if __name__ == "__main__":
    unittest.main()
