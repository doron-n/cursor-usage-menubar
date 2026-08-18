import inspect
import unittest

from cursor_usage_menubar.models import BillingGroup, GroupMember, UsageSnapshot
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


if __name__ == "__main__":
    unittest.main()
