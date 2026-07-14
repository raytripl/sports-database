from __future__ import annotations

import pandas as pd


def compare_role_stability(
    joint_absence: pd.DataFrame,
    metric: str,
    line: float,
    minimum_games: int = 3,
) -> dict[str, object]:
    """Classify descriptive same-player stability without issuing a pick."""
    rows = joint_absence[joint_absence["metric"].eq(metric)]
    if len(rows) != 1:
        raise ValueError(f"Expected one joint-absence row for metric: {metric}")
    row = rows.iloc[0]
    games = int(row["joint_absence_games"])
    average = row["joint_absence_average"]
    fail_closed = games < minimum_games or pd.isna(average) or row["sample_flag"] != "OK"
    return {
        "metric": metric,
        "line": float(line),
        "joint_absence_games": games,
        "joint_absence_average": None if pd.isna(average) else float(average),
        "difference_from_line": None if pd.isna(average) else float(average) - float(line),
        "classification": "INSUFFICIENT_EVIDENCE" if fail_closed else "ROLE_STABLE_SAMPLE",
        "recommendation_eligible": False,
    }
