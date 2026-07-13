from __future__ import annotations

import unittest

import pandas as pd

from src.dna.wnba_on_off import calculate_on_off


class WnbaOnOffTests(unittest.TestCase):
    def history(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"GAME_ID": 1, "GAME_DATE": "2026-07-01", "PLAYER_ID": 10,
                 "PLAYER_NAME": "Target", "TEAM_ABBREVIATION": "AAA", "MIN": 30,
                 "PTS": 10, "FGA": 8},
                {"GAME_ID": 1, "GAME_DATE": "2026-07-01", "PLAYER_ID": 20,
                 "PLAYER_NAME": "Teammate", "TEAM_ABBREVIATION": "AAA", "MIN": 25,
                 "PTS": 5, "FGA": 4},
                {"GAME_ID": 2, "GAME_DATE": "2026-07-02", "PLAYER_ID": 10,
                 "PLAYER_NAME": "Target", "TEAM_ABBREVIATION": "AAA", "MIN": 36,
                 "PTS": 20, "FGA": 16},
                {"GAME_ID": 3, "GAME_DATE": "2026-07-20", "PLAYER_ID": 10,
                 "PLAYER_NAME": "Target", "TEAM_ABBREVIATION": "AAA", "MIN": 40,
                 "PTS": 50, "FGA": 30},
                {"GAME_ID": 4, "GAME_DATE": "2026-06-20", "PLAYER_ID": 10,
                 "PLAYER_NAME": "Target", "TEAM_ABBREVIATION": "OLD", "MIN": 40,
                 "PTS": 99, "FGA": 40},
            ]
        )

    def test_with_without_delta_and_cutoff(self) -> None:
        result = calculate_on_off(
            self.history(), "Target", "Teammate", "2026-07-13", ["PTS", "FGA"]
        )
        points = result[result["metric"] == "PTS"].iloc[0]
        self.assertEqual(points["with_games"], 1)
        self.assertEqual(points["without_games"], 1)
        self.assertEqual(points["with_average"], 10)
        self.assertEqual(points["without_average"], 20)
        self.assertEqual(points["without_minus_with"], 10)

    def test_low_sample_is_flagged(self) -> None:
        result = calculate_on_off(
            self.history(), "Target", "Teammate", "2026-07-13", ["PTS"]
        )
        self.assertEqual(result.iloc[0]["sample_flag"], "LOW_SAMPLE")

    def test_same_player_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            calculate_on_off(
                self.history(), "Target", "Target", "2026-07-13", ["PTS"]
            )


if __name__ == "__main__":
    unittest.main()
