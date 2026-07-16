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


def confidence_label(score: float) -> str:
    if score >= 90:
        return "VERY_HIGH_RESEARCH"

    if score >= 85:
        return "HIGH_RESEARCH"

    if score >= 80:
        return "MEDIUM_RESEARCH"

    if score >= 75:
        return "LEAN_RESEARCH"

    return "PASS"


def build_positive_reasons(row: pd.Series) -> str:
    reasons: list[str] = []

    if float(row["opportunity_component"]) >= 80:
        reasons.append("STRONG_OPPORTUNITY")

    if float(row["directional_matchup_component"]) >= 70:
        reasons.append("MATCHUP_SUPPORT")

    if float(row["statistical_edge_component"]) >= 80:
        reasons.append("STRONG_STATISTICAL_EDGE")

    if float(row["line_value_component"]) >= 70:
        reasons.append("LINE_VALUE_SUPPORT")

    if float(row["data_quality_component"]) >= 75:
        reasons.append("GOOD_DATA_QUALITY")

    if float(row.get("research_direction_gap", 0) or 0) >= 15:
        reasons.append("CLEAR_DIRECTIONAL_SEPARATION")

    return "|".join(reasons) if reasons else "NO_MAJOR_POSITIVE_SIGNAL"


def build_negative_reasons(row: pd.Series) -> str:
    reasons: list[str] = []

    if float(row.get("sample_size", 0) or 0) < 5:
        reasons.append("SMALL_HISTORY_SAMPLE")

    if float(row.get("team_matchup_sample_size", 0) or 0) < 5:
        reasons.append("SMALL_MATCHUP_SAMPLE")

    if float(row.get("data_quality", 0) or 0) < 50:
        reasons.append("LOW_DATA_QUALITY")

    if float(row.get("research_direction_gap", 0) or 0) < 7:
        reasons.append("NARROW_DIRECTION_GAP")

    if str(row.get("slate_risk_status", "")).upper() == "QUARANTINE":
        reasons.append("PRODUCTION_SLATE_QUARANTINE")

    if str(row.get("injury_status", "")).upper() not in {
        "ACTIVE",
        "PROBABLE",
    }:
        reasons.append("LIVE_STATUS_NOT_CLEARED")

    if pd.isna(row.get("expected_minutes")):
        reasons.append("EXPECTED_MINUTES_MISSING")

    return "|".join(reasons) if reasons else "NO_MAJOR_RESEARCH_RED_FLAG"


def build_research_board(source: Path, output: Path) -> int:
    board = pd.read_csv(source)

    over_score = numeric(board, "over_score")
    under_score = numeric(board, "under_score")
    opportunity = numeric(board, "opportunity_score", 50.0).clip(0, 100)
    matchup = numeric(board, "matchup_score", 50.0).clip(0, 100)
    line_value = numeric(board, "line_value_score", 50.0).clip(0, 100)
    data_quality = numeric(board, "data_quality", 0.0).clip(0, 100)

    board["statistical_edge_component"] = pd.concat(
        [over_score, under_score],
        axis=1,
    ).max(axis=1).round(1)

    board["opportunity_component"] = opportunity.round(1)

    board["directional_matchup_component"] = matchup.copy()

    under_rows = text(
        board,
        "research_direction",
    ).str.upper().eq("UNDER")

    board.loc[
        under_rows,
        "directional_matchup_component",
    ] = 100 - matchup.loc[under_rows]

    board["directional_matchup_component"] = (
        board["directional_matchup_component"]
        .clip(0, 100)
        .round(1)
    )

    board["line_value_component"] = line_value.round(1)
    board["data_quality_component"] = data_quality.round(1)

    board["research_confidence"] = numeric(
        board,
        "research_score",
    ).map(confidence_label)

    board["research_why"] = board.apply(
        build_positive_reasons,
        axis=1,
    )

    board["research_why_not"] = board.apply(
        build_negative_reasons,
        axis=1,
    )

    board["best_prop_for_player"] = 0

    same_player_rank = numeric(
        board,
        "research_same_player_rank",
        999,
    )

    board.loc[
        same_player_rank.eq(1),
        "best_prop_for_player",
    ] = 1

    board["production_status"] = "DISABLED_OR_EXCLUDED"

    pick_level = text(board, "pick_level").str.upper()

    board.loc[
        pick_level.isin(["PRIMARY", "SECONDARY"]),
        "production_status",
    ] = pick_level

    board["research_board_label"] = "RESEARCH_ONLY"
    board["production_fields_unchanged"] = 1

    preferred_columns = [
        "research_rank",
        "player",
        "team",
        "opponent",
        "prop_type",
        "line",
        "research_direction",
        "research_score",
        "research_confidence",
        "best_prop_for_player",
        "research_same_player_rank",
        "research_direction_gap",
        "statistical_edge_component",
        "opportunity_component",
        "directional_matchup_component",
        "line_value_component",
        "data_quality_component",
        "research_why",
        "research_why_not",
        "production_status",
        "final_selection",
        "pick_level",
        "eligibility_status",
        "exclusion_reason",
        "correlation_cluster",
    ]

    remaining = [
        column
        for column in board.columns
        if column not in preferred_columns
    ]

    board = board[
        [
            column
            for column in preferred_columns
            if column in board.columns
        ]
        + remaining
    ]

    board = board.sort_values(
        ["research_rank", "player", "prop_type"],
        na_position="last",
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    board.to_csv(output, index=False)

    return len(board)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an explainable research-only prop board."
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

    rows = build_research_board(
        source=args.source,
        output=args.output,
    )

    print("=" * 72)
    print("SPORTS HUB EXPLAINABLE RESEARCH BOARD")
    print("=" * 72)
    print(f"Rows: {rows:,}")
    print(f"Saved: {args.output}")
    print("Label: RESEARCH ONLY")
    print("Production v22 fields were not modified.")


if __name__ == "__main__":
    main()
