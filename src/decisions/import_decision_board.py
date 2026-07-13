from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.db import connect


UPDATABLE_COLUMNS = [
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


def normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result.columns = [
        str(column).strip().lower().replace(" ", "_").replace("/", "_")
        for column in result.columns
    ]
    return result


def clean_value(value: object) -> object:
    if pd.isna(value):
        return None

    if isinstance(value, str):
        text = value.strip()
        return text if text else None

    return value


def normalize_direction(value: object) -> str | None:
    cleaned = clean_value(value)

    if cleaned is None:
        return None

    text = str(cleaned).upper()

    aliases = {
        "O": "OVER",
        "MORE": "OVER",
        "HIGHER": "OVER",
        "U": "UNDER",
        "LESS": "UNDER",
        "LOWER": "UNDER",
    }

    return aliases.get(text, text)


def normalize_recommended(value: object) -> int:
    cleaned = clean_value(value)

    if cleaned is None:
        return 0

    if isinstance(cleaned, bool):
        return int(cleaned)

    text = str(cleaned).strip().lower()

    if text in {"1", "true", "yes", "y"}:
        return 1

    return 0


def import_board(board_path: Path) -> tuple[int, int]:
    if not board_path.exists():
        raise FileNotFoundError(f"Decision board not found: {board_path}")

    frame = normalize_columns(pd.read_csv(board_path))

    if "decision_id" not in frame.columns:
        raise ValueError("Decision board is missing decision_id.")

    missing = [
        column
        for column in UPDATABLE_COLUMNS
        if column not in frame.columns
    ]

    if missing:
        raise ValueError(
            "Decision board is missing columns: " + ", ".join(missing)
        )

    assignments = ", ".join(
        f"{column} = ?"
        for column in UPDATABLE_COLUMNS
    )

    sql = f"""
    UPDATE model_decisions
    SET {assignments}
    WHERE decision_id = ?
    """

    updated = 0
    skipped = 0

    with connect() as connection:
        for _, row in frame.iterrows():
            decision_id = clean_value(row["decision_id"])

            if decision_id is None:
                skipped += 1
                continue

            values = []

            for column in UPDATABLE_COLUMNS:
                value = row[column]

                if column == "direction":
                    value = normalize_direction(value)

                elif column == "recommended":
                    value = normalize_recommended(value)

                else:
                    value = clean_value(value)

                values.append(value)

            values.append(int(decision_id))

            cursor = connection.execute(sql, values)

            if cursor.rowcount == 1:
                updated += 1
            else:
                skipped += 1

    return updated, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a completed Raymond decision board."
    )

    parser.add_argument(
        "--board",
        required=True,
        type=Path,
        help="Completed decision board CSV.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    updated, skipped = import_board(args.board)

    print("=" * 70)
    print("DECISION BOARD IMPORT")
    print("=" * 70)
    print(f"Updated: {updated:,}")
    print(f"Skipped: {skipped:,}")
    print(f"Board: {args.board}")


if __name__ == "__main__":
    main()
