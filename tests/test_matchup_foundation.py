from __future__ import annotations

import unittest

import pandas as pd

from src.imports.capture_matchup_foundation import prepare_pool


class MatchupFoundationTests(unittest.TestCase):
    def row(self) -> dict[str, object]:
        return {
            "player_name": "Player One",
            "team": "AAA",
            "position": "G",
            "stat_type": "Points",
            "line_score": 15.5,
            "game_description": "BBB",
            "captured_at_utc": "2026-07-13T10:00:00Z",
            "slate_date": "2026-07-13",
            "source": "PrizePicks",
        }

    def test_duplicate_capture_is_removed(self) -> None:
        row = self.row()
        result = prepare_pool(pd.DataFrame([row, row]))
        self.assertEqual(len(result), 1)

    def test_invalid_line_is_removed(self) -> None:
        row = self.row()
        row["line_score"] = "bad"
        result = prepare_pool(pd.DataFrame([row]))
        self.assertTrue(result.empty)

    def test_position_is_preserved(self) -> None:
        result = prepare_pool(pd.DataFrame([self.row()]))
        self.assertEqual(result.iloc[0]["position"], "G")


if __name__ == "__main__":
    unittest.main()
