from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.pipelines.wnba_daily import run_pipeline


class WnbaDailyPipelineTests(unittest.TestCase):
    def test_pipeline_runs_in_guarded_order_and_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pool = root / "pool.csv"
            history = root / "history.csv"
            pool.write_text("placeholder", encoding="utf-8")
            history.write_text("placeholder", encoding="utf-8")

            calls: list[str] = []

            with (
                patch("src.pipelines.wnba_daily.save_snapshot",
                      side_effect=lambda **kwargs: ("snapshot", 10)),
                patch("src.pipelines.wnba_daily.capture",
                      side_effect=lambda *args: calls.append("capture") or {"pool_rows": 10}),
                patch("src.pipelines.wnba_daily.create_board",
                      side_effect=lambda *args: calls.append("board") or 4),
                patch("src.pipelines.wnba_daily.score_board",
                      side_effect=lambda *args: calls.append("score") or 4),
                patch("src.pipelines.wnba_daily.import_board",
                      side_effect=lambda *args: calls.append("import") or (4, 0)),
            ):
                result = run_pipeline(
                    pool, "2026-07-13", history, root / "out"
                )

            self.assertEqual(calls, ["capture", "board", "score", "import"])
            self.assertEqual(result["decision_board_rows"], 4)
            self.assertFalse(result["recommendations_enabled"])
            manifest = json.loads(Path(result["manifest_path"]).read_text())
            self.assertEqual(manifest["model_version"], "v17.3")
            self.assertEqual(manifest["baseline_grade_cap"], "B+")

    def test_missing_availability_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pool = root / "pool.csv"
            history = root / "history.csv"
            pool.touch()
            history.touch()
            with self.assertRaises(FileNotFoundError):
                run_pipeline(
                    pool,
                    "2026-07-13",
                    history,
                    root / "out",
                    availability_path=root / "missing.csv",
                )


if __name__ == "__main__":
    unittest.main()
