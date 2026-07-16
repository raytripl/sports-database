from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ALLOWED_PATHS = {
    "PRODUCTION",
    "SHADOW_VALIDATED",
    "RESEARCH_QUALIFIED",
    "RESEARCH_WATCHLIST",
}

MAX_PER_TEAM = 1
MAX_PER_GAME = 2
MAX_CANDIDATES = 12
MAX_PAIR_RELATIONSHIP_SCORE = 69.9


def game_key(row: pd.Series) -> str:
    teams = sorted(
        [
            str(row.get("team", "")).strip().upper(),
            str(row.get("opponent", "")).strip().upper(),
        ]
    )
    return "|".join(teams)


def relationship_lookup(
    relationships: pd.DataFrame,
) -> dict[frozenset[str], float]:
    lookup: dict[frozenset[str], float] = {}

    for _, row in relationships.iterrows():
        key = frozenset(
            {
                str(row.get("left_player", "")).strip().lower(),
                str(row.get("right_player", "")).strip().lower(),
            }
        )

        lookup[key] = float(
            pd.to_numeric(
                row.get("relationship_score"),
                errors="coerce",
            )
            if pd.notna(row.get("relationship_score"))
            else 0.0
        )

    return lookup


def build_diversified_candidates(
    board_path: Path,
    relationships_path: Path,
    output: Path,
) -> tuple[int, int]:
    if not board_path.exists():
        raise FileNotFoundError(
            f"Selection path board not found: {board_path}"
        )

    if not relationships_path.exists():
        raise FileNotFoundError(
            f"Relationships file not found: {relationships_path}"
        )

    board = pd.read_csv(board_path).copy()
    relationships = pd.read_csv(relationships_path)
    lookup = relationship_lookup(relationships)

    board["game_key"] = board.apply(game_key, axis=1)

    best_prop = pd.to_numeric(
        board.get(
            "best_player_prop",
            pd.Series(0, index=board.index),
        ),
        errors="coerce",
    ).fillna(0).eq(1)

    eligible_path = (
        board["selection_path"]
        .astype(str)
        .isin(ALLOWED_PATHS)
    )

    candidates = board[
        best_prop & eligible_path
    ].copy()

    candidates = candidates.sort_values(
        [
            "player_comparison_score",
            "decision_strength",
            "direction_gap",
        ],
        ascending=[False, False, False],
    )

    selected_indices: list[int] = []
    selected_players: set[str] = set()
    team_counts: dict[str, int] = {}
    game_counts: dict[str, int] = {}

    for index, row in candidates.iterrows():
        player = str(row.get("player", "")).strip().lower()
        team = str(row.get("team", "")).strip().upper()
        game = str(row.get("game_key", ""))

        if player in selected_players:
            continue

        if team_counts.get(team, 0) >= MAX_PER_TEAM:
            continue

        if game_counts.get(game, 0) >= MAX_PER_GAME:
            continue

        relationship_blocked = False

        for selected_index in selected_indices:
            selected_player = str(
                candidates.at[selected_index, "player"]
            ).strip().lower()

            score = lookup.get(
                frozenset({player, selected_player}),
                0.0,
            )

            if score > MAX_PAIR_RELATIONSHIP_SCORE:
                relationship_blocked = True
                break

        if relationship_blocked:
            continue

        selected_indices.append(index)
        selected_players.add(player)
        team_counts[team] = team_counts.get(team, 0) + 1
        game_counts[game] = game_counts.get(game, 0) + 1

        if len(selected_indices) == MAX_CANDIDATES:
            break

    candidates["diversified_selected"] = 0
    candidates["diversified_rank"] = pd.NA
    candidates["diversification_label"] = "NOT_SELECTED"

    for rank, index in enumerate(selected_indices, start=1):
        candidates.at[index, "diversified_selected"] = 1
        candidates.at[index, "diversified_rank"] = rank
        candidates.at[
            index,
            "diversification_label",
        ] = "DIVERSIFIED_CANDIDATE"

    candidates["diversification_mode"] = "RESEARCH_ONLY"

    candidates = candidates.sort_values(
        [
            "diversified_selected",
            "diversified_rank",
            "player_comparison_score",
        ],
        ascending=[False, True, False],
        na_position="last",
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(output, index=False)

    return len(candidates), len(selected_indices)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build diversified research candidates."
    )
    parser.add_argument("--board", required=True, type=Path)
    parser.add_argument(
        "--relationships",
        required=True,
        type=Path,
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    candidates, selected = build_diversified_candidates(
        board_path=args.board,
        relationships_path=args.relationships,
        output=args.output,
    )

    print("=" * 72)
    print("SPORTS HUB DIVERSIFICATION ENGINE")
    print("=" * 72)
    print(f"Eligible best-player props: {candidates}")
    print(f"Diversified candidates: {selected}")
    print(f"Saved: {args.output}")
    print("Mode: RESEARCH ONLY")
    print("v22-control fields were not modified.")


if __name__ == "__main__":
    main()
