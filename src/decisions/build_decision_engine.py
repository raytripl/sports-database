from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def numeric(
    frame: pd.DataFrame,
    column: str,
    default: float = 0.0,
) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(
            default,
            index=frame.index,
            dtype="float64",
        )

    return pd.to_numeric(
        frame[column],
        errors="coerce",
    ).fillna(default)


def confidence_label(gap: float) -> str:
    if gap >= 25:
        return "HIGH"

    if gap >= 12:
        return "MEDIUM"

    return "LOW"


def build_decision_engine(
    source: Path,
    output: Path,
) -> int:
    if not source.exists():
        raise FileNotFoundError(
            f"Scored board not found: {source}"
        )

    board = pd.read_csv(source).copy()

    over_score = numeric(board, "over_score")
    under_score = numeric(board, "under_score")

    board["model_direction"] = "OVER"

    board.loc[
        under_score > over_score,
        "model_direction",
    ] = "UNDER"

    board["direction_gap"] = (
        over_score - under_score
    ).abs().round(1)

    board["decision_strength"] = pd.concat(
        [over_score, under_score],
        axis=1,
    ).max(axis=1).round(1)

    board["decision_confidence"] = (
        board["direction_gap"]
        .map(confidence_label)
    )

    board["same_player_decision_rank"] = (
        board.groupby("player")["decision_strength"]
        .rank(
            method="first",
            ascending=False,
        )
        .astype("Int64")
    )

    board["best_decision_prop_for_player"] = (
        board["same_player_decision_rank"]
        .eq(1)
        .astype(int)
    )

    board["decision_engine_label"] = "RESEARCH_ONLY"
    board["production_fields_unchanged"] = 1

    preferred = [
        "player",
        "team",
        "opponent",
        "prop_type",
        "line",
        "model_direction",
        "direction_gap",
        "decision_strength",
        "decision_confidence",
        "same_player_decision_rank",
        "best_decision_prop_for_player",
        "over_score",
        "under_score",
        "model_score",
        "opportunity_score",
        "matchup_score",
        "final_selection",
        "pick_level",
        "eligibility_status",
        "exclusion_reason",
        "decision_engine_label",
        "production_fields_unchanged",
    ]

    remaining = [
        column
        for column in board.columns
        if column not in preferred
    ]

    board = board[
        [
            column
            for column in preferred
            if column in board.columns
        ]
        + remaining
    ]

    board = board.sort_values(
        [
            "decision_strength",
            "direction_gap",
        ],
        ascending=[False, False],
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    board.to_csv(
        output,
        index=False,
    )

    return len(board)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a research-only decision engine board."
        )
    )

    parser.add_argument(
        "--source",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    rows = build_decision_engine(
        source=args.source,
        output=args.output,
    )

    print("=" * 72)
    print("SPORTS HUB DECISION ENGINE")
    print("=" * 72)
    print(f"Rows: {rows:,}")
    print(f"Saved: {args.output}")
    print("Mode: RESEARCH ONLY")
    print("v22-control fields were not modified.")


if __name__ == "__main__":
    main()
