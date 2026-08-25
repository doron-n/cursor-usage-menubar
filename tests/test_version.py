import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from cursor_usage_menubar.app_version import (
    bump,
    current_version,
    notes_for,
    read_version,
    version_label,
    write_version,
)


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

    def test_notes_history_includes_older_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "changelog.json"
            path.write_text(
                '{"releases":['
                '{"version":"1.0.10","title":"Month graph","highlights":["Pages events"]},'
                '{"version":"1.0.3","title":"Global budget","highlights":["View → Global"]},'
                '{"version":"1.0.1","title":"Public page","highlights":["First installer"]}'
                "]}\n"
            )
            notes = notes_for("1.0.10", path, history=True)
        self.assertIn("Month graph", notes)
        self.assertIn("- Pages events", notes)
        self.assertIn("## 1.0.3 — Global budget", notes)
        self.assertIn("## 1.0.1 — Public page", notes)

    def test_notes_for_unknown_version_is_generic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "changelog.json"
            path.write_text('{"releases":[]}\n')
            notes = notes_for("9.9.9", path)
        self.assertIn("Cursor Usage 9.9.9 for Apple Silicon.", notes)
        self.assertNotIn("- ", notes)

    def test_current_version_reads_version_file(self):
        env = {key: value for key, value in os.environ.items() if key != "CURSOR_USAGE_VERSION"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(current_version(), read_version())
            self.assertEqual(version_label(), f"Version {read_version()}")

    def test_current_version_prefers_env(self):
        with patch.dict(os.environ, {"CURSOR_USAGE_VERSION": "9.9.9"}):
            self.assertEqual(current_version(), "9.9.9")

    def test_frozen_app_reads_info_plist(self):
        bundle = Mock()
        bundle.infoDictionary.return_value = {"CFBundleShortVersionString": "1.2.3"}
        env = {key: value for key, value in os.environ.items() if key != "CURSOR_USAGE_VERSION"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("sys.frozen", True, create=True),
            patch("Foundation.NSBundle") as ns_bundle,
        ):
            ns_bundle.mainBundle.return_value = bundle
            self.assertEqual(current_version(), "1.2.3")


if __name__ == "__main__":
    unittest.main()
