import unittest
from unittest.mock import patch

from cursor_usage_menubar.app import _safe_fetch_usage, info_rows, user_usage_rows
from cursor_usage_menubar.models import BillingGroup, GroupMember, ModelSpend, UsageSnapshot


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
        self.assertTrue(any(r == "View: Team (all)" for r in rows))
        self.assertFalse(any("Grok" in r for r in rows))

    def test_view_row_shows_myself_and_group(self):
        base = dict(
            email="ada@example.com",
            team_name="Acme",
            plan_name="Enterprise",
            spent_cents=100,
            limit_cents=200,
            remaining_cents=100,
            percent=50,
            cycle_start=None,
            cycle_end=None,
            models=(),
            status=None,
            top_model=None,
        )
        self.assertTrue(
            any(r == "View: Myself only" for r in info_rows(UsageSnapshot(**base, scope="self")))
        )
        self.assertTrue(
            any(
                r == "View: Platform (9485)"
                for r in info_rows(
                    UsageSnapshot(**base, scope="group", group_id=9485, group_label="Platform")
                )
            )
        )

    def test_group_view_lists_users_not_as_top_model(self):
        snap = UsageSnapshot(
            email="ada@example.com",
            team_name="Acme",
            plan_name="Enterprise",
            spent_cents=300,
            limit_cents=1000,
            remaining_cents=700,
            percent=30,
            cycle_start=None,
            cycle_end=None,
            models=(),
            status=None,
            top_model=None,
            scope="group",
            group_id=9484,
            group_label="xDome-R&D",
            groups=(
                BillingGroup(
                    id=9484,
                    name="xDome-R&D",
                    spend_cents=300,
                    members=(
                        GroupMember(1, "a@x.com", "Ada", 200, 50000),
                        GroupMember(2, "b@x.com", "Bob", 100, 50000),
                    ),
                ),
            ),
        )
        rows = info_rows(snap)
        self.assertTrue(any(r.startswith("Top user: Ada") for r in rows))
        self.assertFalse(any(r.startswith("Top model:") for r in rows))
        users = user_usage_rows(snap)
        self.assertEqual(users[0], "Users by usage")
        self.assertTrue(any(u.startswith("Ada · $2.00") for u in users))
        self.assertTrue(any(u.startswith("Bob · $1.00") for u in users))

    def test_status_row_when_signed_out(self):
        snap = UsageSnapshot.empty("Open Cursor to refresh your session")
        rows = info_rows(snap)
        self.assertEqual(rows[0], "Open Cursor to refresh your session")

    def test_safe_fetch_usage_degrades_instead_of_raising(self):
        with patch(
            "cursor_usage_menubar.app.fetch_usage", side_effect=RuntimeError("boom")
        ):
            snap = _safe_fetch_usage()
        self.assertIsNone(snap.spent_cents)
        self.assertEqual(snap.status, "Open Cursor to refresh your session")

    def test_safe_fetch_usage_passes_through_on_success(self):
        good = UsageSnapshot.empty("fine")
        with patch("cursor_usage_menubar.app.fetch_usage", return_value=good):
            snap = _safe_fetch_usage()
        self.assertIs(snap, good)


if __name__ == "__main__":
    unittest.main()
