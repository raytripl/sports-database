from __future__ import annotations

import unittest

import pandas as pd

from src.dna.wnba_role_stability import compare_role_stability


class RoleStabilityTests(unittest.TestCase):
    def test_low_sample_fails_closed(self) -> None:
        frame = pd.DataFrame([{
            "metric": "AST", "joint_absence_games": 2,
            "joint_absence_average": 8.0, "sample_flag": "LOW_SAMPLE",
        }])
        result = compare_role_stability(frame, "AST", 7.0)
        self.assertEqual(result["classification"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(result["recommendation_eligible"])

    def test_adequate_sample_is_descriptive_only(self) -> None:
        frame = pd.DataFrame([{
            "metric": "AST", "joint_absence_games": 3,
            "joint_absence_average": 8.33, "sample_flag": "OK",
        }])
        result = compare_role_stability(frame, "AST", 7.0)
        self.assertEqual(result["classification"], "ROLE_STABLE_SAMPLE")
        self.assertFalse(result["recommendation_eligible"])


if __name__ == "__main__":
    unittest.main()
