from __future__ import annotations

import unittest
from datetime import datetime, timezone

import pandas as pd

from src.imports.wnba_official_injuries import (
    candidate_times,
    compare_reports,
    parse_positioned_pages,
    report_url,
)


class OfficialWnbaInjuryTests(unittest.TestCase):
    def test_urls_use_eastern_quarter_hours(self) -> None:
        now = datetime(2026, 7, 14, 22, 52, tzinfo=timezone.utc)
        candidates = candidate_times(now, lookback_hours=.25)
        self.assertEqual(len(candidates), 2)
        self.assertTrue(report_url(candidates[0]).endswith("2026-07-14_06_45PM.pdf"))

    def test_positioned_table_carries_game_and_team_fields(self) -> None:
        page = [
            (24, 141, "07/14/2026"), (121, 141, "07:00"), (146, 141, "(ET)"),
            (201, 141, "WAS@TOR"), (265, 141, "Toronto"), (300, 141, "Tempo"),
            (426, 141, "Fagbenle,"), (468, 141, "Temi"), (587, 141, "Out"),
            (667, 141, "Concussion"), (715, 141, "Protocol"),
            (426, 163, "Rice,"), (448, 163, "Kiki"), (587, 163, "Out"),
            (667, 163, "Injury/Illness"), (727, 163, "Left Ankle"),
        ]
        result = parse_positioned_pages([page])
        self.assertEqual(result["player"].tolist(), ["Temi Fagbenle", "Kiki Rice"])
        self.assertTrue(result["team"].eq("Toronto Tempo").all())
        self.assertTrue(result["matchup"].eq("WAS@TOR").all())

    def test_changes_detect_status_transitions(self) -> None:
        keys = {"game_date": "2026-07-14", "game_time": "07:00", "matchup": "WAS@TOR", "team": "Toronto Tempo", "player": "Temi Fagbenle", "reason": "Concussion"}
        old = pd.DataFrame([keys | {"injury_status": "QUESTIONABLE"}])
        new = pd.DataFrame([keys | {"injury_status": "OUT"}])
        changes = compare_reports(old, new)
        self.assertEqual(changes.iloc[0]["previous_status"], "QUESTIONABLE")
        self.assertEqual(changes.iloc[0]["current_status"], "OUT")


if __name__ == "__main__":
    unittest.main()
