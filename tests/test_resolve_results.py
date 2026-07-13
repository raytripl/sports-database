from __future__ import annotations

import unittest

import pandas as pd

from src.audits.resolve_results import (
    classify_status,
    deduplicate_player_games,
    normalize_name,
    result_value,
)


class ResultResolverTests(unittest.TestCase):
    def test_name_normalization(self) -> None:
        self.assertEqual(normalize_name("A'ja Wilson"), "ajawilson")

    def test_directional_statuses(self) -> None:
        self.assertEqual(classify_status("OVER", 21, 20.5), "HIT")
        self.assertEqual(classify_status("OVER", 20, 20.5), "MISS")
        self.assertEqual(classify_status("UNDER", 20, 20.5), "HIT")
        self.assertEqual(classify_status("UNDER", 21, 20.5), "MISS")
        self.assertEqual(classify_status("PASS", 21, 20.5), "PASS")
        self.assertEqual(classify_status("PASS", 20.5, 20.5), "PASS")
        self.assertEqual(classify_status("OVER", 20.5, 20.5), "PUSH")

    def test_prop_mapping(self) -> None:
        row = pd.Series({"PRA": 30, "FG3M": 4})
        self.assertEqual(result_value(row, "Pts+Rebs+Asts"), 30.0)
        self.assertEqual(result_value(row, "3-PT Made"), 4.0)
        self.assertIsNone(result_value(row, "Unsupported"))

    def test_duplicate_player_games_are_removed(self) -> None:
        frame = pd.DataFrame(
            {
                "GAME_ID": [1, 1],
                "PLAYER_ID": [10, 10],
                "PLAYER_NAME": ["Test Player", "Test Player"],
                "MIN": [30, 31],
            }
        )
        result = deduplicate_player_games(frame)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["MIN"], 31)


if __name__ == "__main__":
    unittest.main()
