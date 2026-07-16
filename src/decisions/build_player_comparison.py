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
        return pd.Series(default, index=frame.index, dtype="float64")

    return pd.to_numeric(
        frame[column],
        errors="coerce",
    ).fillna(default)


def text(
    frame: pd.DataFrame,
    column: str,
    default: str = "",
) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype="object")

    return frame[column].fillna(default).astype(str)


def build_player_comparison(
    source: Path,
    output: Path,
) -> int:
    if not source.exists():
        raise FileNotFoundError(f"Decision board not found: {source}")

    board = pd.read_csv(source).copy()

    decision_strength = numeric(board, "decision_strength")
    direction_gap = numeric(board, "direction_gap")
    opportunity = numeric(board, "opportunity_score", 50.0).clip(0, 100)
    matchup = numeric(board, "matchup_score", 50.0).clip(0, 100)
    line_value = numeric(board, "line_value_score", 50.0).clip(0, 100)
    evidence = numeric(
        board,
        "evidence_agreement_score",
        50.0,
    ).clip(0, 100)
    risk = numeric(board, "ceiling_risk_score", 50.0).clip(0, 100)

    model_direction = text(
        board,
        "model_direction",
    ).str.strip().str.upper()

    directional_matchup = matchup.copy()
    under_rows = model_direction.eq("UNDER")

    directional_matchup.loc[under_rows] = (
        100.0 - matchup.loc[under_rows]
    )

    board["player_comparison_score"] = (
        decision_strength * 0.45
        + direction_gap.clip(upper=50.0) / 50.0 * 15.0
        + opportunity * 0.15
        + directional_matchup * 0.10
        + line_value * 0.05
        + evidence * 0.05
        + (100.0 - risk) * 0.05
    ).clip(0, 100).round(1)

    board["player_prop_rank"] = (
        board.groupby("player")["player_comparison_score"]
        .rank(method="first", ascending=False)
        .astype("Int64")
    )

    board["best_player_prop"] = (
        board["player_prop_rank"].eq(1).astype(int)
    )

    board["player_prop_count"] = (
        board.groupby("player")["player"]
        .transform("count")
        .astype(int)
    )

    best_score = (
        board.groupby("player")["player_comparison_score"]
        .transform("max")
    )

    board["player_score_gap_to_best"] = (
        best_score - board["player_comparison_score"]
    ).round(1)

    board["player_comparison_label"] = "ALTERNATIVE_PROP"

    board.loc[
        board["best_player_prop"].eq(1),
        "player_comparison_label",
    ] = "BEST_PLAYER_PROP"

    board["player_comparison_reason"] = (
        "LOWER_COMPOSITE_SCORE_THAN_PLAYER_BEST"
    )

    board.loc[
        board["best_player_prop"].eq(1),
        "player_comparison_reason",
    ] = "HIGHEST_COMPOSITE_PROP_SCORE"

    board["player_comparison_mode"] = "RESEARCH_ONLY"

    preferred = [
        "player",
        "team",
        "opponent",
        "prop_type",
        "line",
        "model_direction",
        "decision_strength",
        "direction_gap",
        "decision_confidence",
        "player_comparison_score",
        "player_prop_rank",
        "best_player_prop",
        "player_prop_count",
        "player_score_gap_to_best",
        "player_comparison_label",
        "player_comparison_reason",
        "opportunity_score",
        "matchup_score",
        "line_value_score",
        "evidence_agreement_score",
        "ceiling_risk_score",
        "over_score",
        "under_score",
        "final_selection",
        "pick_level",
        "eligibility_status",
        "exclusion_reason",
        "player_comparison_mode",
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

    board = board.sort_values(
        [
            "best_player_prop",
            "player_comparison_score",
            "direction_gap",
        ],
        ascending=[False, False, False],
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    board.to_csv(output, index=False)

    return len(board)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare each player's available props."
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    rows = build_player_comparison(
        source=args.source,
        output=args.output,
    )

    print("=" * 72)
    print("SPORTS HUB PLAYER COMPARISON ENGINE")
    print("=" * 72)
    print(f"Rows: {rows:,}")
    print(f"Saved: {args.output}")
    print("Mode: RESEARCH ONLY")
    print("v22-control fields were not modified.")


if __name__ == "__main__":
    main()
