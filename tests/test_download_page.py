import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "docs" / "index.html"
CHANGELOG = ROOT / "docs" / "changelog.json"


class DownloadPageTest(unittest.TestCase):
    def test_changelog_covers_current_and_previous(self):
        data = json.loads(CHANGELOG.read_text(encoding="utf-8"))
        versions = [rel["version"] for rel in data["releases"]]
        self.assertEqual(versions[0], "1.0.19")
        self.assertIn("1.0.9", versions)
        self.assertIn("1.0.8", versions)
        self.assertIn("1.0.7", versions)
        self.assertIn("1.0.6", versions)
        self.assertIn("1.0.5", versions)
        self.assertIn("1.0.4", versions)
        self.assertIn("1.0.3", versions)
        self.assertIn("1.0.2", versions)
        self.assertIn("1.0.1", versions)
        latest = data["releases"][0]
        self.assertTrue(latest["title"])
        self.assertGreaterEqual(len(latest["highlights"]), 3)

    def test_page_has_notes_and_download(self):
        html = INDEX.read_text(encoding="utf-8")
        self.assertIn("What’s new", html)
        self.assertIn('id="latest"', html)
        self.assertIn('id="previous"', html)
        self.assertIn('id="downloads"', html)
        self.assertIn("download_count", html)
        self.assertIn("function downloadTotal", html)
        self.assertIn("changelog.json", html)
        self.assertIn("api.github.com/repos/", html)
        self.assertIn("/releases", html)
        self.assertIn("Highlights for this build", html)
        self.assertIn("Global budget", html)
        self.assertIn("assets/app-icon.png", html)
        self.assertIn("assets/overview.png", html)
        self.assertIn("assets/users.png", html)
        self.assertIn("assets/settings.png", html)
        self.assertIn("@keyframes", html)
        self.assertTrue((ROOT / "docs" / "assets" / "overview.png").is_file())
        self.assertTrue((ROOT / "docs" / "assets" / "users.png").is_file())
        self.assertTrue((ROOT / "docs" / "assets" / "settings.png").is_file())
        for version in ("1.0.19", "1.0.18", "1.0.17", "1.0.16", "1.0.15", "1.0.14", "1.0.13", "1.0.12", "1.0.11", "1.0.10", "1.0.9", "1.0.8", "1.0.7", "1.0.6", "1.0.5", "1.0.4", "1.0.3", "1.0.2", "1.0.1"):
            self.assertIn('"' + version + '"', html)
        self.assertNotIn("WebKit", html)
        self.assertTrue((ROOT / "docs" / "assets" / "app-icon.png").is_file())


if __name__ == "__main__":
    unittest.main()
