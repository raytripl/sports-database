from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


RESEARCH_DEGRADER_RULE_VERSION = "WNBA_RESEARCH_DEGRADER_V1"

HARD_DEGRADER_PROP_DIRECTIONS = {
    ("REBS+ASTS", "OVER"),
}

WATCHLIST_ONLY_PROP_DIRECTIONS = {
    ("POINTS", "UNDER"),
}


RESEARCH_MINIMUM = 75.0
WATCHLIST_MINIMUM = 60.0
MINIMUM_DIRECTION_GAP = 10.0


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


def build_failed_gates(row: pd.Series) -> str:
    failures: list[str] = []

    if int(row.get("best_player_prop", 0) or 0) != 1:
        failures.append("NOT_BEST_PLAYER_PROP")

    if float(row.get("player_comparison_score", 0) or 0) < RESEARCH_MINIMUM:
        failures.append("COMPARISON_SCORE_LT_75")

    if float(row.get("direction_gap", 0) or 0) < MINIMUM_DIRECTION_GAP:
        failures.append("DIRECTION_GAP_LT_10")

    if str(row.get("decision_confidence", "")).upper() == "LOW":
        failures.append("LOW_DECISION_CONFIDENCE")

    injury_status = str(row.get("injury_status", "")).strip().upper()

    if injury_status in {
        "OUT",
        "INACTIVE",
        "DOUBTFUL",
    }:
        failures.append(f"INJURY_{injury_status}")

    exclusion = str(row.get("exclusion_reason", "")).strip()

    if exclusion:
        failures.append(f"PRODUCTION_BLOCK_{exclusion}")

    return "|".join(failures)


def build_selection_paths(
    source: Path,
    output: Path,
) -> int:
    if not source.exists():
        raise FileNotFoundError(
            f"Player comparison board not found: {source}"
        )

    board = pd.read_csv(source).copy()

    final_selection = text(
        board,
        "final_selection",
    ).str.strip().str.upper()

    model_direction = text(
        board,
        "model_direction",
    ).str.strip().str.upper()

    prop_type = (
        text(board, "prop_type")
        .str.strip()
        .str.upper()
    )

    prop_direction_pairs = pd.Series(
        list(zip(prop_type, model_direction)),
        index=board.index,
    )

    hard_degrader = prop_direction_pairs.isin(
        HARD_DEGRADER_PROP_DIRECTIONS
    )

    watchlist_only_degrader = prop_direction_pairs.isin(
        WATCHLIST_ONLY_PROP_DIRECTIONS
    )

    board["research_degrader_status"] = "NONE"
    board["research_degrader_reason"] = ""
    board["research_degrader_rule_version"] = (
        RESEARCH_DEGRADER_RULE_VERSION
    )

    board.loc[
        hard_degrader,
        "research_degrader_status",
    ] = "HARD_BLOCK"

    board.loc[
        hard_degrader,
        "research_degrader_reason",
    ] = "HISTORICAL_DEGRADER_REBS_PLUS_ASTS_OVER"

    board.loc[
        watchlist_only_degrader,
        "research_degrader_status",
    ] = "WATCHLIST_ONLY"

    board.loc[
        watchlist_only_degrader,
        "research_degrader_reason",
    ] = "HISTORICAL_DEGRADER_POINTS_UNDER"

    best_player_prop = numeric(
        board,
        "best_player_prop",
    ).eq(1)

    comparison_score = numeric(
        board,
        "player_comparison_score",
    )

    direction_gap = numeric(
        board,
        "direction_gap",
    )

    confidence = text(
        board,
        "decision_confidence",
    ).str.strip().str.upper()

    shadow_eligible = numeric(
        board,
        "shadow_parlay_eligible",
    ).eq(1)

    injury_status = text(
        board,
        "injury_status",
    ).str.strip().str.upper()

    unavailable = injury_status.isin(
        [
            "OUT",
            "INACTIVE",
            "DOUBTFUL",
        ]
    )

    board["selection_path"] = "NO_BET"
    board["selection_label"] = "LOW_CONFIDENCE"
    board["path_direction"] = model_direction
    board["production_eligible_path"] = 0
    board["research_eligible_path"] = 0
    board["watchlist_eligible_path"] = 0

    production = (
        final_selection.isin(["OVER", "UNDER"])
        & ~unavailable
    )

    shadow = (
        ~production
        & shadow_eligible
        & best_player_prop
        & ~unavailable
    )

    research = (
        ~production
        & ~shadow
        & best_player_prop
        & comparison_score.ge(RESEARCH_MINIMUM)
        & direction_gap.ge(MINIMUM_DIRECTION_GAP)
        & confidence.isin(["HIGH", "MEDIUM"])
        & model_direction.isin(["OVER", "UNDER"])
        & ~unavailable
        & ~hard_degrader
        & ~watchlist_only_degrader
    )

    watchlist = (
        ~production
        & ~shadow
        & ~research
        & best_player_prop
        & comparison_score.ge(WATCHLIST_MINIMUM)
        & model_direction.isin(["OVER", "UNDER"])
        & ~unavailable
        & ~hard_degrader
    )

    board.loc[production, "selection_path"] = "PRODUCTION"
    board.loc[production, "selection_label"] = "OFFICIAL"
    board.loc[production, "production_eligible_path"] = 1

    board.loc[shadow, "selection_path"] = "SHADOW_VALIDATED"
    board.loc[shadow, "selection_label"] = "SHADOW_ONLY"
    board.loc[shadow, "research_eligible_path"] = 1

    board.loc[research, "selection_path"] = "RESEARCH_QUALIFIED"
    board.loc[research, "selection_label"] = "RESEARCH_ONLY"
    board.loc[research, "research_eligible_path"] = 1

    board.loc[watchlist, "selection_path"] = "RESEARCH_WATCHLIST"
    board.loc[watchlist, "selection_label"] = "WATCHLIST"
    board.loc[watchlist, "watchlist_eligible_path"] = 1

    board.loc[
        hard_degrader,
        "selection_path",
    ] = "NO_BET"

    board.loc[
        hard_degrader,
        "selection_label",
    ] = "LOW_CONFIDENCE"

    board.loc[
        hard_degrader,
        [
            "production_eligible_path",
            "research_eligible_path",
            "watchlist_eligible_path",
        ],
    ] = 0

    board["failed_gates"] = board.apply(
        build_failed_gates,
        axis=1,
    )

    board["selection_reason"] = board["selection_path"]

    board.loc[
        board["selection_path"].eq("NO_BET"),
        "selection_reason",
    ] = board.loc[
        board["selection_path"].eq("NO_BET"),
        "failed_gates",
    ]

    board.loc[
        hard_degrader,
        "selection_reason",
    ] = board.loc[
        hard_degrader,
        "research_degrader_reason",
    ]

    board.loc[
        watchlist_only_degrader
        & board["selection_path"].eq(
            "RESEARCH_WATCHLIST"
        ),
        "selection_reason",
    ] = board.loc[
        watchlist_only_degrader
        & board["selection_path"].eq(
            "RESEARCH_WATCHLIST"
        ),
        "research_degrader_reason",
    ]

    board["selection_path_mode"] = "RESEARCH_ONLY"

    preferred = [
        "selection_path",
        "selection_label",
        "path_direction",
        "player",
        "team",
        "opponent",
        "prop_type",
        "line",
        "player_comparison_score",
        "player_prop_rank",
        "best_player_prop",
        "decision_strength",
        "direction_gap",
        "decision_confidence",
        "failed_gates",
        "selection_reason",
        "research_degrader_status",
        "research_degrader_reason",
        "research_degrader_rule_version",
        "production_eligible_path",
        "research_eligible_path",
        "watchlist_eligible_path",
        "final_selection",
        "exclusion_reason",
        "selection_path_mode",
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

    path_order = {
        "PRODUCTION": 0,
        "SHADOW_VALIDATED": 1,
        "RESEARCH_QUALIFIED": 2,
        "RESEARCH_WATCHLIST": 3,
        "NO_BET": 4,
    }

    board["_path_order"] = (
        board["selection_path"]
        .map(path_order)
        .fillna(99)
    )

    board = board.sort_values(
        [
            "_path_order",
            "player_comparison_score",
            "direction_gap",
        ],
        ascending=[True, False, False],
    ).drop(columns="_path_order")

    output.parent.mkdir(parents=True, exist_ok=True)
    board.to_csv(output, index=False)

    return len(board)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assign every prop to a selection path."
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    rows = build_selection_paths(
        source=args.source,
        output=args.output,
    )

    print("=" * 72)
    print("SPORTS HUB SELECTION PATH ENGINE")
    print("=" * 72)
    print(f"Rows: {rows:,}")
    print(f"Saved: {args.output}")
    print("Production v22 fields were not modified.")


if __name__ == "__main__":
    main()
