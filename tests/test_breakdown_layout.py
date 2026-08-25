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

    def test_forecast_summary_is_taller_for_third_party(self):
        from cursor_usage_menubar.breakdown import BASE_SUMMARY_H, summary_height

        claude = ModelSpend(
            "Claude 4.6 Sonnet", "claude-4.6-sonnet", 1800, 1_000_000, 200_000, 10, False
        )
        mix = UsageSnapshot(
            email="a@b.c",
            team_name="Acme",
            plan_name="Enterprise",
            spent_cents=1800,
            limit_cents=10000,
            remaining_cents=8200,
            percent=18,
            cycle_start=None,
            cycle_end=None,
            models=(claude,),
            status=None,
            top_model=claude,
        )
        self.assertGreater(summary_height(mix), BASE_SUMMARY_H)

    def test_no_webkit(self):
        import cursor_usage_menubar.breakdown as mod

        source = inspect.getsource(mod)
        self.assertNotIn("WebKit", source)
        self.assertNotIn("WKWebView", source)
        self.assertIn("NSDisclosureBezelStyle", source)

    def test_show_breakdown_is_callable(self):
        self.assertTrue(callable(show_breakdown))

    def test_model_filter_popup_is_wired(self):
        import cursor_usage_menubar.breakdown as mod

        source = inspect.getsource(mod)
        self.assertIn("NSPopUpButton", source)
        self.assertIn("filterChanged:", source)
        self.assertIn("Cursor models", source)
        self.assertIn("Other models", source)


class BreakdownWindowTest(unittest.TestCase):
    def _controller(self):
        from cursor_usage_menubar.breakdown import BreakdownController

        ctrl = BreakdownController.alloc().init()
        ctrl.snapshot = _snap()
        return ctrl

    def test_default_filter_is_all_models(self):
        ctrl = self._controller()
        self.assertEqual(ctrl.model_filter, "all")

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

    def test_ensure_window_recreates_when_window_gone(self):
        ctrl = self._controller()
        ctrl._ensure_window()
        first = ctrl.window
        ctrl._window_alive = lambda: False
        ctrl._ensure_window()
        self.assertIsNot(ctrl.window, first)

    def test_window_background_is_control_background_color(self):
        from AppKit import NSColor

        ctrl = self._controller()
        ctrl._ensure_window()
        self.assertTrue(
            ctrl.window.backgroundColor().isEqual_(NSColor.controlBackgroundColor())
        )

    def test_scroll_view_draws_control_background(self):
        from AppKit import NSColor

        ctrl = self._controller()
        ctrl._ensure_window()
        ctrl.render()
        scroll = ctrl.window.contentView()
        self.assertTrue(scroll.drawsBackground())
        self.assertTrue(
            scroll.backgroundColor().isEqual_(NSColor.controlBackgroundColor())
        )


if __name__ == "__main__":
    unittest.main()
