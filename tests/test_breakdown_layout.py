import inspect
import unittest

from cursor_usage_menubar.breakdown import layout_height, show_breakdown
from cursor_usage_menubar.models import ModelSpend, UsageSnapshot


def _snap() -> UsageSnapshot:
    child = ModelSpend("Grok 4.5", "grok", 800, 10, 4, 3, False, ())
    auto = ModelSpend("Auto", "auto-smart", 1000, 12, 5, 3, True, (child,))
    return UsageSnapshot(
        email="a@b.c",
        team_name="Acme",
        plan_name="Enterprise",
        spent_cents=1000,
        limit_cents=2000,
        remaining_cents=1000,
        percent=50,
        cycle_start="2026-08-01",
        cycle_end="2026-08-31",
        models=(auto,),
        status=None,
        top_model=auto,
    )


class BreakdownLayoutTest(unittest.TestCase):
    def test_expanded_auto_is_taller(self):
        snap = _snap()
        self.assertGreater(layout_height(snap, True), layout_height(snap, False))

    def test_no_webkit(self):
        import cursor_usage_menubar.breakdown as mod

        source = inspect.getsource(mod)
        self.assertNotIn("WebKit", source)
        self.assertNotIn("WKWebView", source)
        self.assertIn("NSDisclosureBezelStyle", source)

    def test_show_breakdown_is_callable(self):
        self.assertTrue(callable(show_breakdown))


if __name__ == "__main__":
    unittest.main()
