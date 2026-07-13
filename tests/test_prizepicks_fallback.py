from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.automation.prizepicks_hourly import (
    acquire_pool,
    find_latest_export,
    single_run_lock,
    valid_export,
)


class PrizePicksFallbackTests(unittest.TestCase):
    def test_stale_lock_is_recovered(self):
        with tempfile.TemporaryDirectory() as folder:
            lock = Path(folder) / "capture.lock"
            lock.write_text("99999999", encoding="ascii")
            with single_run_lock(lock):
                self.assertTrue(lock.exists())
            self.assertFalse(lock.exists())

    def _write_export(self, path: Path, player: str = "Player") -> None:
        pd.DataFrame([{
            "projection_id": "1", "league": "WNBA", "player_name": player,
            "team": "AAA", "stat_type": "Points", "line_score": 10.5,
            "odds_type": "standard", "start_time": "2026-07-13T20:00:00Z",
        }]).to_csv(path, index=False)

    def test_rejects_unrelated_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "unrelated.csv"
            pd.DataFrame({"a": [1]}).to_csv(path, index=False)
            self.assertFalse(valid_export(path))

    def test_finds_newest_valid_export(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            older, newer = root / "older.csv", root / "newer.csv"
            self._write_export(older, "Old")
            self._write_export(newer, "New")
            older.touch()
            newer.touch()
            newer_time = older.stat().st_mtime + 5
            import os
            os.utime(newer, (newer_time, newer_time))
            self.assertEqual(find_latest_export([root]), newer)

    def test_api_failure_uses_manual_export(self):
        with tempfile.TemporaryDirectory() as folder:
            export = Path(folder) / "pool.csv"
            self._write_export(export)
            with patch("src.automation.prizepicks_hourly.prizepicks.download_prizepicks_payload", side_effect=RuntimeError("403")), patch(
                "src.automation.prizepicks_hourly.find_latest_export", return_value=export
            ):
                raw, csv_path, rows, mode, error = acquire_pool()
            self.assertEqual((raw, csv_path, rows, mode), (export, export, 1, "MANUAL_EXPORT_FALLBACK"))
            self.assertIn("403", error)


if __name__ == "__main__":
    unittest.main()
