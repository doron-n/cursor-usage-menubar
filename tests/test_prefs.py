import tempfile
import unittest
from pathlib import Path

from cursor_usage_menubar.prefs import load_prefs, save_prefs


class PrefsTest(unittest.TestCase):
    def test_round_trip_scope_and_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prefs.json"
            save_prefs({"scope": "group", "group_id": 9485}, path)
            self.assertEqual(load_prefs(path)["group_id"], 9485)
            self.assertEqual(load_prefs(path)["scope"], "group")
            save_prefs({"scope": "self"}, path)
            loaded = load_prefs(path)
            self.assertEqual(loaded["scope"], "self")
            self.assertEqual(loaded["group_id"], 9485)

    def test_legacy_group_id_infers_group_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prefs.json"
            path.write_text('{"group_id": 9485}\n')
            self.assertEqual(load_prefs(path)["scope"], "group")

    def test_empty_and_invalid_are_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prefs.json"
            self.assertEqual(load_prefs(path)["scope"], "self")
            self.assertIsNone(load_prefs(path)["group_id"])
            save_prefs({"group_id": "nope", "scope": "nope"}, path)
            self.assertIsNone(load_prefs(path)["group_id"])
            self.assertEqual(load_prefs(path)["scope"], "self")
            save_prefs({"scope": "team"}, path)
            self.assertEqual(load_prefs(path)["scope"], "team")
            save_prefs({"theme": "light"}, path)
            self.assertEqual(load_prefs(path)["theme"], "light")
            save_prefs({"theme": "nope"}, path)
            self.assertEqual(load_prefs(path)["theme"], "dark")

    def test_group_ids_round_trip_and_legacy_single_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prefs.json"
            save_prefs({"scope": "group", "group_ids": [10, 10, "20", 30]}, path)
            loaded = load_prefs(path)
            self.assertEqual(loaded["scope"], "group")
            self.assertEqual(loaded["group_ids"], [10, 20, 30])
            self.assertEqual(loaded["group_id"], 10)
            save_prefs({"scope": "self"}, path)
            loaded = load_prefs(path)
            self.assertEqual(loaded["scope"], "self")
            self.assertEqual(loaded["group_ids"], [10, 20, 30])
            path.write_text('{"scope": "group", "group_id": 9485}\n')
            loaded = load_prefs(path)
            self.assertEqual(loaded["group_ids"], [9485])
            self.assertEqual(loaded["group_id"], 9485)

    def test_refresh_and_dock_badge_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prefs.json"
            loaded = load_prefs(path)
            self.assertEqual(loaded["refresh_seconds"], 300)
            self.assertTrue(loaded["dock_badge"])
            save_prefs({"refresh_seconds": 60, "dock_badge": False}, path)
            loaded = load_prefs(path)
            self.assertEqual(loaded["refresh_seconds"], 60)
            self.assertFalse(loaded["dock_badge"])
            save_prefs({"refresh_seconds": 99, "dock_badge": "nope"}, path)
            loaded = load_prefs(path)
            self.assertEqual(loaded["refresh_seconds"], 300)
            self.assertTrue(loaded["dock_badge"])


if __name__ == "__main__":
    unittest.main()
