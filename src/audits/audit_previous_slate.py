from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import pandas as pd


PROP_TO_RESULT = {
    "Points": "PTS",
    "Rebounds": "REB",
    "Assists": "AST",
    "Pts+Rebs+Asts": "PRA",
    "Pts+Rebs": "PTS_REB",
    "Pts+Asts": "PTS_AST",
    "Rebs+Asts": "REB_AST",
    "Fantasy Score": "FANTASY_SCORE_PP",
    "Offensive Rebounds": "OREB",
    "Defensive Rebounds": "DREB",
    "FG Made": "FGM",
    "FG Attempted": "FGA",
    "3-PT Made": "FG3M",
    "3-PT Attempted": "FG3A",
    "Free Throws Made": "FTM",
    "Free Throws Attempted": "FTA",
    "Stocks": "STOCKS",
    "Steals": "STL",
    "Blocks": "BLK",
    "Turnovers": "TOV",
}


def normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    text = text.lower().strip()
    return re.sub(r"[^a-z0-9]+", "", text)


def numeric(value: object) -> float | None:
    converted = pd.to_numeric(value, errors="coerce")

    if pd.isna(converted):
        return None

    return float(converted)


def actual_value(result: pd.Series, prop_type: str) -> float | None:
    direct_column = PROP_TO_RESULT.get(prop_type)

    if direct_column:
        return numeric(result.get(direct_column))

    if prop_type == "Two Pointers Made":
        fgm = numeric(result.get("FGM"))
        fg3m = numeric(result.get("FG3M"))

        if fgm is None or fg3m is None:
            return None

        return fgm - fg3m

    if prop_type == "Two Pointers Attempted":
        fga = numeric(result.get("FGA"))
        fg3a = numeric(result.get("FG3A"))

        if fga is None or fg3a is None:
            return None

        return fga - fg3a

    return None


def grade_direction(
    actual: float,
    line: float,
    direction: str,
) -> str:
    if actual == line:
        return "PUSH"

    if direction == "OVER":
        return "HIT" if actual > line else "MISS"

    if direction == "UNDER":
        return "HIT" if actual < line else "MISS"

    return "UNRESOLVED_DIRECTION"


def classify_process(row: pd.Series) -> str:
    if row["audit_status"] not in {"HIT", "MISS", "PUSH"}:
        return "UNRESOLVED"

    if row["audit_status"] == "HIT":
        return "PROCESS_SUCCESS"

    minutes = numeric(row.get("actual_minutes"))
    expected_minutes = numeric(row.get("expected_minutes"))
    opportunity_score = numeric(row.get("opportunity_score"))
    matchup_score = numeric(row.get("matchup_score"))

    if (
        minutes is not None
        and expected_minutes is not None
        and minutes < expected_minutes - 5
    ):
        return "OPPORTUNITY_FAILURE"

    if opportunity_score is not None and opportunity_score < 60:
        return "WEAK_OPPORTUNITY_SIGNAL"

    direction = str(row.get("audit_direction", "")).upper()

    if direction == "OVER" and matchup_score is not None and matchup_score < 50:
        return "MATCHUP_CONFLICT"

    if direction == "UNDER" and matchup_score is not None and matchup_score > 50:
        return "MATCHUP_CONFLICT"

    if abs(float(row.get("margin", 0) or 0)) <= 2:
        return "GOOD_PROCESS_NORMAL_VARIANCE"

    return "MODEL_OR_PROJECTION_ERROR"


def audit_slate(
    board_path: Path,
    results_path: Path,
    output_path: Path,
) -> dict[str, int]:
    if not board_path.exists():
        raise FileNotFoundError(f"Board not found: {board_path}")

    if not results_path.exists():
        raise FileNotFoundError(f"Results not found: {results_path}")

    board = pd.read_csv(board_path)
    results = pd.read_csv(results_path)

    board["_player_key"] = board["player"].map(normalize_name)
    results["_player_key"] = results["PLAYER_NAME"].map(normalize_name)

    results = results.drop_duplicates("_player_key", keep="last")
    result_lookup = results.set_index("_player_key")

    rows: list[dict[str, object]] = []

    for _, prop in board.iterrows():
        record = prop.to_dict()
        player_key = prop["_player_key"]
        final_selection = str(
            prop.get("final_selection", "")
        ).strip().upper()

        baseline_direction = str(
            prop.get("direction", "")
        ).strip().upper()

        over_score = numeric(prop.get("over_score"))
        under_score = numeric(prop.get("under_score"))

        if final_selection in {"OVER", "UNDER"}:
            direction = final_selection
            prediction_layer = "V22_FINAL_SELECTION"
        elif baseline_direction in {"OVER", "UNDER"}:
            direction = baseline_direction
            prediction_layer = "BASELINE_DIRECTION"
        elif over_score is not None and under_score is not None:
            direction = "OVER" if over_score >= under_score else "UNDER"
            prediction_layer = "INFERRED_RESEARCH_DIRECTION"
        else:
            direction = "NO_PREDICTION"
            prediction_layer = "NO_DIRECTION_AVAILABLE"

        signal_direction = direction
        shadow_action = str(
            prop.get("shadow_action", "")
        ).strip().upper()

        if shadow_action == "FADE" and signal_direction == "OVER":
            play_direction = "UNDER"
            direction_semantics = "FADE_OPPOSITE"
        elif shadow_action == "FADE" and signal_direction == "UNDER":
            play_direction = "OVER"
            direction_semantics = "FADE_OPPOSITE"
        else:
            play_direction = signal_direction
            direction_semantics = "DIRECT"

        record["signal_direction"] = signal_direction
        record["play_direction"] = play_direction
        record["direction_semantics"] = direction_semantics
        record["audit_direction"] = play_direction
        record["prediction_layer"] = prediction_layer
        record["production_prediction"] = int(
            final_selection in {"OVER", "UNDER"}
        )
        record["baseline_prediction"] = int(
            baseline_direction in {"OVER", "UNDER"}
        )
        record["actual_value"] = pd.NA
        record["margin"] = pd.NA
        record["audit_status"] = "UNRESOLVED"
        record["result_match_status"] = "PLAYER_NOT_FOUND"
        record["actual_minutes"] = pd.NA
        record["actual_fga"] = pd.NA
        record["actual_fg3a"] = pd.NA
        record["actual_rebounds"] = pd.NA
        record["actual_assists"] = pd.NA
        record["actual_points"] = pd.NA
        record["unsupported_prop"] = 0

        if player_key not in result_lookup.index:
            record["process_classification"] = "PLAYER_RESULT_MISSING"
            rows.append(record)
            continue

        result = result_lookup.loc[player_key]

        if isinstance(result, pd.DataFrame):
            result = result.iloc[-1]

        record["result_match_status"] = "MATCHED"
        record["actual_minutes"] = numeric(result.get("MIN"))
        record["actual_fga"] = numeric(result.get("FGA"))
        record["actual_fg3a"] = numeric(result.get("FG3A"))
        record["actual_rebounds"] = numeric(result.get("REB"))
        record["actual_assists"] = numeric(result.get("AST"))
        record["actual_points"] = numeric(result.get("PTS"))

        actual = actual_value(result, str(prop["prop_type"]))

        if actual is None:
            record["unsupported_prop"] = 1
            record["audit_status"] = "UNSUPPORTED_PROP"
            record["process_classification"] = "UNSUPPORTED_PROP"
            rows.append(record)
            continue

        line = float(prop["line"])
        record["actual_value"] = actual
        record["margin"] = round(actual - line, 2)

        if direction == "OVER":
            directional_margin = actual - line
        elif direction == "UNDER":
            directional_margin = line - actual
        else:
            directional_margin = None

        record["directional_margin"] = (
            round(directional_margin, 2)
            if directional_margin is not None
            else pd.NA
        )

        record["audit_status"] = grade_direction(
            actual=actual,
            line=line,
            direction=direction,
        )

        rows.append(record)

    audit = pd.DataFrame(rows)

    audit["process_classification"] = audit.apply(
        classify_process,
        axis=1,
    )

    resolved = audit["audit_status"].isin(["HIT", "MISS", "PUSH"])

    audit["same_player_result_rank"] = pd.NA

    audit.loc[resolved, "same_player_result_rank"] = (
        audit.loc[resolved]
        .groupby("player")["directional_margin"]
        .rank(method="first", ascending=False)
        .astype("Int64")
    )

    audit["best_actual_prop_for_player"] = 0

    audit.loc[
        audit["same_player_result_rank"].eq(1),
        "best_actual_prop_for_player",
    ] = 1

    audit["model_best_prop_for_player"] = (
        pd.to_numeric(
            audit.get(
                "same_player_rank",
                pd.Series(pd.NA, index=audit.index),
            ),
            errors="coerce",
        )
        .eq(1)
        .astype(int)
    )

    audit["same_player_choice_correct"] = (
        audit["best_actual_prop_for_player"].eq(1)
        & audit["model_best_prop_for_player"].eq(1)
    ).astype(int)

    preferred = [
        "decision_id",
        "slate_date",
        "player",
        "team",
        "opponent",
        "prop_type",
        "line",
        "signal_direction",
        "play_direction",
        "direction_semantics",
        "audit_direction",
        "prediction_layer",
        "production_prediction",
        "baseline_prediction",
        "actual_value",
        "margin",
        "directional_margin",
        "audit_status",
        "process_classification",
        "actual_minutes",
        "actual_fga",
        "actual_fg3a",
        "actual_points",
        "actual_rebounds",
        "actual_assists",
        "model_score",
        "opportunity_score",
        "matchup_score",
        "over_score",
        "under_score",
        "sample_size",
        "same_player_rank",
        "same_player_result_rank",
        "model_best_prop_for_player",
        "best_actual_prop_for_player",
        "same_player_choice_correct",
        "final_selection",
        "shadow_action",
        "exclusion_reason",
        "result_match_status",
        "unsupported_prop",
    ]

    remaining = [
        column
        for column in audit.columns
        if column not in preferred and column != "_player_key"
    ]

    audit = audit[
        [column for column in preferred if column in audit.columns]
        + remaining
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(output_path, index=False)

    counts = audit["audit_status"].value_counts().to_dict()

    return {
        "rows": len(audit),
        "hits": int(counts.get("HIT", 0)),
        "misses": int(counts.get("MISS", 0)),
        "pushes": int(counts.get("PUSH", 0)),
        "unsupported": int(counts.get("UNSUPPORTED_PROP", 0)),
        "unresolved": int(counts.get("UNRESOLVED", 0)),
        "players_missing": int(
            audit["result_match_status"].eq("PLAYER_NOT_FOUND").sum()
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit every prop from a completed WNBA slate."
    )

    parser.add_argument("--board", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    summary = audit_slate(
        board_path=args.board,
        results_path=args.results,
        output_path=args.output,
    )

    print("=" * 72)
    print("SPORTS HUB FULL-SLATE WNBA AUDIT")
    print("=" * 72)

    for key, value in summary.items():
        print(f"{key}: {value}")

    print(f"Saved: {args.output}")
    print("Production v22 weights were not changed.")


if __name__ == "__main__":
    main()
