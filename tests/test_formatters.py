import unittest

from cursor_usage_menubar.formatters import (
    child_label,
    dollars,
    is_auto_event,
    is_auto_intent,
    menu_title,
    percent_used,
)


class FormattersTest(unittest.TestCase):
    def test_dollars_two_places(self):
        self.assertEqual(dollars(23734), "$237.34")
        self.assertEqual(dollars(0), "$0.00")

    def test_percent_integer_and_none_without_limit(self):
        self.assertEqual(percent_used(23734, 50000), 47)
        self.assertIsNone(percent_used(100, 0))
        self.assertIsNone(percent_used(100, -1))

    def test_menu_title_live_and_unknown(self):
        self.assertEqual(menu_title(23734, 48), "Cursor · $237.34 · 48%")
        self.assertEqual(menu_title(None, None), "Cursor · —")
        self.assertEqual(menu_title(100, None), "Cursor · —")
        self.assertEqual(menu_title(None, 10), "Cursor · —")

    def test_auto_event_matching(self):
        self.assertTrue(is_auto_event("Cursor Grok 4.5 (Auto Balanced)"))
        self.assertTrue(is_auto_event("Composer (default)"))
        self.assertFalse(is_auto_event("Cursor Grok 4.5"))

    def test_auto_intent(self):
        self.assertTrue(is_auto_intent("auto-smart"))
        self.assertTrue(is_auto_intent("auto"))
        self.assertFalse(is_auto_intent("claude-4.6-sonnet"))

    def test_child_label_strips_auto_suffix(self):
        self.assertEqual(
            child_label("Cursor Grok 4.5 (Auto Balanced)"),
            "Grok 4.5",
        )


if __name__ == "__main__":
    unittest.main()
