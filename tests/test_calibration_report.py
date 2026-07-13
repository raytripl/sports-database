import unittest

import pandas as pd

from src.audits.calibration_report import (
    calibration_gates,
    closing_decisions,
    grade_ordering_status,
    grouped_performance,
    opportunity_class,
)


class CalibrationReportTests(unittest.TestCase):
    def test_closing_decisions_remove_hourly_duplicates_and_line_moves(self):
        frame = pd.DataFrame([
            {"decision_id": 1, "created_at": "2026-07-13T10:00:00Z", "slate_date": "2026-07-13", "sport": "WNBA", "game_id": "1", "player": "A", "opponent": "B", "prop_type": "Points", "line": 10.5, "model_score": 70},
            {"decision_id": 2, "created_at": "2026-07-13T12:00:00Z", "slate_date": "2026-07-13", "sport": "WNBA", "game_id": "1", "player": "A", "opponent": "B", "prop_type": "Points", "line": 11.5, "model_score": 72},
        ])
        result = closing_decisions(frame)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["decision_id"], 2)

    def test_hit_rate_excludes_pushes_and_passes(self):
        frame = pd.DataFrame([
            {"sport": "WNBA", "direction": "OVER", "status": "HIT", "margin": 2},
            {"sport": "WNBA", "direction": "UNDER", "status": "MISS", "margin": 1},
            {"sport": "WNBA", "direction": "OVER", "status": "PUSH", "margin": 0},
            {"sport": "WNBA", "direction": "PASS", "status": "PASS", "margin": 5},
        ])
        report = grouped_performance(frame, ["sport"])
        self.assertEqual(report.iloc[0]["resolved_directional"], 3)
        self.assertEqual(report.iloc[0]["hit_rate"], 0.5)
        self.assertEqual(report.iloc[0]["passes"], 1)

    def test_grade_inversion_is_detected(self):
        report = pd.DataFrame([
            {"grade": "B+", "resolved_directional": 30, "hit_rate": 0.48},
            {"grade": "B", "resolved_directional": 30, "hit_rate": 0.55},
        ])
        result = grade_ordering_status(report)
        self.assertEqual(result["status"], "NOT_ORDERED")
        self.assertEqual(len(result["violations"]), 1)

    def test_low_samples_do_not_validate_grade_ordering(self):
        report = pd.DataFrame([
            {"grade": "B+", "resolved_directional": 10, "hit_rate": 0.7},
            {"grade": "B", "resolved_directional": 10, "hit_rate": 0.5},
        ])
        self.assertEqual(grade_ordering_status(report)["status"], "INSUFFICIENT_DATA")

    def test_calibration_cannot_enable_recommendations(self):
        frame = pd.DataFrame(columns=["direction", "status", "slate_date", "sport"])
        grades = pd.DataFrame(columns=["grade", "resolved_directional", "hit_rate"])
        gates = calibration_gates(frame, grades)
        self.assertEqual(gates["status"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(gates["recommendations_enabled"])
        self.assertFalse(gates["weights_changed"])

    def test_opportunity_class_is_sport_specific(self):
        self.assertEqual(opportunity_class("WNBA", "FG Attempts"), "OPPORTUNITY")
        self.assertEqual(opportunity_class("WNBA", "Points"), "RESULT")
        self.assertEqual(opportunity_class("MLB", "Total Pitches"), "OPPORTUNITY")
        self.assertEqual(opportunity_class("MLB", "Hitter Fantasy Score"), "RESULT")


if __name__ == "__main__":
    unittest.main()
