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
        self.assertEqual(versions[0], "1.0.3")
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
        self.assertIn("changelog.json", html)
        self.assertIn("api.github.com/repos/", html)
        self.assertIn("/releases", html)
        self.assertIn("Global budget", html)
        self.assertNotIn("WebKit", html)


if __name__ == "__main__":
    unittest.main()
