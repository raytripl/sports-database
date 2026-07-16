from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def text(
    frame: pd.DataFrame,
    column: str,
    default: str = "",
) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype="object")

    return frame[column].fillna(default).astype(str)


def build_game_key(row: pd.Series) -> str:
    teams = sorted(
        [
            str(row.get("team", "")).strip().upper(),
            str(row.get("opponent", "")).strip().upper(),
        ]
    )
    return "|".join(teams)


def build_correlation_engine(
    source: Path,
    output: Path,
) -> int:
    if not source.exists():
        raise FileNotFoundError(
            f"Selection path board not found: {source}"
        )

    board = pd.read_csv(source).copy()

    board["game_key"] = board.apply(
        build_game_key,
        axis=1,
    )

    board["correlation_cluster"] = (
        text(board, "game_key")
        + "|"
        + text(board, "team").str.upper()
    )

    board["duplicate_player_risk"] = (
        board.groupby("player")["player"]
        .transform("count")
        .gt(1)
        .astype(int)
    )

    board["same_team_prop_count"] = (
        board.groupby("team")["team"]
        .transform("count")
        .astype(int)
    )

    board["same_game_prop_count"] = (
        board.groupby("game_key")["game_key"]
        .transform("count")
        .astype(int)
    )

    board["correlation_score"] = 0.0

    board.loc[
        board["duplicate_player_risk"].eq(1),
        "correlation_score",
    ] += 50.0

    board.loc[
        board["same_team_prop_count"].ge(2),
        "correlation_score",
    ] += 20.0

    board.loc[
        board["same_game_prop_count"].ge(2),
        "correlation_score",
    ] += 20.0

    board["correlation_score"] = (
        board["correlation_score"]
        .clip(0, 100)
        .round(1)
    )

    warnings: list[str] = []

    for _, row in board.iterrows():
        row_warnings: list[str] = []

        if int(row.get("duplicate_player_risk", 0) or 0) == 1:
            row_warnings.append("DUPLICATE_PLAYER_OPTIONS")

        if int(row.get("same_team_prop_count", 0) or 0) >= 2:
            row_warnings.append("SAME_TEAM_EXPOSURE")

        if int(row.get("same_game_prop_count", 0) or 0) >= 2:
            row_warnings.append("SAME_GAME_EXPOSURE")

        warnings.append("|".join(row_warnings))

    board["correlation_warning"] = warnings

    board["recommended_diversification"] = "NONE"

    board.loc[
        board["correlation_score"].ge(40),
        "recommended_diversification",
    ] = "LIMIT_SAME_GAME_OR_TEAM"

    board["correlation_mode"] = "RESEARCH_ONLY"

    preferred = [
        "selection_path",
        "selection_label",
        "path_direction",
        "player",
        "team",
        "opponent",
        "game_key",
        "prop_type",
        "line",
        "player_comparison_score",
        "player_prop_rank",
        "best_player_prop",
        "decision_strength",
        "direction_gap",
        "decision_confidence",
        "correlation_score",
        "correlation_warning",
        "duplicate_player_risk",
        "same_team_prop_count",
        "same_game_prop_count",
        "correlation_cluster",
        "recommended_diversification",
        "failed_gates",
        "final_selection",
        "exclusion_reason",
        "correlation_mode",
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

    output.parent.mkdir(parents=True, exist_ok=True)
    board.to_csv(output, index=False)

    return len(board)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add research-only correlation context."
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    rows = build_correlation_engine(
        source=args.source,
        output=args.output,
    )

    print("=" * 72)
    print("SPORTS HUB CORRELATION ENGINE")
    print("=" * 72)
    print(f"Rows: {rows:,}")
    print(f"Saved: {args.output}")
    print("Production v22 fields were not modified.")


if __name__ == "__main__":
    main()
