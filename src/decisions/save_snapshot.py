from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.db import connect
from src.decisions.schema import initialize_schema


DEFAULT_MODEL_VERSION = "v17.3"
DEFAULT_REVISION = "Evidence-Enforced Revision B"


COLUMN_ALIASES = {
    "player_name": "player",
    "name": "player",
    "stat_type": "prop_type",
    "market": "prop_type",
    "projection": "line",
    "line_score": "line",
    "prop_line": "line",
    "stat_value": "line",
    "value": "line",
    "pick": "direction",
    "side": "direction",
    "score": "model_score",
    "model_grade": "grade",
    "rank": "overall_rank",
}


def normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()

    result.columns = [
        str(column).strip().lower().replace(" ", "_").replace("/", "_")
        for column in result.columns
    ]

    result = result.rename(
        columns={
            source: target
            for source, target in COLUMN_ALIASES.items()
            if source in result.columns and target not in result.columns
        }
    )

    return result


def clean_text(value: object) -> str | None:
    if pd.isna(value):
        return None

    text = str(value).strip()
    return text or None


def clean_float(value: object) -> float | None:
    if pd.isna(value) or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clean_int(value: object) -> int | None:
    number = clean_float(value)
    return int(number) if number is not None else None


def clean_bool(value: object) -> int | None:
    if pd.isna(value) or value == "":
        return None

    if isinstance(value, bool):
        return int(value)

    text = str(value).strip().lower()

    if text in {"1", "true", "yes", "y", "confirmed"}:
        return 1

    if text in {"0", "false", "no", "n", "unconfirmed"}:
        return 0

    return None


def normalize_direction(value: object) -> str:
    text = clean_text(value)

    if text is None:
        return "PASS"

    normalized = text.upper()

    if normalized in {"O", "OVER", "MORE", "HIGHER"}:
        return "OVER"

    if normalized in {"U", "UNDER", "LESS", "LOWER"}:
        return "UNDER"

    if normalized in {"PASS", "AVOID", "FADE", "NEUTRAL"}:
        return normalized

    return normalized


def build_snapshot_id(
    slate_date: str,
    sport: str,
    source_file: Path,
) -> str:
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    raw = "|".join(
        [
            slate_date,
            sport.upper(),
            str(source_file.resolve()),
            created_at,
        ]
    )

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def required_columns_present(frame: pd.DataFrame) -> None:
    required = {"player", "prop_type", "line"}

    missing = sorted(required - set(frame.columns))

    if missing:
        raise ValueError(
            "Input pool is missing required columns: "
            + ", ".join(missing)
        )


def value_from_row(row: pd.Series, column: str) -> object:
    return row[column] if column in row.index else None


def save_snapshot(
    pool_path: Path,
    slate_date: str,
    sport: str,
    snapshot_id: str | None = None,
) -> tuple[str, int]:
    initialize_schema()

    if not pool_path.exists():
        raise FileNotFoundError(f"Pool file not found: {pool_path}")

    frame = pd.read_csv(pool_path)
    frame = normalize_columns(frame)

    required_columns_present(frame)

    resolved_snapshot_id = snapshot_id or build_snapshot_id(
        slate_date=slate_date,
        sport=sport,
        source_file=pool_path,
    )

    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    insert_columns = [
        "slate_date",
        "created_at",
        "sport",
        "game_id",
        "game_time",
        "game_description",
        "projection_type",
        "line_tier",
        "is_standard_line",
        "is_combo_prop",
        "player",
        "player_id",
        "team",
        "opponent",
        "prop_type",
        "line",
        "direction",
        "model_version",
        "operating_revision",
        "model_score",
        "grade",
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
        "source_pool_file",
        "snapshot_id",
    ]

    column_sql = ", ".join(insert_columns)
    placeholder_sql = ", ".join("?" for _ in insert_columns)

    insert_sql = (
        f"INSERT OR IGNORE INTO model_decisions "
        f"({column_sql}) VALUES ({placeholder_sql})"
    )

    inserted = 0

    with connect() as connection:
        connection.execute("PRAGMA foreign_keys = ON;")

        for _, row in frame.iterrows():
            player = clean_text(value_from_row(row, "player"))
            prop_type = clean_text(value_from_row(row, "prop_type"))
            line = clean_float(value_from_row(row, "line"))

            if not player or not prop_type or line is None:
                continue

            values = (
                slate_date,
                created_at,
                sport.upper(),
                clean_text(value_from_row(row, "game_id")),
                clean_text(value_from_row(row, "game_time")),
                clean_text(value_from_row(row, "game_description")),
                clean_text(value_from_row(row, "projection_type")),
                clean_text(value_from_row(row, "line_tier")),
                clean_bool(value_from_row(row, "is_standard_line")) or 0,
                1 if "+" in player else 0,
                player,
                clean_text(value_from_row(row, "player_id")),
                clean_text(value_from_row(row, "team")),
                clean_text(value_from_row(row, "opponent")),
                prop_type,
                line,
                normalize_direction(value_from_row(row, "direction")),
                clean_text(value_from_row(row, "model_version"))
                or DEFAULT_MODEL_VERSION,
                clean_text(value_from_row(row, "operating_revision"))
                or DEFAULT_REVISION,
                clean_float(value_from_row(row, "model_score")),
                clean_text(value_from_row(row, "grade")),
                clean_int(value_from_row(row, "overall_rank")),
                clean_int(value_from_row(row, "same_player_rank")),
                clean_float(value_from_row(row, "opportunity_score")),
                clean_float(value_from_row(row, "suppression_score")),
                clean_float(value_from_row(row, "matchup_score")),
                clean_float(value_from_row(row, "skill_score")),
                clean_float(value_from_row(row, "role_score")),
                clean_float(value_from_row(row, "workload_score")),
                clean_float(value_from_row(row, "coach_score")),
                clean_float(value_from_row(row, "manager_score")),
                clean_float(value_from_row(row, "ceiling_risk_score")),
                clean_float(value_from_row(row, "line_value_score")),
                clean_float(value_from_row(row, "evidence_agreement_score")),
                clean_bool(value_from_row(row, "recommended")) or 0,
                clean_text(value_from_row(row, "entry_type")),
                clean_bool(value_from_row(row, "lineup_confirmed")),
                clean_int(value_from_row(row, "batting_order")),
                clean_bool(value_from_row(row, "starter_confirmed")),
                clean_text(value_from_row(row, "injury_status")),
                clean_text(value_from_row(row, "minutes_restriction")),
                clean_float(value_from_row(row, "expected_minutes")),
                clean_float(value_from_row(row, "expected_plate_appearances")),
                clean_float(value_from_row(row, "expected_innings")),
                clean_float(value_from_row(row, "expected_pitch_count")),
                clean_float(value_from_row(row, "opponent_k_percent")),
                clean_float(
                    value_from_row(row, "opponent_k_percent_vs_hand")
                ),
                clean_float(
                    value_from_row(row, "confirmed_lineup_k_percent")
                ),
                clean_text(value_from_row(row, "over_reason")),
                clean_text(value_from_row(row, "under_reason")),
                clean_text(value_from_row(row, "red_flags")),
                clean_text(value_from_row(row, "decision_reason")),
                str(pool_path),
                resolved_snapshot_id,
            )

            cursor = connection.execute(insert_sql, values)

            if cursor.rowcount == 1:
                inserted += 1

    return resolved_snapshot_id, inserted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Save a pregame Model Decision Log snapshot."
    )

    parser.add_argument(
        "--pool",
        required=True,
        type=Path,
        help="Path to the processed PrizePicks pool CSV.",
    )

    parser.add_argument(
        "--date",
        required=True,
        help="Slate date in YYYY-MM-DD format.",
    )

    parser.add_argument(
        "--sport",
        required=True,
        help="Sport code such as MLB or WNBA.",
    )

    parser.add_argument(
        "--snapshot-id",
        help="Optional fixed snapshot ID.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    snapshot_id, inserted = save_snapshot(
        pool_path=args.pool,
        slate_date=args.date,
        sport=args.sport,
        snapshot_id=args.snapshot_id,
    )

    print("=" * 70)
    print("MODEL DECISION LOG")
    print("=" * 70)
    print(f"Snapshot ID: {snapshot_id}")
    print(f"Rows inserted: {inserted:,}")
    print(f"Pool: {args.pool}")


if __name__ == "__main__":
    main()
