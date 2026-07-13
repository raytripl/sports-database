from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.automation.prizepicks_hourly import eligible_mlb_dates
from src.decisions.score_mlb_decision_board import (
    grade,
    matchup_context,
    opportunity_context,
    result_column,
    score_board,
)


class MlbBaselineTests(unittest.TestCase):
    def test_hourly_router_uses_only_today_and_tomorrow(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        frame = pd.DataFrame({
            "league": ["MLB", "MLB", "MLB", "WNBA"],
            "slate_date": ["2026-07-13", "2026-07-14", "2026-07-15", "2026-07-13"],
        })
        now = datetime(2026, 7, 13, 12, tzinfo=ZoneInfo("America/Chicago"))
        self.assertEqual(eligible_mlb_dates(frame, now), ["2026-07-13", "2026-07-14"])

    def test_prop_aliases(self):
        self.assertEqual(result_column("Hitter Fantasy Score (PP)"), "HITTER_FANTASY_PP")
        self.assertEqual(result_column("Hits+Runs+RBIs"), "H_PLUS_R_PLUS_RBI")
        self.assertEqual(result_column("Pitcher Strikeouts"), "K")

    def test_grade_is_capped_at_b_plus(self):
        self.assertEqual(grade("OVER", 100, 20), "B+")

    def test_hitter_opportunity_uses_plate_appearances(self):
        history = pd.DataFrame({"PA": [4, 5, 4, 5, 4]})
        context = opportunity_context(history, False)
        self.assertGreater(context["opportunity_score"], 70)
        self.assertAlmostEqual(context["expected_plate_appearances"], 4.4)

    def test_pitcher_opportunity_uses_workload(self):
        history = pd.DataFrame({"PITCHES": [92, 96, 98], "OUTS": [18, 19, 20]})
        context = opportunity_context(history, True)
        self.assertGreater(context["opportunity_score"], 75)
        self.assertGreater(context["expected_innings"], 6)

    def test_small_matchup_sample_is_shrunk(self):
        history = pd.DataFrame({"OPPONENT": ["NYY", "BOS", "BOS"], "H": [3, 1, 1]})
        context = matchup_context(history, "NYY", "H")
        self.assertLess(context["matchup_score"], 60)

    def test_future_history_excluded_and_recommendations_off(self):
        board = pd.DataFrame([{
            "decision_id": 1, "slate_date": "2026-07-13", "player": "Test Hitter",
            "opponent": "NYY", "prop_type": "Hits", "line": 0.5,
            "direction": "", "grade": "", "entry_type": "", "over_reason": "",
            "under_reason": "", "red_flags": "", "decision_reason": "",
            "model_score": None, "overall_rank": None, "same_player_rank": None,
            "opportunity_score": None, "suppression_score": None, "matchup_score": None,
            "skill_score": None, "role_score": None, "workload_score": None,
            "coach_score": None, "manager_score": None, "ceiling_risk_score": None,
            "line_value_score": None, "evidence_agreement_score": None,
            "recommended": 0, "lineup_confirmed": None, "batting_order": None,
            "starter_confirmed": None, "injury_status": None, "minutes_restriction": None,
            "expected_minutes": None, "expected_plate_appearances": None,
            "expected_innings": None, "expected_pitch_count": None,
            "opponent_k_percent": None, "opponent_k_percent_vs_hand": None,
            "confirmed_lineup_k_percent": None,
        }])
        history = pd.DataFrame([
            {"RESULT_DATE": "2026-07-10", "PLAYER_NAME": "Test Hitter", "PLAYER_TYPE": "HITTER", "OPPONENT": "NYY", "PA": 4, "H": 1},
            {"RESULT_DATE": "2026-07-11", "PLAYER_NAME": "Test Hitter", "PLAYER_TYPE": "HITTER", "OPPONENT": "NYY", "PA": 4, "H": 2},
            {"RESULT_DATE": "2026-07-12", "PLAYER_NAME": "Test Hitter", "PLAYER_TYPE": "HITTER", "OPPONENT": "NYY", "PA": 4, "H": 1},
            {"RESULT_DATE": "2026-07-14", "PLAYER_NAME": "Test Hitter", "PLAYER_TYPE": "HITTER", "OPPONENT": "NYY", "PA": 5, "H": 0},
        ])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            board_path, history_path, output = root / "board.csv", root / "history.csv", root / "out.csv"
            board.to_csv(board_path, index=False)
            history.to_csv(history_path, index=False)
            score_board(board_path, history_path, output)
            scored = pd.read_csv(output)
        self.assertEqual(scored.loc[0, "sample_size"], 3)
        self.assertEqual(scored.loc[0, "recommended"], 0)
        self.assertNotIn(scored.loc[0, "grade"], {"A", "A+"})


if __name__ == "__main__":
    unittest.main()
