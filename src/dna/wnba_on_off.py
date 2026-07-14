from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.db import connect
from src.decisions.schema import initialize_schema


DEFAULT_METRICS = [
    "MIN",
    "PTS",
    "REB",
    "AST",
    "PRA",
    "PTS_REB",
    "PTS_AST",
    "REB_AST",
    "FGA",
    "FG3A",
    "FTA",
    "OREB",
    "DREB",
    "FANTASY_SCORE_PP",
]

REQUIRED_COLUMNS = {
    "GAME_ID",
    "GAME_DATE",
    "PLAYER_NAME",
    "TEAM_ABBREVIATION",
    "MIN",
}


def normalize_name(value: object) -> str:
    text = str(value).strip().lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def require_columns(frame: pd.DataFrame) -> None:
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError("History is missing columns: " + ", ".join(missing))


def deduplicate_player_games(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "PLAYER_ID" in result.columns:
        keys = ["GAME_ID", "PLAYER_ID"]
    else:
        result["_dedupe_player"] = result["PLAYER_NAME"].map(normalize_name)
        keys = ["GAME_ID", "_dedupe_player"]
    return result.drop_duplicates(subset=keys, keep="last").copy()


def pregame_history(frame: pd.DataFrame, as_of_date: str) -> pd.DataFrame:
    dates = pd.to_datetime(frame["GAME_DATE"], errors="coerce").dt.normalize()
    cutoff = pd.Timestamp(as_of_date).normalize()
    result = frame.loc[dates < cutoff].copy()
    result["GAME_DATE"] = dates.loc[result.index]
    return result


def safe_average(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return None if values.empty else float(values.mean())


def rate_per_minute(values: pd.Series, minutes: pd.Series) -> float | None:
    numeric_values = pd.to_numeric(values, errors="coerce")
    numeric_minutes = pd.to_numeric(minutes, errors="coerce")
    valid = numeric_values.notna() & numeric_minutes.notna() & (numeric_minutes > 0)
    if not valid.any():
        return None
    return float(numeric_values[valid].sum() / numeric_minutes[valid].sum())


def calculate_on_off(
    history: pd.DataFrame,
    player: str,
    teammate: str,
    as_of_date: str,
    metrics: list[str] | None = None,
) -> pd.DataFrame:
    require_columns(history)
    frame = pregame_history(history, as_of_date)
    frame = deduplicate_player_games(frame)
    frame["_player_key"] = frame["PLAYER_NAME"].map(normalize_name)

    player_key = normalize_name(player)
    teammate_key = normalize_name(teammate)
    if player_key == teammate_key:
        raise ValueError("Player and teammate must be different")

    target = frame[frame["_player_key"] == player_key].copy()
    if target.empty:
        raise ValueError(f"No pregame history found for player: {player}")

    teammate_rows = frame[
        (frame["_player_key"] == teammate_key)
        & (pd.to_numeric(frame["MIN"], errors="coerce") > 0)
    ]
    shared_teams = set(target["TEAM_ABBREVIATION"].dropna().astype(str)) & set(
        teammate_rows["TEAM_ABBREVIATION"].dropna().astype(str)
    )
    if not shared_teams:
        raise ValueError(
            f"No shared team history found for {player} and {teammate}"
        )
    target = target[target["TEAM_ABBREVIATION"].astype(str).isin(shared_teams)].copy()
    present_keys = set(
        zip(
            teammate_rows["GAME_ID"].astype(str),
            teammate_rows["TEAM_ABBREVIATION"].astype(str),
        )
    )
    target["teammate_present"] = [
        (str(game_id), str(team)) in present_keys
        for game_id, team in zip(target["GAME_ID"], target["TEAM_ABBREVIATION"])
    ]

    with_rows = target[target["teammate_present"]]
    without_rows = target[~target["teammate_present"]]
    with_games = len(with_rows)
    without_games = len(without_rows)
    confidence = round(min(with_games, without_games) / 5.0 * 100.0, 1)
    confidence = min(confidence, 100.0)
    sample_flag = "OK" if min(with_games, without_games) >= 5 else "LOW_SAMPLE"

    selected_metrics = metrics or DEFAULT_METRICS
    selected_metrics = [metric for metric in selected_metrics if metric in frame.columns]
    if not selected_metrics:
        raise ValueError("None of the requested metrics exist in history")

    teams = sorted(shared_teams)
    team = teams[0] if len(teams) == 1 else "MULTI"
    rows: list[dict[str, object]] = []

    for metric in selected_metrics:
        with_average = safe_average(with_rows[metric])
        without_average = safe_average(without_rows[metric])
        delta = None
        if with_average is not None and without_average is not None:
            delta = without_average - with_average
        rows.append(
            {
                "as_of_date": str(pd.Timestamp(as_of_date).date()),
                "team": team,
                "player": player,
                "teammate": teammate,
                "metric": metric,
                "with_games": with_games,
                "without_games": without_games,
                "with_average": with_average,
                "without_average": without_average,
                "without_minus_with": delta,
                "with_per_minute": rate_per_minute(with_rows[metric], with_rows["MIN"]),
                "without_per_minute": rate_per_minute(
                    without_rows[metric], without_rows["MIN"]
                ),
                "sample_confidence": confidence,
                "sample_flag": sample_flag,
            }
        )

    return pd.DataFrame(rows)


def calculate_joint_absence(
    history: pd.DataFrame,
    player: str,
    absent_teammates: list[str],
    as_of_date: str,
    metrics: list[str] | None = None,
    minimum_games: int = 3,
) -> pd.DataFrame:
    """Measure the target only in games where every named teammate was absent.

    This deliberately evaluates the intersection of absences. It never sums
    individual teammate effects.
    """
    require_columns(history)
    if not absent_teammates:
        raise ValueError("At least one absent teammate is required")
    teammate_keys = {normalize_name(name) for name in absent_teammates}
    if len(teammate_keys) != len(absent_teammates):
        raise ValueError("Absent teammates must be unique")
    player_key = normalize_name(player)
    if player_key in teammate_keys:
        raise ValueError("Player cannot also be an absent teammate")

    frame = deduplicate_player_games(pregame_history(history, as_of_date))
    frame["_player_key"] = frame["PLAYER_NAME"].map(normalize_name)
    target = frame[frame["_player_key"].eq(player_key)].copy()
    if target.empty:
        raise ValueError(f"No pregame history found for player: {player}")

    present_by_teammate: dict[str, set[tuple[str, str]]] = {}
    shared_teams = set(target["TEAM_ABBREVIATION"].dropna().astype(str))
    for key in teammate_keys:
        rows = frame[
            frame["_player_key"].eq(key)
            & (pd.to_numeric(frame["MIN"], errors="coerce") > 0)
        ]
        shared_teams &= set(rows["TEAM_ABBREVIATION"].dropna().astype(str))
        present_by_teammate[key] = set(zip(rows["GAME_ID"].astype(str), rows["TEAM_ABBREVIATION"].astype(str)))
    if not shared_teams:
        raise ValueError("No shared team history found for the requested joint absence")
    target = target[target["TEAM_ABBREVIATION"].astype(str).isin(shared_teams)].copy()

    target["joint_absence"] = [
        all((str(game_id), str(team)) not in games for games in present_by_teammate.values())
        for game_id, team in zip(target["GAME_ID"], target["TEAM_ABBREVIATION"])
    ]
    absent = target[target["joint_absence"]]
    baseline = target[~target["joint_absence"]]
    absent_games = len(absent)
    baseline_games = len(baseline)
    sample_flag = "OK" if absent_games >= minimum_games and baseline_games >= minimum_games else "LOW_SAMPLE"
    teammate_label = " + ".join(sorted(absent_teammates))
    selected = [metric for metric in (metrics or DEFAULT_METRICS) if metric in frame.columns]
    if not selected:
        raise ValueError("None of the requested metrics exist in history")

    result = []
    for metric in selected:
        absent_average = safe_average(absent[metric])
        baseline_average = safe_average(baseline[metric])
        result.append({
            "as_of_date": str(pd.Timestamp(as_of_date).date()),
            "team": target["TEAM_ABBREVIATION"].astype(str).mode().iloc[0],
            "player": player,
            "teammates_absent": teammate_label,
            "metric": metric,
            "joint_absence_games": absent_games,
            "baseline_games": baseline_games,
            "joint_absence_average": absent_average,
            "baseline_average": baseline_average,
            "joint_absence_delta": (
                absent_average - baseline_average
                if absent_average is not None and baseline_average is not None else None
            ),
            "joint_absence_per_minute": rate_per_minute(absent[metric], absent["MIN"]),
            "sample_flag": sample_flag,
            "recommendation_eligible": False,
        })
    return pd.DataFrame(result)


def save_splits(frame: pd.DataFrame, source: str) -> int:
    initialize_schema()
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sql = """
        INSERT INTO wnba_on_off_splits (
            generated_at, as_of_date, season, team, player, teammate, metric,
            with_games, without_games, with_average, without_average,
            without_minus_with, with_per_minute, without_per_minute,
            sample_confidence, sample_flag, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(as_of_date, player, teammate, metric, team) DO UPDATE SET
            generated_at = excluded.generated_at,
            season = excluded.season,
            with_games = excluded.with_games,
            without_games = excluded.without_games,
            with_average = excluded.with_average,
            without_average = excluded.without_average,
            without_minus_with = excluded.without_minus_with,
            with_per_minute = excluded.with_per_minute,
            without_per_minute = excluded.without_per_minute,
            sample_confidence = excluded.sample_confidence,
            sample_flag = excluded.sample_flag,
            source = excluded.source
    """
    with connect() as connection:
        for _, row in frame.iterrows():
            values = (
                generated_at,
                row["as_of_date"],
                int(str(row["as_of_date"])[:4]),
                row["team"],
                row["player"],
                row["teammate"],
                row["metric"],
                int(row["with_games"]),
                int(row["without_games"]),
                row["with_average"],
                row["without_average"],
                row["without_minus_with"],
                row["with_per_minute"],
                row["without_per_minute"],
                row["sample_confidence"],
                row["sample_flag"],
                source,
            )
            connection.execute(sql, values)
    return len(frame)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate WNBA player performance with/without a teammate."
    )
    parser.add_argument("--history", required=True, type=Path)
    parser.add_argument("--player", required=True)
    parser.add_argument("--teammate", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--save-db", action="store_true")
    parser.add_argument("--source", default="WNBA_RESULTS_HISTORY.csv")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.history.exists():
        raise FileNotFoundError(f"History file not found: {args.history}")
    history = pd.read_csv(args.history)
    splits = calculate_on_off(
        history, args.player, args.teammate, args.as_of
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    splits.to_csv(args.output, index=False)
    if args.save_db:
        save_splits(splits, args.source)

    first = splits.iloc[0]
    print("=" * 70)
    print("WNBA TEAMMATE ON/OFF")
    print("=" * 70)
    print(f"Player: {args.player}")
    print(f"Teammate: {args.teammate}")
    print(f"Pregame cutoff: {args.as_of} (exclusive)")
    print(f"With games: {int(first['with_games'])}")
    print(f"Without games: {int(first['without_games'])}")
    print(f"Sample flag: {first['sample_flag']}")
    print(f"Saved: {args.output}")
    print("Deltas are descriptive and do not change v17.3 weights.")


if __name__ == "__main__":
    main()
