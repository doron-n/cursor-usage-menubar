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
