from __future__ import annotations

import unittest

import pandas as pd

from src.markets.line_movement import calculate_standard_movement


class LineMovementTests(unittest.TestCase):
    def test_only_standard_lines_are_compared(self) -> None:
        common = {"slate_date": "2026-07-14", "sport": "WNBA", "player": "Guard", "prop_type": "Points"}
        frame = pd.DataFrame([
            common | {"captured_at": "2026-07-14T10:00:00Z", "line": 18, "is_standard_line": 1},
            common | {"captured_at": "2026-07-14T11:00:00Z", "line": 13.5, "is_standard_line": 0},
            common | {"captured_at": "2026-07-14T12:00:00Z", "line": 19, "is_standard_line": 1},
        ])
        result = calculate_standard_movement(frame).iloc[0]
        self.assertEqual(result["opening_standard_line"], 18)
        self.assertEqual(result["current_standard_line"], 19)
        self.assertEqual(result["absolute_movement"], 1)

    def test_no_standard_lines_fails_closed(self) -> None:
        frame = pd.DataFrame([{
            "captured_at": "2026-07-14T10:00:00Z", "slate_date": "2026-07-14",
            "sport": "WNBA", "player": "Guard", "prop_type": "Points",
            "line": 13.5, "is_standard_line": 0,
        }])
        self.assertTrue(calculate_standard_movement(frame).empty)


if __name__ == "__main__":
    unittest.main()
