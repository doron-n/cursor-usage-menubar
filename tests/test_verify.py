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
