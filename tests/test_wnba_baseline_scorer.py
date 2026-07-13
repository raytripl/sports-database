from __future__ import annotations

import unittest

import pandas as pd

from src.decisions.score_decision_board import (
    assign_grade,
    deduplicate_player_games,
    filter_pregame_history,
)
from src.decisions.wnba_opportunity import calculate_opportunity_context
from src.decisions.wnba_matchup import (
    calculate_team_matchup_context,
    matchup_opponent,
)
from src.decisions.wnba_suppression import calculate_suppression_context


class BaselineScorerTests(unittest.TestCase):
    def test_grade_is_capped_at_b_plus(self) -> None:
        self.assertEqual(assign_grade("OVER", 100.0, 20), "B+")
        self.assertEqual(assign_grade("UNDER", 95.0, 20), "B+")

    def test_future_games_are_excluded(self) -> None:
        board = pd.DataFrame({"slate_date": ["2026-07-13"]})
        history = pd.DataFrame(
            {
                "GAME_DATE": ["2026-07-12", "2026-07-13", "2026-07-14"],
                "PLAYER_NAME": ["A", "A", "A"],
                "MIN": [30, 31, 32],
            }
        )
        filtered, slate_date = filter_pregame_history(board, history)
        self.assertEqual(str(slate_date.date()), "2026-07-13")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(int(filtered.iloc[0]["MIN"]), 30)

    def test_duplicate_player_games_are_removed(self) -> None:
        history = pd.DataFrame(
            {
                "GAME_ID": [1, 1, 2],
                "PLAYER_ID": [10, 10, 10],
                "PLAYER_NAME": ["A", "A", "A"],
                "PTS": [12, 12, 18],
            }
        )
        result = deduplicate_player_games(history)
        self.assertEqual(len(result), 2)

    def test_stable_minutes_create_higher_opportunity_score(self) -> None:
        stable = pd.DataFrame(
            {
                "MIN": [34, 34, 35, 34, 35, 34, 35, 34, 35, 34],
                "FGA": [14] * 10,
                "FTA": [4] * 10,
            }
        )
        volatile = pd.DataFrame(
            {
                "MIN": [10, 38, 12, 36, 14, 34, 16, 32, 18, 30],
                "FGA": [14] * 10,
                "FTA": [4] * 10,
            }
        )
        stable_result = calculate_opportunity_context(stable, "Points")
        volatile_result = calculate_opportunity_context(volatile, "Points")
        self.assertGreater(
            float(stable_result["opportunity_score"]),
            float(volatile_result["opportunity_score"]),
        )

    def test_declining_minutes_raise_suppression(self) -> None:
        declining = pd.DataFrame(
            {
                "MIN": [36, 36, 35, 34, 32, 28, 25, 22, 20, 18],
                "PTS": [20, 19, 18, 17, 16, 14, 12, 10, 9, 8],
                "FGA": [16, 16, 15, 15, 14, 12, 10, 9, 8, 7],
                "FTA": [4] * 10,
            }
        )
        stable = pd.DataFrame(
            {
                "MIN": [32] * 10,
                "PTS": [15] * 10,
                "FGA": [12] * 10,
                "FTA": [4] * 10,
            }
        )
        declining_result = calculate_suppression_context(declining, "Points", 15.5)
        stable_result = calculate_suppression_context(stable, "Points", 15.5)
        self.assertGreater(
            float(declining_result["suppression_score"]),
            float(stable_result["suppression_score"]),
        )
        self.assertIn(
            "HIST_MINUTES_DECLINE",
            str(declining_result["historical_under_reasons"]),
        )

    def test_ceiling_risk_flags_high_outcomes(self) -> None:
        history = pd.DataFrame(
            {
                "MIN": [34] * 10,
                "PRA": [20, 22, 24, 25, 27, 29, 31, 35, 40, 45],
                "FGA": [14] * 10,
                "FTA": [4] * 10,
            }
        )
        result = calculate_suppression_context(history, "Pts+Rebs+Asts", 26.5)
        self.assertGreater(float(result["ceiling_risk_score"]), 50.0)

    def test_matchup_opponent_parsing(self) -> None:
        self.assertEqual(matchup_opponent("CHI @ LAS", "CHI"), "LAS")
        self.assertEqual(matchup_opponent("LAS vs. CHI", "LAS"), "CHI")

    def test_team_matchup_score_shrinks_small_samples(self) -> None:
        history = pd.DataFrame(
            {
                "GAME_ID": [1, 1, 2, 2],
                "GAME_DATE": pd.to_datetime(
                    ["2026-07-10", "2026-07-10", "2026-07-11", "2026-07-11"]
                ),
                "TEAM_ABBREVIATION": ["ATL", "ATL", "MIN", "MIN"],
                "MATCHUP": ["ATL @ LAS", "ATL @ LAS", "MIN vs. PHX", "MIN vs. PHX"],
                "PTS": [60, 40, 35, 35],
            }
        )
        result = calculate_team_matchup_context(history, "LAS", "Points")
        self.assertEqual(result["team_matchup_sample_size"], 1)
        self.assertGreater(float(result["matchup_score"]), 50.0)
        self.assertLess(float(result["matchup_score"]), 60.0)


if __name__ == "__main__":
    unittest.main()
