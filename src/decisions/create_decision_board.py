from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.db import connect


DECISION_COLUMNS = [
    "decision_id",
    "snapshot_id",
    "slate_date",
    "sport",
    "player",
    "team",
    "opponent",
    "prop_type",
    "line",
    "direction",
    "grade",
    "model_score",
    "overall_rank",
    "same_player_rank",
    "opportunity_score",
    "suppression_score",
    "matchup_score",
    "skill_score",
    "role_score",
    "workload_score",
    "coach_score",
    "manager_score",
    "ceiling_risk_score",
    "line_value_score",
    "evidence_agreement_score",
    "recommended",
    "entry_type",
    "lineup_confirmed",
    "batting_order",
    "starter_confirmed",
    "injury_status",
    "minutes_restriction",
    "expected_minutes",
    "expected_plate_appearances",
    "expected_innings",
    "expected_pitch_count",
    "opponent_k_percent",
    "opponent_k_percent_vs_hand",
    "confirmed_lineup_k_percent",
    "over_reason",
    "under_reason",
    "red_flags",
    "decision_reason",
]


def load_snapshot(snapshot_id: str) -> pd.DataFrame:
    query = """
    SELECT
        decision_id,
        snapshot_id,
        slate_date,
        sport,
        player,
        team,
        opponent,
        prop_type,
        line,
        direction,
        grade,
        model_score,
        overall_rank,
        same_player_rank,
        opportunity_score,
        suppression_score,
        matchup_score,
        skill_score,
        role_score,
        workload_score,
        coach_score,
        manager_score,
        ceiling_risk_score,
        line_value_score,
        evidence_agreement_score,
        recommended,
        entry_type,
        lineup_confirmed,
        batting_order,
        starter_confirmed,
        injury_status,
        minutes_restriction,
        expected_minutes,
        expected_plate_appearances,
        expected_innings,
        expected_pitch_count,
        opponent_k_percent,
        opponent_k_percent_vs_hand,
        confirmed_lineup_k_percent,
        over_reason,
        under_reason,
        red_flags,
        decision_reason
    FROM model_decisions
    WHERE snapshot_id = ?
      AND is_standard_line = 1
      AND is_combo_prop = 0
    ORDER BY player, prop_type, line
    """

    with connect() as connection:
        frame = pd.read_sql_query(
            query,
            connection,
            params=(snapshot_id,),
        )

    if frame.empty:
        raise ValueError(f"No rows found for snapshot: {snapshot_id}")

    return frame


def create_board(snapshot_id: str, output_path: Path) -> int:
    frame = load_snapshot(snapshot_id)

    frame = frame[DECISION_COLUMNS].copy()

    # These fields must be filled by the Raymond Model before lock.
    text_columns = [
        "direction",
        "grade",
        "entry_type",
        "over_reason",
        "under_reason",
        "red_flags",
        "decision_reason",
    ]

    for column in text_columns:
        frame[column] = pd.Series(
            [""] * len(frame),
            dtype="object",
        )

    numeric_columns = [
        "model_score",
        "overall_rank",
        "same_player_rank",
        "opportunity_score",
        "suppression_score",
        "matchup_score",
        "skill_score",
        "role_score",
        "workload_score",
        "coach_score",
        "manager_score",
        "ceiling_risk_score",
        "line_value_score",
        "evidence_agreement_score",
    ]

    for column in numeric_columns:
        frame[column] = pd.NA

    frame["recommended"] = 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)

    return len(frame)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a Raymond Model decision board."
    )

    parser.add_argument(
        "--snapshot-id",
        required=True,
        help="Snapshot ID stored in model_decisions.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output CSV path.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    row_count = create_board(
        snapshot_id=args.snapshot_id,
        output_path=args.output,
    )

    print("=" * 70)
    print("RAYMOND DECISION BOARD")
    print("=" * 70)
    print(f"Snapshot: {args.snapshot_id}")
    print(f"Rows: {row_count:,}")
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
