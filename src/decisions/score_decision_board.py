from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from src.decisions.wnba_opportunity import calculate_opportunity_context
from src.decisions.wnba_matchup import calculate_team_matchup_context
from src.decisions.wnba_suppression import calculate_suppression_context


PROP_TO_RESULT = {
    "Points": "PTS",
    "Rebounds": "REB",
    "Assists": "AST",
    "Pts+Rebs+Asts": "PRA",
    "Pts+Rebs": "PTS_REB",
    "Pts+Asts": "PTS_AST",
    "Rebs+Asts": "REB_AST",
    "Fantasy Score": "FANTASY_SCORE_PP",
    "3-PT Made": "FG3M",
    "3-PT Attempted": "FG3A",
    "FG Attempted": "FGA",
    "FG Made": "FGM",
    "Def Rebounds": "DREB",
    "Defensive Rebounds": "DREB",
    "Off Rebounds": "OREB",
    "Offensive Rebounds": "OREB",
    "Blks+Stls": "STOCKS",
    "Blocked Shots": "BLK",
    "Steals": "STL",
    "Turnovers": "TOV",
    "2-PT Attempted": "FG2A",
    "Two Pointers Attempted": "FG2A",
    "2-PT Made": "FG2M",
    "Two Pointers Made": "FG2M",
    "Free Throws Attempted": "FTA",
    "Free Throws Made": "FTM",
}

TEXT_COLUMNS = [
    "direction",
    "grade",
    "entry_type",
    "over_reason",
    "under_reason",
    "red_flags",
    "decision_reason",
]

BASELINE_RED_FLAG = (
    "Baseline only: current injuries, starters, role, matchup, and coaching "
    "strategy are not verified"
)

REQUIRED_BOARD_COLUMNS = {
    "decision_id",
    "slate_date",
    "player",
    "prop_type",
    "line",
}

REQUIRED_HISTORY_COLUMNS = {
    "GAME_ID",
    "GAME_DATE",
    "PLAYER_NAME",
    "TEAM_ABBREVIATION",
    "MATCHUP",
    "MIN",
}


def normalize_name(value: object) -> str:
    text = str(value).strip().lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def numeric_values(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").dropna()


def safe_mean(series: pd.Series) -> float | None:
    values = numeric_values(series)
    return None if values.empty else float(values.mean())


def rate_above(series: pd.Series, line: float) -> float | None:
    values = numeric_values(series)
    return None if values.empty else float((values > line).mean())


def rate_below(series: pd.Series, line: float) -> float | None:
    values = numeric_values(series)
    return None if values.empty else float((values < line).mean())


def clip_score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


def calculate_scores(values: pd.Series, line: float) -> dict[str, object]:
    values = numeric_values(values)
    sample_size = len(values)

    if sample_size == 0:
        return {
            "sample_size": 0,
            "season_avg": None,
            "l5_avg": None,
            "l10_avg": None,
            "season_over_rate": None,
            "l5_over_rate": None,
            "l10_over_rate": None,
            "season_under_rate": None,
            "l5_under_rate": None,
            "l10_under_rate": None,
            "over_score": 0.0,
            "under_score": 0.0,
        }

    season = values
    l5 = values.tail(5)
    l10 = values.tail(10)

    season_avg = safe_mean(season)
    l5_avg = safe_mean(l5)
    l10_avg = safe_mean(l10)

    season_over = rate_above(season, line)
    l5_over = rate_above(l5, line)
    l10_over = rate_above(l10, line)

    season_under = rate_below(season, line)
    l5_under = rate_below(l5, line)
    l10_under = rate_below(l10, line)

    denominator = max(abs(line), 1.0)
    over_edge = (((l10_avg or 0.0) - line) / denominator) * 100.0
    under_edge = ((line - (l10_avg or 0.0)) / denominator) * 100.0
    sample_confidence = min(sample_size / 10.0, 1.0)

    over_score = (
        0.30 * (season_over or 0.0) * 100
        + 0.25 * (l10_over or 0.0) * 100
        + 0.15 * (l5_over or 0.0) * 100
        + 0.20 * (50 + over_edge)
        + 0.10 * sample_confidence * 100
    )

    under_score = (
        0.30 * (season_under or 0.0) * 100
        + 0.25 * (l10_under or 0.0) * 100
        + 0.15 * (l5_under or 0.0) * 100
        + 0.20 * (50 + under_edge)
        + 0.10 * sample_confidence * 100
    )

    return {
        "sample_size": sample_size,
        "season_avg": season_avg,
        "l5_avg": l5_avg,
        "l10_avg": l10_avg,
        "season_over_rate": season_over,
        "l5_over_rate": l5_over,
        "l10_over_rate": l10_over,
        "season_under_rate": season_under,
        "l5_under_rate": l5_under,
        "l10_under_rate": l10_under,
        "over_score": clip_score(over_score),
        "under_score": clip_score(under_score),
    }


def choose_direction(
    over_score: float,
    under_score: float,
    sample_size: int,
) -> tuple[str, float, str]:
    best_score = max(over_score, under_score)
    difference = abs(over_score - under_score)

    if sample_size < 3:
        return "PASS", best_score, "Insufficient history"

    if best_score < 58 or difference < 5:
        return "PASS", best_score, "No clear statistical edge"

    if over_score > under_score:
        return "OVER", over_score, "Baseline history favors the over"

    return "UNDER", under_score, "Baseline history favors the under"


def assign_grade(direction: str, score: float, sample_size: int) -> str:
    if direction == "PASS":
        return "PASS"
    if sample_size < 5:
        return "B-"
    if score >= 82:
        return "B+"
    if score >= 74:
        return "B"
    if score >= 66:
        return "B-"
    return "C"


def require_columns(
    frame: pd.DataFrame,
    required: set[str],
    label: str,
) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: {', '.join(missing)}")


def filter_pregame_history(
    board: pd.DataFrame,
    history: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Timestamp]:
    slate_dates = pd.to_datetime(board["slate_date"], errors="coerce").dropna().unique()
    if len(slate_dates) != 1:
        raise ValueError("Decision board must contain exactly one valid slate_date")

    slate_date = pd.Timestamp(slate_dates[0]).normalize()
    game_dates = pd.to_datetime(history["GAME_DATE"], errors="coerce").dt.normalize()
    filtered = history.loc[game_dates < slate_date].copy()
    filtered["GAME_DATE"] = game_dates.loc[filtered.index]
    return filtered, slate_date


def deduplicate_player_games(history: pd.DataFrame) -> pd.DataFrame:
    """Keep one canonical result for each player in each game."""

    frame = history.copy()
    if "PLAYER_ID" in frame.columns:
        keys = ["GAME_ID", "PLAYER_ID"]
    else:
        frame["_dedupe_player"] = frame["PLAYER_NAME"].map(normalize_name)
        keys = ["GAME_ID", "_dedupe_player"]
    return frame.drop_duplicates(subset=keys, keep="last").copy()


def score_board(
    board_path: Path,
    history_path: Path,
    output_path: Path,
) -> int:
    if not board_path.exists():
        raise FileNotFoundError(f"Decision board not found: {board_path}")
    if not history_path.exists():
        raise FileNotFoundError(f"History file not found: {history_path}")

    board = pd.read_csv(board_path)
    history = pd.read_csv(history_path)

    require_columns(board, REQUIRED_BOARD_COLUMNS, "Decision board")
    require_columns(history, REQUIRED_HISTORY_COLUMNS, "History file")

    history, slate_date = filter_pregame_history(board, history)
    history = deduplicate_player_games(history)
    history = history.sort_values("GAME_DATE")
    history["_player_key"] = history["PLAYER_NAME"].map(normalize_name)
    board["_player_key"] = board["player"].map(normalize_name)

    for column in TEXT_COLUMNS:
        board[column] = board[column].astype("object")

    scoring_rows: list[dict[str, object]] = []
    opportunity_rows: list[dict[str, object]] = []
    suppression_rows: list[dict[str, object]] = []
    matchup_rows: list[dict[str, object]] = []

    for index, row in board.iterrows():
        prop_type = str(row["prop_type"])
        result_column = PROP_TO_RESULT.get(prop_type)
        player_history = history[history["_player_key"] == row["_player_key"]]
        opportunity = calculate_opportunity_context(player_history, prop_type)
        suppression = calculate_suppression_context(
            player_history,
            prop_type,
            float(row["line"]),
        )
        matchup = calculate_team_matchup_context(
            history,
            str(row["opponent"]),
            prop_type,
        )

        if result_column is None or result_column not in history.columns:
            metrics = calculate_scores(pd.Series(dtype=float), float(row["line"]))
            red_flag = f"Unsupported prop type; {BASELINE_RED_FLAG}"
        else:
            metrics = calculate_scores(
                player_history[result_column],
                float(row["line"]),
            )
            red_flag = BASELINE_RED_FLAG

        direction, model_score, reason = choose_direction(
            float(metrics["over_score"]),
            float(metrics["under_score"]),
            int(metrics["sample_size"]),
        )

        grade = assign_grade(
            direction,
            model_score,
            int(metrics["sample_size"]),
        )

        board.at[index, "direction"] = direction
        board.at[index, "grade"] = grade
        board.at[index, "model_score"] = model_score
        # Baseline statistics never create a betting recommendation. Current
        # opportunity and matchup confirmation are mandatory under v17.3.
        board.at[index, "recommended"] = 0
        board.at[index, "entry_type"] = ""
        board.at[index, "opportunity_score"] = opportunity["opportunity_score"]
        board.at[index, "expected_minutes"] = opportunity["expected_minutes"]
        board.at[index, "suppression_score"] = suppression["suppression_score"]
        board.at[index, "ceiling_risk_score"] = suppression["ceiling_risk_score"]
        board.at[index, "matchup_score"] = matchup["matchup_score"]
        if direction == "UNDER":
            board.at[index, "under_reason"] = (
                suppression["historical_under_reasons"]
                or "NO_HISTORICAL_STRUCTURAL_REASON"
            )
        elif direction == "OVER":
            board.at[index, "over_reason"] = opportunity["opportunity_note"]
        board.at[index, "red_flags"] = red_flag
        board.at[index, "decision_reason"] = (
            f"BASELINE STATISTICAL ONLY — {reason}; "
            f"{opportunity['opportunity_note']}; "
            f"{suppression['suppression_note']}; "
            f"{matchup['matchup_note']}; "
            f"history cutoff {slate_date.date()}"
        )
        scoring_rows.append(metrics)
        opportunity_rows.append(opportunity)
        suppression_rows.append(suppression)
        matchup_rows.append(matchup)

    metrics_frame = pd.DataFrame(scoring_rows)

    for column in metrics_frame.columns:
        board[column] = metrics_frame[column].values

    opportunity_frame = pd.DataFrame(opportunity_rows)
    for column in opportunity_frame.columns:
        if column not in {"opportunity_score", "expected_minutes"}:
            board[column] = opportunity_frame[column].values

    suppression_frame = pd.DataFrame(suppression_rows)
    for column in suppression_frame.columns:
        if column not in {
            "suppression_score",
            "ceiling_risk_score",
        }:
            board[column] = suppression_frame[column].values

    matchup_frame = pd.DataFrame(matchup_rows)
    for column in matchup_frame.columns:
        if column != "matchup_score":
            board[column] = matchup_frame[column].values

    board["statistical_score"] = board["model_score"]

    board["same_player_rank"] = (
        board.groupby("player")["model_score"]
        .rank(method="first", ascending=False)
        .astype("Int64")
    )

    playable = board["direction"].isin(["OVER", "UNDER"])
    board.loc[playable, "overall_rank"] = (
        board.loc[playable, "model_score"]
        .rank(method="first", ascending=False)
        .astype("Int64")
    )

    board = board.drop(columns=["_player_key"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    board.to_csv(output_path, index=False)

    return len(board)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score a WNBA Raymond decision board using history."
    )
    parser.add_argument("--board", required=True, type=Path)
    parser.add_argument("--history", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = score_board(
        board_path=args.board,
        history_path=args.history,
        output_path=args.output,
    )

    print("=" * 70)
    print("WNBA BASELINE SCORER")
    print("=" * 70)
    print(f"Rows scored: {rows:,}")
    print(f"Saved: {args.output}")
    print()
    print("WARNING: Baseline statistical grades only.")
    print("A/A+ grades are disabled until opportunity and matchup data exist.")


if __name__ == "__main__":
    main()
