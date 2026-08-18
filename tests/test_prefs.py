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
            self.assertEqual(load_prefs(path)["scope"], "self")


if __name__ == "__main__":
    unittest.main()
