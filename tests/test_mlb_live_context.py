from __future__ import annotations

import unittest

import pandas as pd

from src.decisions.enrich_mlb_live_context import live_flags, replace_flags
from src.imports.fetch_mlb_live_context import build_context


class MlbLiveContextTests(unittest.TestCase):
    def test_official_feed_parses_lineup_pitcher_and_weather(self):
        schedule = {
            "dates": [{"games": [{
                "gamePk": 123,
                "status": {"detailedState": "Scheduled"},
                "venue": {"name": "Park"},
                "teams": {
                    "away": {"team": {"abbreviation": "NYY"}, "probablePitcher": {"id": 8, "fullName": "Away Pitcher"}},
                    "home": {"team": {"abbreviation": "BOS"}, "probablePitcher": {"id": 9, "fullName": "Home Pitcher"}},
                },
            }]}]
        }
        feed = {
            "gameData": {
                "status": {"detailedState": "Pre-Game"},
                "venue": {"name": "Fenway Park"},
                "weather": {"condition": "Cloudy", "temp": 74, "wind": "8 mph"},
            },
            "liveData": {"boxscore": {"teams": {
                "away": {"battingOrder": list(range(1, 10)), "players": {f"ID{i}": {"person": {"fullName": f"Away {i}"}} for i in range(1, 10)}},
                "home": {"battingOrder": list(range(11, 20)), "players": {f"ID{i}": {"person": {"fullName": f"Home {i}"}} for i in range(11, 20)}},
            }}},
        }

        def fake_fetch(url: str) -> dict:
            return schedule if "schedule" in url else feed

        frame = build_context("2026-07-13", fake_fetch, "2026-07-13T12:00:00Z")
        hitter = frame[frame["player"] == "Away 1"].iloc[0]
        pitcher = frame[frame["player"] == "Away Pitcher"].iloc[0]
        self.assertEqual(hitter["batting_order"], 1)
        self.assertEqual(hitter["lineup_confirmed"], 1)
        self.assertEqual(hitter["weather_condition"], "Cloudy")
        self.assertEqual(pitcher["starter_confirmed"], 1)

    def test_missing_hitter_lineup_is_hard_veto(self):
        row = pd.Series({"game_status": "Scheduled", "lineup_confirmed": 0, "batting_order": None, "weather_condition": "Clear"})
        flags = live_flags("HITTER", row)
        self.assertIn("HARD_VETO_UNCONFIRMED_LINEUP", flags)
        self.assertIn("HARD_VETO_MISSING_BATTING_ORDER", flags)

    def test_pitcher_keeps_k_rate_veto(self):
        row = pd.Series({"game_status": "Scheduled", "starter_confirmed": 1, "weather_condition": "Clear"})
        flags = live_flags("PITCHER", row)
        self.assertIn("HARD_VETO_K_RATE_NOT_VERIFIED", flags)

    def test_live_flags_are_replaced_not_duplicated(self):
        existing = "Baseline; MLB_LIVE[OLD]"
        self.assertEqual(replace_flags(existing, ["NEW"]), "Baseline; MLB_LIVE[NEW]")


if __name__ == "__main__":
    unittest.main()
