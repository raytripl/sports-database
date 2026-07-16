from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


SAME_PLAYER_FAMILY_RISK = {
    frozenset({"Points", "Pts+Rebs+Asts"}): 95.0,
    frozenset({"Points", "Pts+Rebs"}): 90.0,
    frozenset({"Points", "Pts+Asts"}): 90.0,
    frozenset({"Points", "Fantasy Score"}): 88.0,
    frozenset({"Rebounds", "Pts+Rebs"}): 88.0,
    frozenset({"Assists", "Pts+Asts"}): 88.0,
    frozenset({"Rebounds", "Rebs+Asts"}): 88.0,
    frozenset({"Assists", "Rebs+Asts"}): 88.0,
    frozenset({"Pts+Rebs", "Pts+Rebs+Asts"}): 92.0,
    frozenset({"Pts+Asts", "Pts+Rebs+Asts"}): 92.0,
    frozenset({"Rebs+Asts", "Pts+Rebs+Asts"}): 92.0,
    frozenset({"3-PT Made", "Points"}): 60.0,
    frozenset({"3-PT Attempted", "3-PT Made"}): 75.0,
    frozenset({"FG Attempted", "Points"}): 65.0,
    frozenset({"FG Made", "Points"}): 78.0,
}


def text(
    frame: pd.DataFrame,
    column: str,
    default: str = "",
) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype="object")

    return frame[column].fillna(default).astype(str)


def game_key(row: pd.Series) -> str:
    teams = sorted(
        [
            str(row.get("team", "")).strip().upper(),
            str(row.get("opponent", "")).strip().upper(),
        ]
    )
    return "|".join(teams)


def relationship_score(
    left: pd.Series,
    right: pd.Series,
) -> tuple[float, str]:
    left_player = str(left.get("player", "")).strip().lower()
    right_player = str(right.get("player", "")).strip().lower()

    left_team = str(left.get("team", "")).strip().upper()
    right_team = str(right.get("team", "")).strip().upper()

    left_game = str(left.get("game_key", ""))
    right_game = str(right.get("game_key", ""))

    left_prop = str(left.get("prop_type", "")).strip()
    right_prop = str(right.get("prop_type", "")).strip()

    left_direction = str(
        left.get("path_direction", left.get("model_direction", ""))
    ).strip().upper()

    right_direction = str(
        right.get("path_direction", right.get("model_direction", ""))
    ).strip().upper()

    reasons: list[str] = []
    score = 0.0

    if left_player == right_player:
        family_score = SAME_PLAYER_FAMILY_RISK.get(
            frozenset({left_prop, right_prop}),
            85.0,
        )

        score = max(score, family_score)
        reasons.append("SAME_PLAYER")

        if left_direction != right_direction:
            score = min(100.0, score + 10.0)
            reasons.append("OPPOSITE_DIRECTIONS")

    elif left_team == right_team:
        score = max(score, 30.0)
        reasons.append("SAME_TEAM")

        if left_game == right_game:
            score = max(score, 35.0)

    elif left_game == right_game:
        score = max(score, 20.0)
        reasons.append("SAME_GAME")

    if (
        left_direction == "OVER"
        and right_direction == "OVER"
        and left_game == right_game
    ):
        score = min(100.0, score + 10.0)
        reasons.append("SHARED_GAME_ENVIRONMENT")

    if (
        left_direction != right_direction
        and left_game == right_game
    ):
        score = min(100.0, score + 5.0)
        reasons.append("MIXED_DIRECTION_GAME")

    return round(score, 1), "|".join(reasons)


def build_relationship_engine(
    source: Path,
    output: Path,
) -> int:
    if not source.exists():
        raise FileNotFoundError(
            f"Selection path board not found: {source}"
        )

    board = pd.read_csv(source).copy()
    board["game_key"] = board.apply(game_key, axis=1)

    best = board[
        pd.to_numeric(
            board.get(
                "best_player_prop",
                pd.Series(0, index=board.index),
            ),
            errors="coerce",
        ).fillna(0).eq(1)
    ].copy()

    rows: list[dict[str, object]] = []

    for left_index, left in best.iterrows():
        for right_index, right in best.iterrows():
            if right_index <= left_index:
                continue

            score, reason = relationship_score(left, right)

            rows.append(
                {
                    "left_player": left.get("player"),
                    "left_team": left.get("team"),
                    "left_opponent": left.get("opponent"),
                    "left_prop_type": left.get("prop_type"),
                    "left_line": left.get("line"),
                    "left_direction": left.get(
                        "path_direction",
                        left.get("model_direction"),
                    ),
                    "left_selection_path": left.get("selection_path"),
                    "right_player": right.get("player"),
                    "right_team": right.get("team"),
                    "right_opponent": right.get("opponent"),
                    "right_prop_type": right.get("prop_type"),
                    "right_line": right.get("line"),
                    "right_direction": right.get(
                        "path_direction",
                        right.get("model_direction"),
                    ),
                    "right_selection_path": right.get("selection_path"),
                    "same_game": int(
                        str(left.get("game_key", ""))
                        == str(right.get("game_key", ""))
                    ),
                    "same_team": int(
                        str(left.get("team", "")).upper()
                        == str(right.get("team", "")).upper()
                    ),
                    "same_player": int(
                        str(left.get("player", "")).lower()
                        == str(right.get("player", "")).lower()
                    ),
                    "relationship_score": score,
                    "relationship_reason": reason,
                    "relationship_label": (
                        "HIGH_RISK"
                        if score >= 70
                        else "MODERATE_RISK"
                        if score >= 35
                        else "LOW_RISK"
                    ),
                    "relationship_mode": "RESEARCH_ONLY",
                }
            )

    relationships = pd.DataFrame(rows)

    output.parent.mkdir(parents=True, exist_ok=True)
    relationships.to_csv(output, index=False)

    return len(relationships)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build prop-to-prop relationship scores."
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    rows = build_relationship_engine(
        source=args.source,
        output=args.output,
    )

    print("=" * 72)
    print("SPORTS HUB RELATIONSHIP ENGINE")
    print("=" * 72)
    print(f"Relationships: {rows:,}")
    print(f"Saved: {args.output}")
    print("Mode: RESEARCH ONLY")
    print("v22-control fields were not modified.")


if __name__ == "__main__":
    main()
