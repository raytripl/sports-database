from __future__ import annotations

import unittest

import pandas as pd

from src.decisions.enrich_mlb_k_context import (
    confirmed_lineup_k_rate,
    extract_stat,
    k_rate,
    replace_k_flags,
)


class MlbKContextTests(unittest.TestCase):
    def test_extracts_official_team_k_rate(self):
        payload = {"stats": [{"splits": [{"stat": {"plateAppearances": 400, "strikeOuts": 100}}]}]}
        self.assertEqual(k_rate(extract_stat(payload)), (25.0, 400))

    def test_confirmed_lineup_uses_only_nine_live_hitters(self):
        live = pd.DataFrame({
            "player": [f"Hitter {i}" for i in range(9)] + ["Bench"],
            "player_role": ["HITTER"] * 10,
            "team": ["NYY"] * 10,
            "lineup_confirmed": [1] * 9 + [0],
        })
        history = pd.DataFrame({
            "PLAYER_NAME": [f"Hitter {i}" for i in range(9)] + ["Bench"],
            "PLAYER_TYPE": ["HITTER"] * 10,
            "PA": [10] * 10,
            "SO": [2] * 9 + [10],
        })
        rate, pa, count = confirmed_lineup_k_rate(live, history, "NYY")
        self.assertEqual((rate, pa, count), (20.0, 90, 9))

    def test_legacy_veto_clears_only_when_verified(self):
        existing = "Baseline; MLB_LIVE[HARD_VETO_K_RATE_NOT_VERIFIED]"
        result = replace_k_flags(existing, [], True)
        self.assertNotIn("K_RATE_NOT_VERIFIED", result)
        self.assertIn("MLB_K[VERIFIED]", result)

    def test_missing_sample_preserves_hard_veto(self):
        result = replace_k_flags("Baseline", ["HARD_VETO_LOW_HANDED_K_SAMPLE"], False)
        self.assertIn("HARD_VETO_LOW_HANDED_K_SAMPLE", result)


if __name__ == "__main__":
    unittest.main()
