import tempfile
import unittest
from pathlib import Path

from cursor_usage_menubar.app_version import bump, notes_for, read_version, write_version


class VersionBumpTest(unittest.TestCase):
    def test_patch_minor_major(self):
        self.assertEqual(bump("1.0.0"), "1.0.1")
        self.assertEqual(bump("1.0.9", "patch"), "1.0.10")
        self.assertEqual(bump("1.2.3", "minor"), "1.3.0")
        self.assertEqual(bump("1.2.3", "major"), "2.0.0")

    def test_rejects_junk(self):
        with self.assertRaises(ValueError):
            bump("1.0")
        with self.assertRaises(ValueError):
            bump("1.0.0", "build")

    def test_round_trip_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "VERSION"
            write_version("1.4.2", path)
            self.assertEqual(read_version(path), "1.4.2")

    def test_notes_for_uses_changelog_highlights(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "changelog.json"
            path.write_text(
                '{"releases":[{"version":"1.0.3","title":"Global budget",'
                '"highlights":["View → Global","Model filter"]}]}\n'
            )
            notes = notes_for("1.0.3", path)
        self.assertIn("Cursor Usage 1.0.3 for Apple Silicon.", notes)
        self.assertIn("Global budget", notes)
        self.assertIn("- View → Global", notes)
        self.assertIn("- Model filter", notes)
        self.assertIn("doron-n.github.io/cursor-usage-menubar", notes)

    def test_notes_for_unknown_version_is_generic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "changelog.json"
            path.write_text('{"releases":[]}\n')
            notes = notes_for("9.9.9", path)
        self.assertIn("Cursor Usage 9.9.9 for Apple Silicon.", notes)
        self.assertNotIn("- ", notes)


if __name__ == "__main__":
    unittest.main()
