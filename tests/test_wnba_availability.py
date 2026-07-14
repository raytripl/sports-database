from __future__ import annotations

import unittest

from src.decisions.enrich_wnba_availability import (
    availability_flags,
    load_availability,
    optional_bool,
    replace_live_flag,
)
import tempfile
from pathlib import Path
import pandas as pd


class WnbaAvailabilityTests(unittest.TestCase):
    def test_boolean_normalization(self) -> None:
        self.assertEqual(optional_bool("yes"), 1)
        self.assertEqual(optional_bool("false"), 0)
        self.assertIsNone(optional_bool(None))

    def test_questionable_is_hard_veto(self) -> None:
        flags = availability_flags("QUESTIONABLE", 1, None)
        self.assertIn("HARD_VETO_QUESTIONABLE", flags)

    def test_restriction_is_hard_veto(self) -> None:
        flags = availability_flags("ACTIVE", 1, "20-25 minutes")
        self.assertIn("HARD_VETO_MINUTES_RESTRICTION", flags)

    def test_unconfirmed_lineup_is_hard_veto(self) -> None:
        flags = availability_flags("ACTIVE", 0, None)
        self.assertIn("HARD_VETO_UNCONFIRMED_LINEUP", flags)

    def test_live_flag_is_replaced_not_duplicated(self) -> None:
        existing = "Baseline only; LIVE_AVAILABILITY[HARD_VETO_OUT]"
        result = replace_live_flag(existing, ["HARD_VETO_QUESTIONABLE"])
        self.assertEqual(
            result,
            "Baseline only; LIVE_AVAILABILITY[HARD_VETO_QUESTIONABLE]",
        )

    def test_availability_file_is_validated_for_ingestion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "availability.csv"
            pd.DataFrame([{
                "player": "Temi Fagbenle", "team": "TOR", "injury_status": "OUT",
                "captured_at": "2026-07-14T14:45:00-05:00", "source": "WNBA official",
            }]).to_csv(path, index=False)
            result = load_availability(path)
            self.assertEqual(result.iloc[0]["injury_status"], "OUT")
            self.assertIn("lineup_confirmed", result.columns)


if __name__ == "__main__":
    unittest.main()
