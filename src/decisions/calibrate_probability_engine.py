from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_BUCKETS = [
    (0.50, 0.60, "50-60"),
    (0.60, 0.70, "60-70"),
    (0.70, 0.80, "70-80"),
    (0.80, 0.90, "80-90"),
    (0.90, 1.01, "90-100"),
]

MIN_BUCKET_ROWS = 10


def probability_bucket(value: float) -> str:
    for lower, upper, label in DEFAULT_BUCKETS:
        if lower <= value < upper:
            return label

    return "OUT_OF_RANGE"


def build_calibration_table(
    probability_board: pd.DataFrame,
    audit: pd.DataFrame,
) -> pd.DataFrame:
    keys = ["player", "prop_type", "line"]

    merged = probability_board.merge(
        audit[
            keys
            + [
                "audit_status",
                "actual_value",
                "directional_margin",
            ]
        ],
        on=keys,
        how="left",
    )

    resolved = merged[
        merged["audit_status"].isin(["HIT", "MISS"])
    ].copy()

    resolved["actual_hit"] = (
        resolved["audit_status"].eq("HIT").astype(int)
    )

    resolved["calibration_bucket"] = (
        resolved["selected_probability"]
        .astype(float)
        .map(probability_bucket)
    )

    calibration = (
        resolved.groupby(
            "calibration_bucket",
            dropna=False,
        )
        .agg(
            historical_rows=("actual_hit", "size"),
            raw_probability_mean=(
                "selected_probability",
                "mean",
            ),
            historical_hit_rate=("actual_hit", "mean"),
        )
        .reset_index()
    )

    calibration["calibration_status"] = "INSUFFICIENT_DATA"

    calibration.loc[
        calibration["historical_rows"].ge(MIN_BUCKET_ROWS),
        "calibration_status",
    ] = "USABLE_RESEARCH_ONLY"

    return calibration


def calibrate_board(
    probability_board: pd.DataFrame,
    calibration: pd.DataFrame,
) -> pd.DataFrame:
    board = probability_board.copy()

    board["calibration_bucket"] = (
        board["selected_probability"]
        .astype(float)
        .map(probability_bucket)
    )

    board = board.merge(
        calibration,
        on="calibration_bucket",
        how="left",
    )

    board["raw_probability"] = (
        board["selected_probability"]
    )

    board["calibrated_probability"] = (
        board["historical_hit_rate"]
    )

    insufficient = (
        board["historical_rows"].fillna(0)
        .lt(MIN_BUCKET_ROWS)
    )

    board.loc[
        insufficient,
        "calibrated_probability",
    ] = 0.50

    board["calibrated_probability"] = (
        board["calibrated_probability"]
        .clip(0.0, 1.0)
        .round(4)
    )

    board["calibrated_edge"] = (
        board["calibrated_probability"] - 0.50
    ).round(4)

    board["calibrated_edge_percent"] = (
        board["calibrated_edge"] * 100.0
    ).round(2)

    board["calibrated_rank"] = (
        board["calibrated_probability"]
        .rank(
            method="first",
            ascending=False,
        )
        .astype("Int64")
    )

    board["calibration_engine_mode"] = "RESEARCH_ONLY"
    board["production_fields_unchanged"] = 1

    preferred = [
        "calibrated_rank",
        "probability_rank",
        "player",
        "team",
        "opponent",
        "prop_type",
        "line",
        "path_direction",
        "selection_path",
        "raw_probability",
        "calibrated_probability",
        "calibrated_edge",
        "calibrated_edge_percent",
        "calibration_bucket",
        "historical_rows",
        "historical_hit_rate",
        "calibration_status",
        "player_comparison_score",
        "decision_strength",
        "direction_gap",
        "final_selection",
        "exclusion_reason",
        "calibration_engine_mode",
        "production_fields_unchanged",
    ]

    remaining = [
        column
        for column in board.columns
        if column not in preferred
    ]

    board = board[
        [column for column in preferred if column in board.columns]
        + remaining
    ]

    return board.sort_values(
        [
            "calibrated_probability",
            "raw_probability",
        ],
        ascending=[False, False],
    )


def run_calibration(
    probability_path: Path,
    audit_path: Path,
    output_path: Path,
    calibration_output_path: Path,
) -> tuple[int, int]:
    if not probability_path.exists():
        raise FileNotFoundError(
            f"Probability board not found: {probability_path}"
        )

    if not audit_path.exists():
        raise FileNotFoundError(
            f"Audit file not found: {audit_path}"
        )

    probability_board = pd.read_csv(probability_path)
    audit = pd.read_csv(audit_path)

    calibration = build_calibration_table(
        probability_board,
        audit,
    )

    calibrated_board = calibrate_board(
        probability_board,
        calibration,
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    calibration_output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    calibrated_board.to_csv(
        output_path,
        index=False,
    )

    calibration.to_csv(
        calibration_output_path,
        index=False,
    )

    return len(calibrated_board), len(calibration)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Calibrate provisional probabilities "
            "using completed-slate results."
        )
    )

    parser.add_argument(
        "--probabilities",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--audit",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--calibration-output",
        required=True,
        type=Path,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    rows, buckets = run_calibration(
        probability_path=args.probabilities,
        audit_path=args.audit,
        output_path=args.output,
        calibration_output_path=args.calibration_output,
    )

    print("=" * 72)
    print("SPORTS HUB PROBABILITY CALIBRATION")
    print("=" * 72)
    print(f"Rows: {rows:,}")
    print(f"Calibration buckets: {buckets}")
    print(f"Saved board: {args.output}")
    print(f"Saved calibration: {args.calibration_output}")
    print("Mode: RESEARCH ONLY")
    print("v22-control fields were not modified.")


if __name__ == "__main__":
    main()
