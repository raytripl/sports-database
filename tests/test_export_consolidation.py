from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.imports.consolidate_exports import consolidate_directory


def write_export(path: Path, league: str, player: str, projection: str) -> None:
    pd.DataFrame([{
        "projection_id": projection, "league": league, "player_name": player,
        "team": "AAA", "stat_type": "Points", "line_score": 10.5,
        "odds_type": "standard", "start_time": "2026-07-13T20:00:00Z",
    }]).to_csv(path, index=False)


class ExportConsolidationTests(unittest.TestCase):
    def test_newest_file_per_league_is_combined(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_wnba = root / "wnba_old.csv"
            new_wnba = root / "wnba_new.csv"
            tennis = root / "tennis.csv"
            write_export(old_wnba, "WNBA", "Old Guard", "1")
            write_export(new_wnba, "WNBA", "New Guard", "2")
            write_export(tennis, "TENNIS", "Server", "3")
            os.utime(old_wnba, (1000, 1000))
            os.utime(new_wnba, (2000, 2000))
            os.utime(tennis, (2100, 2100))
            output = root / "combined" / "latest.csv"
            path, manifest = consolidate_directory(
                root, output, anchor=tennis, max_age_hours=1
            )
            frame = pd.read_csv(path)
            self.assertEqual(set(frame["league"]), {"WNBA", "TENNIS"})
            self.assertIn("New Guard", set(frame["player_name"]))
            self.assertNotIn("Old Guard", set(frame["player_name"]))
            self.assertEqual(manifest["mode"], "CONSOLIDATED_EXPORTS")

    def test_single_export_is_returned_without_rewrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "wnba.csv"
            write_export(source, "WNBA", "Guard", "1")
            path, manifest = consolidate_directory(root, root / "out.csv", anchor=source)
            self.assertEqual(path, source)
            self.assertEqual(manifest["mode"], "SINGLE_EXPORT")


if __name__ == "__main__":
    unittest.main()
