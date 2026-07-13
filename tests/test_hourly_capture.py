from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from src.automation.prizepicks_hourly import eligible_wnba_dates
from src.decisions.save_snapshot import filter_to_sport


class HourlyCaptureTests(unittest.TestCase):
    def test_only_today_and_tomorrow_wnba_are_routed(self) -> None:
        frame = pd.DataFrame(
            {
                "league": ["WNBA", "WNBA", "WNBA", "MLB"],
                "slate_date": [
                    "2026-07-13", "2026-07-14", "2026-07-15", "2026-07-13"
                ],
            }
        )
        now = datetime(2026, 7, 13, 12, tzinfo=ZoneInfo("America/Chicago"))
        self.assertEqual(
            eligible_wnba_dates(frame, now), ["2026-07-13", "2026-07-14"]
        )

    def test_sport_boundary_blocks_cross_sport_rows(self) -> None:
        frame = pd.DataFrame(
            {"league": ["WNBA", "MLB"], "player": ["Guard", "Hitter"]}
        )
        result = filter_to_sport(frame, "WNBA")
        self.assertEqual(result["player"].tolist(), ["Guard"])


if __name__ == "__main__":
    unittest.main()
