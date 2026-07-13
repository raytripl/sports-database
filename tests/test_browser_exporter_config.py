from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "browser-extension" / "sports_hub_prizepicks_extension"


class BrowserExporterConfigTests(unittest.TestCase):
    def test_exporter_defaults_to_all_captured_rows(self):
        html = (ROOT / "popup.html").read_text(encoding="utf-8")
        self.assertIn('id="sports" type="text" value=""', html)
        self.assertNotIn('value="MLB,WNBA"', html)

    def test_downloads_go_to_downloads_root(self):
        script = (ROOT / "popup.js").read_text(encoding="utf-8")
        self.assertIn("`prizepicks_pool_${timestamp()}.csv`", script)
        self.assertNotIn("SportsHub/prizepicks_pool_", script)

    def test_manifest_version(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "1.1.0")


if __name__ == "__main__":
    unittest.main()
