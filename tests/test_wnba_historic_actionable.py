import unittest

import pandas as pd

from src.decisions.build_wnba_actionable import classify
from src.wnba.backfill_results import prepare_history


class HistoricActionableTests(unittest.TestCase):
    def test_backfill_adds_two_point_fields_and_deduplicates(self):
        frame = pd.DataFrame([
            {"GAME_ID": "1", "GAME_DATE": "2026-06-01", "PLAYER_ID": 2,
             "PLAYER_NAME": "A", "TEAM_ID": 3, "TEAM_ABBREVIATION": "ATL",
             "MATCHUP": "ATL vs. LAS", "MIN": 30, "PTS": 10, "REB": 4,
             "AST": 2, "OREB": 1, "DREB": 3, "FGM": 4, "FGA": 9,
             "FG3M": 1, "FG3A": 3, "FTM": 1, "FTA": 2, "STL": 1,
             "BLK": 0, "TOV": 2},
        ] * 2)
        result = prepare_history(frame, "07/12/2026")
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["FG2M"], 3)
        self.assertEqual(result.iloc[0]["FG2A"], 6)

    def base_row(self):
        return pd.Series({
            "direction": "OVER", "grade": "B+", "sample_size": 18,
            "model_score": 82, "over_score": 82, "under_score": 30,
            "opportunity_score": 75, "injury_status": "ACTIVE",
            "lineup_confirmed": "yes", "minutes_restriction": "",
            "availability_captured_at": "2026-07-13T17:00:00-05:00",
            "slate_date": "2026-07-13",
        })

    def test_live_confirmation_can_create_flex_review_only(self):
        status, _ = classify(self.base_row())
        self.assertEqual(status, "ACTIONABLE_FLEX_REVIEW")

    def test_missing_live_context_blocks_candidate(self):
        row = self.base_row()
        row["lineup_confirmed"] = ""
        status, reason = classify(row)
        self.assertEqual(status, "LIVE_BLOCKED")
        self.assertEqual(reason, "LINEUP_UNCONFIRMED")

    def test_history_below_ten_is_pass(self):
        row = self.base_row()
        row["sample_size"] = 9
        status, reason = classify(row)
        self.assertEqual(status, "PASS")
        self.assertIn("HISTORY_LT_10", reason)


if __name__ == "__main__":
    unittest.main()
