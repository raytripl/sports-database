from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.mlb.backfill_history import boxscore_rows, merge_history


def sample_boxscore(name: str = "Test Player") -> dict:
    return {"teams": {
        "away": {"team": {"abbreviation": "NYY"}, "players": {"ID1": {
            "person": {"id": 1, "fullName": name},
            "stats": {
                "batting": {"plateAppearances": 4, "atBats": 3, "hits": 2,
                            "doubles": 1, "triples": 0, "homeRuns": 0,
                            "runs": 1, "rbi": 1, "baseOnBalls": 1,
                            "hitByPitch": 0, "stolenBases": 0, "strikeOuts": 0},
                "pitching": {},
            },
        }}},
        "home": {"team": {"abbreviation": "BOS"}, "players": {}},
    }}


class MlbHistoryBackfillTests(unittest.TestCase):
    def test_hitter_formulas(self):
        row = boxscore_rows("2026-07-01", 10, sample_boxscore())[0]
        self.assertEqual(row["TOTAL_BASES"], 3)
        self.assertEqual(row["H_PLUS_R_PLUS_RBI"], 4)
        self.assertEqual(row["HITTER_FANTASY_PP"], 14)

    def test_doubleheaders_are_preserved(self):
        one = pd.DataFrame(boxscore_rows("2026-07-01", 10, sample_boxscore()))
        two = pd.DataFrame(boxscore_rows("2026-07-01", 11, sample_boxscore()))
        merged = merge_history(pd.DataFrame(), pd.concat([one, two]), "2026-07-01", "2026-07-01")
        self.assertEqual(len(merged), 2)
        self.assertEqual(set(merged["GAME_ID"]), {"10", "11"})

    def test_refetched_range_replaces_old_rows(self):
        old = pd.DataFrame([{
            "RESULT_DATE": "2026-07-01", "GAME_ID": "old", "PLAYER_NAME": "OLD",
            "PLAYER_TYPE": "HITTER"
        }, {
            "RESULT_DATE": "2026-06-30", "GAME_ID": "keep", "PLAYER_NAME": "KEEP",
            "PLAYER_TYPE": "HITTER"
        }])
        new = pd.DataFrame(boxscore_rows("2026-07-01", 10, sample_boxscore()))
        merged = merge_history(old, new, "2026-07-01", "2026-07-01")
        self.assertNotIn("OLD", set(merged["PLAYER_NAME"]))
        self.assertIn("KEEP", set(merged["PLAYER_NAME"]))


if __name__ == "__main__":
    unittest.main()
