import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.audits.resolve_full_board import (
    classify_status,
    load_results,
    opportunity_fields,
    result_column,
    select_result_rows,
)


class FullBoardAuditTests(unittest.TestCase):
    def test_directional_statuses_and_pass(self):
        self.assertEqual(classify_status("OVER", 6, 5), "HIT")
        self.assertEqual(classify_status("UNDER", 6, 5), "MISS")
        self.assertEqual(classify_status("OVER", 5, 5), "PUSH")
        self.assertEqual(classify_status("PASS", 6, 5), "PASS")

    def test_prop_mappings_cover_full_game_markets(self):
        self.assertEqual(result_column("WNBA", "Pts+Rebs+Asts"), "PRA")
        self.assertEqual(result_column("WNBA", "3-PT Attempted"), "FG3A")
        self.assertEqual(result_column("MLB", "Pitcher Strikeouts"), "K")
        self.assertEqual(result_column("MLB", "Hitter Fantasy Score (PP)"), "HITTER_FANTASY_PP")
        self.assertIsNone(result_column("WNBA", "1H Points"))

    def test_mlb_pitcher_and_hitter_rows_are_separated(self):
        frame = pd.DataFrame([
            {"_player_key": "twoway", "PLAYER_TYPE": "HITTER"},
            {"_player_key": "twoway", "PLAYER_TYPE": "PITCHER"},
        ])
        self.assertEqual(len(select_result_rows(frame, "Two Way", "MLB", "K")), 1)
        self.assertEqual(select_result_rows(frame, "Two Way", "MLB", "K").iloc[0]["PLAYER_TYPE"], "PITCHER")
        self.assertEqual(select_result_rows(frame, "Two Way", "MLB", "H").iloc[0]["PLAYER_TYPE"], "HITTER")

    def test_future_and_duplicate_results_are_excluded(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "wnba.csv"
            pd.DataFrame([
                {"GAME_ID": 1, "GAME_DATE": "2026-07-12", "PLAYER_ID": 7, "PLAYER_NAME": "A", "MIN": 20},
                {"GAME_ID": 1, "GAME_DATE": "2026-07-12", "PLAYER_ID": 7, "PLAYER_NAME": "A", "MIN": 22},
                {"GAME_ID": 2, "GAME_DATE": "2026-07-13", "PLAYER_ID": 7, "PLAYER_NAME": "A", "MIN": 30},
            ]).to_csv(path, index=False)
            result = load_results(path, "WNBA", "2026-07-12")
            self.assertEqual(len(result), 1)
            self.assertEqual(result.iloc[0]["MIN"], 22)

    def test_opportunity_fields_are_sport_specific(self):
        wnba = opportunity_fields("WNBA", pd.Series({"MIN": 31}))
        hitter = opportunity_fields("MLB", pd.Series({"PLAYER_TYPE": "HITTER", "PA": 5}))
        pitcher = opportunity_fields("MLB", pd.Series({"PLAYER_TYPE": "PITCHER", "IP": 6, "PITCHES": 94}))
        self.assertEqual(wnba["minutes"], 31)
        self.assertEqual(hitter["plate_appearances"], 5)
        self.assertEqual(pitcher["innings"], 6)
        self.assertEqual(pitcher["pitch_count"], 94)


if __name__ == "__main__":
    unittest.main()
