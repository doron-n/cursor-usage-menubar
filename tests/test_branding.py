import unittest

from cursor_usage_menubar.branding import icon_path
from cursor_usage_menubar.theme import DARK, usage_tone


class BrandingTest(unittest.TestCase):
    def test_app_icon_exists(self):
        path = icon_path()
        self.assertTrue(path.is_file(), path)
        self.assertGreater(path.stat().st_size, 1000)

    def test_icns_exists_for_bundle(self):
        icns = icon_path().parents[2] / "packaging" / "CursorUsage.icns"
        self.assertTrue(icns.is_file(), icns)
        self.assertGreater(icns.stat().st_size, 1000)

    def test_dark_theme_is_cyan_not_system_green(self):
        red, green, blue, _alpha = DARK["accent"]
        self.assertGreater(green, 0.7)
        self.assertGreater(blue, 0.6)
        self.assertLess(red, 0.4)


class UiViewsTest(unittest.TestCase):
    def test_gauge_and_graph_construct(self):
        from AppKit import NSMakeRect
        from cursor_usage_menubar.ui import AvatarView, GaugeView, GraphView, PieView

        gauge = GaugeView.alloc().initWithFrame_percent_theme_(
            NSMakeRect(0, 0, 120, 120), 76, "dark"
        )
        self.assertEqual(gauge.percent, 76)
        graph = GraphView.alloc().initWithFrame_series_theme_(
            NSMakeRect(0, 0, 200, 80), (("2026-08-01", 100), ("2026-08-02", 240)), "dark"
        )
        self.assertEqual(len(graph.series), 2)
        avatar = AvatarView.alloc().initWithFrame_name_color_(
            NSMakeRect(0, 0, 36, 36), "Yair Zori", usage_tone("dark", 40)
        )
        self.assertIsNotNone(avatar)
        pie = PieView.alloc().initWithFrame_cursor_other_theme_(
            NSMakeRect(0, 0, 80, 80), 700, 300, "dark"
        )
        self.assertEqual(pie.cursor_cents, 700)
        self.assertEqual(pie.other_cents, 300)


if __name__ == "__main__":
    unittest.main()
