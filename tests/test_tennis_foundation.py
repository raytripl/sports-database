from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.tennis.capture_props import capture_pool, player_key


class TennisFoundationTests(unittest.TestCase):
    def test_name_normalization(self):
        self.assertEqual(player_key("Benoît Paire"), "benoitpaire")

    def test_capture_is_idempotent_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pool = root / "tennis.csv"
            database = root / "sports.db"
            pd.DataFrame([
                {
                    "projection_id": "1", "league": "TENNIS", "player_name": "Player One",
                    "player_id": "10", "team": "Player One", "stat_type": "Aces",
                    "line_score": 5.5, "odds_type": "standard",
                    "projection_type": "Single Stat", "start_time": "2026-07-14T12:00:00Z",
                    "game_description": "Player Two", "captured_at_utc": "2026-07-13T20:00:00Z",
                },
                {
                    "projection_id": "2", "league": "TENNIS", "player_name": "Player One",
                    "player_id": "10", "team": "Player One", "stat_type": "Aces",
                    "line_score": 8.5, "odds_type": "demon",
                    "projection_type": "Single Stat", "start_time": "2026-07-14T12:00:00Z",
                    "game_description": "Player Two", "captured_at_utc": "2026-07-13T20:00:00Z",
                },
                {
                    "projection_id": "3", "league": "WNBA", "player_name": "Guard",
                    "team": "AAA", "stat_type": "Points", "line_score": 10.5,
                    "odds_type": "standard", "start_time": "2026-07-14T12:00:00Z",
                },
            ]).to_csv(pool, index=False)
            with patch("src.db.DB_PATH", database):
                first = capture_pool(pool)
                second = capture_pool(pool)
                import sqlite3
                with closing(sqlite3.connect(database)) as connection:
                    lines = pd.read_sql_query("SELECT * FROM tennis_prop_lines", connection)
                    captures = pd.read_sql_query("SELECT * FROM tennis_captures", connection)
            self.assertEqual(first["rows"], 2)
            self.assertEqual(first["standard_rows"], 1)
            self.assertEqual(first["rows_inserted"], 2)
            self.assertEqual(second["rows_inserted"], 0)
            self.assertEqual(len(lines), 2)
            self.assertEqual(len(captures), 1)
            self.assertTrue(lines["direction"].eq("PASS").all())
            self.assertTrue(lines["recommended"].eq(0).all())


if __name__ == "__main__":
    unittest.main()
