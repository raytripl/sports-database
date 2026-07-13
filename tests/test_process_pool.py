from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.imports.process_pool import process_pool


class ProcessPoolTests(unittest.TestCase):
    def test_mixed_dates_and_download_timestamp_are_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "incoming.csv"
            frame = pd.DataFrame(
                [
                    {
                        "projection_id": 1,
                        "league": "WNBA",
                        "player_name": "Today",
                        "team": "AAA",
                        "position": "G",
                        "stat_type": "Points",
                        "line_score": 10.5,
                        "odds_type": "standard",
                        "start_time": "2026-07-13T19:00:00-04:00",
                        "downloaded_at_utc": "2026-07-13T18:00:00Z",
                    },
                    {
                        "projection_id": 2,
                        "league": "WNBA",
                        "player_name": "Tomorrow",
                        "team": "BBB",
                        "position": "F",
                        "stat_type": "Rebounds",
                        "line_score": 7.5,
                        "odds_type": "demon",
                        "start_time": "2026-07-14T19:00:00-04:00",
                        "downloaded_at_utc": "2026-07-13T18:00:00Z",
                    },
                ]
            )
            frame.to_csv(source, index=False)

            with (
                patch("src.imports.process_pool.PROCESSED_DIR", root / "processed"),
                patch("src.imports.process_pool.ARCHIVE_DIR", root / "archive"),
            ):
                _, _, _, _, processed, standard = process_pool(source)

            self.assertEqual(len(processed), 2)
            self.assertEqual(set(processed["slate_date"]), {"2026-07-13", "2026-07-14"})
            self.assertTrue(processed["captured_at_utc"].notna().all())
            self.assertEqual(len(standard), 1)


if __name__ == "__main__":
    unittest.main()
