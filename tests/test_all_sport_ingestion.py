from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.imports.process_pool import process_pool


class AllSportIngestionTests(unittest.TestCase):
    def test_every_sport_is_preserved_but_unsupported_sports_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "mixed.csv"
            rows = []
            for index, league in enumerate(["WNBA", "MLB", "TENNIS", "CS2", "LOL"], start=1):
                rows.append({
                    "projection_id": str(index), "league": league,
                    "player_name": f"Player {index}", "team": "AAA",
                    "position": "", "stat_type": "Points", "line_score": 10.5,
                    "odds_type": "standard", "start_time": "2026-07-13T20:00:00Z",
                    "downloaded_at_utc": "2026-07-13T18:00:00Z",
                })
            pd.DataFrame(rows).to_csv(source, index=False)
            processed_dir = root / "processed"
            with (
                patch("src.imports.process_pool.PROCESSED_DIR", processed_dir),
                patch("src.imports.process_pool.ARCHIVE_DIR", root / "archive"),
            ):
                _, _, _, _, processed, standard = process_pool(source)

            self.assertEqual(set(processed["league"]), {"WNBA", "MLB", "TENNIS", "CS2", "LOL"})
            active = processed[processed["league"].isin(["MLB", "WNBA"])]
            unsupported = processed[~processed["league"].isin(["MLB", "WNBA"])]
            self.assertTrue(active["model_status"].eq("ACTIVE_BASELINE").all())
            self.assertTrue(unsupported["model_status"].eq("UNSUPPORTED_PASS").all())
            self.assertEqual(len(standard), 5)

            queue = pd.read_csv(processed_dir / "raymond_unsupported_queue_latest.csv")
            self.assertEqual(set(queue["league"]), {"TENNIS", "CS2", "LOL"})
            self.assertTrue(queue["direction"].eq("PASS").all())
            self.assertTrue(queue["recommended"].eq(0).all())


if __name__ == "__main__":
    unittest.main()
