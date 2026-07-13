from __future__ import annotations

import unittest

import pandas as pd

from src.decisions.save_snapshot import filter_to_slate_date


class SnapshotSlateFilterTests(unittest.TestCase):
    def test_mixed_pool_is_filtered(self) -> None:
        frame = pd.DataFrame(
            {
                "slate_date": ["2026-07-13", "2026-07-14"],
                "player": ["Today", "Tomorrow"],
            }
        )
        result = filter_to_slate_date(frame, "2026-07-13")
        self.assertEqual(result["player"].tolist(), ["Today"])

    def test_missing_requested_date_is_rejected(self) -> None:
        frame = pd.DataFrame({"slate_date": ["2026-07-14"]})
        with self.assertRaises(ValueError):
            filter_to_slate_date(frame, "2026-07-13")

    def test_legacy_pool_without_date_is_preserved(self) -> None:
        frame = pd.DataFrame({"player": ["One", "Two"]})
        self.assertEqual(len(filter_to_slate_date(frame, "2026-07-13")), 2)


if __name__ == "__main__":
    unittest.main()
