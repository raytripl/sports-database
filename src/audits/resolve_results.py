from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.db import connect
from src.decisions.schema import initialize_schema


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
}

REQUIRED_RESULT_COLUMNS = {
    "GAME_ID",
    "GAME_DATE",
    "PLAYER_NAME",
    "MIN",
}


def normalize_name(value: object) -> str:
    text = str(value).strip().lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def require_columns(frame: pd.DataFrame, required: set[str]) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("Results file is missing columns: " + ", ".join(missing))


def deduplicate_player_games(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "PLAYER_ID" in result.columns:
        keys = ["GAME_ID", "PLAYER_ID"]
    else:
        result["_dedupe_player"] = result["PLAYER_NAME"].map(normalize_name)
        keys = ["GAME_ID", "_dedupe_player"]
    return result.drop_duplicates(subset=keys, keep="last").copy()


def load_slate_results(results_path: Path, slate_date: str) -> pd.DataFrame:
    if not results_path.exists():
        raise FileNotFoundError(f"Results file not found: {results_path}")

    frame = pd.read_csv(results_path)
    require_columns(frame, REQUIRED_RESULT_COLUMNS)
    dates = pd.to_datetime(frame["GAME_DATE"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame = frame.loc[dates == slate_date].copy()
    frame = deduplicate_player_games(frame)
    frame["_player_key"] = frame["PLAYER_NAME"].map(normalize_name)
    return frame


def classify_status(direction: str, actual: float, line: float) -> str:
    if direction not in {"OVER", "UNDER"}:
        return "PASS"
    if actual == line:
        return "PUSH"
    if direction == "OVER":
        return "HIT" if actual > line else "MISS"
    if direction == "UNDER":
        return "HIT" if actual < line else "MISS"
    raise ValueError(f"Unsupported decision direction: {direction}")


def result_value(row: pd.Series, prop_type: str) -> float | None:
    column = PROP_TO_RESULT.get(prop_type)
    if column is None or column not in row.index:
        return None
    value = pd.to_numeric(pd.Series([row[column]]), errors="coerce").iloc[0]
    return None if pd.isna(value) else float(value)


def resolve_snapshot(
    snapshot_id: str,
    results_path: Path,
) -> dict[str, int]:
    initialize_schema()

    with connect() as connection:
        decisions = pd.read_sql_query(
            """
            SELECT decision_id, slate_date, sport, player, team,
                   prop_type, line, direction
            FROM model_decisions
            WHERE snapshot_id = ?
            ORDER BY decision_id
            """,
            connection,
            params=(snapshot_id,),
        )

    if decisions.empty:
        raise ValueError(f"No model decisions found for snapshot: {snapshot_id}")

    slate_dates = decisions["slate_date"].dropna().astype(str).unique()
    sports = decisions["sport"].dropna().astype(str).str.upper().unique()
    if len(slate_dates) != 1 or len(sports) != 1:
        raise ValueError("Snapshot must contain exactly one slate date and sport")
    if sports[0] != "WNBA":
        raise ValueError("This resolver currently supports WNBA snapshots only")

    slate_date = slate_dates[0]
    results = load_slate_results(results_path, slate_date)
    grouped = {
        key: group
        for key, group in results.groupby("_player_key", sort=False)
    }

    counts = {
        "HIT": 0,
        "MISS": 0,
        "PUSH": 0,
        "PASS": 0,
        "PENDING": 0,
        "UNSUPPORTED": 0,
    }
    resolved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    upsert_sql = """
        INSERT INTO prop_results (
            decision_id, resolved_at, status, actual_value, margin,
            minutes, opportunity_received, result_notes,
            process_quality, model_change_required
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        ON CONFLICT(decision_id) DO UPDATE SET
            resolved_at = excluded.resolved_at,
            status = excluded.status,
            actual_value = excluded.actual_value,
            margin = excluded.margin,
            minutes = excluded.minutes,
            opportunity_received = excluded.opportunity_received,
            result_notes = excluded.result_notes,
            process_quality = excluded.process_quality
    """

    with connect() as connection:
        for _, decision in decisions.iterrows():
            key = normalize_name(decision["player"])
            player_rows = grouped.get(key)

            if player_rows is None or player_rows.empty:
                status = "PENDING"
                counts[status] += 1
                values = (
                    int(decision["decision_id"]), resolved_at, status,
                    None, None, None, "NO_RESULT_FOUND",
                    "No matching player result found for the slate",
                    "UNREVIEWED",
                )
                connection.execute(upsert_sql, values)
                continue

            # A player should have only one game per slate. If a rare doubleheader
            # appears, prefer the row matching the saved team; otherwise do not guess.
            if len(player_rows) > 1 and "TEAM_ABBREVIATION" in player_rows.columns:
                team_rows = player_rows[
                    player_rows["TEAM_ABBREVIATION"].astype(str).str.upper()
                    == str(decision["team"]).upper()
                ]
                if len(team_rows) == 1:
                    player_rows = team_rows

            if len(player_rows) != 1:
                status = "PENDING"
                counts[status] += 1
                values = (
                    int(decision["decision_id"]), resolved_at, status,
                    None, None, None, "AMBIGUOUS_RESULT",
                    "Multiple matching player results; no result was guessed",
                    "UNREVIEWED",
                )
                connection.execute(upsert_sql, values)
                continue

            result = player_rows.iloc[0]
            actual = result_value(result, str(decision["prop_type"]))
            if actual is None:
                status = "UNSUPPORTED"
                counts[status] += 1
                values = (
                    int(decision["decision_id"]), resolved_at, status,
                    None, None, float(result["MIN"]), "RESULT_COLUMN_UNAVAILABLE",
                    f"Unsupported or missing result column for {decision['prop_type']}",
                    "UNREVIEWED",
                )
                connection.execute(upsert_sql, values)
                continue

            line = float(decision["line"])
            direction = str(decision["direction"]).upper()
            status = classify_status(direction, actual, line)
            counts[status] += 1
            minutes = pd.to_numeric(pd.Series([result["MIN"]]), errors="coerce").iloc[0]
            minutes_value = None if pd.isna(minutes) else float(minutes)
            opportunity = (
                f"MIN={minutes_value:g}" if minutes_value is not None else "MIN=UNKNOWN"
            )
            values = (
                int(decision["decision_id"]), resolved_at, status,
                actual, actual - line, minutes_value, opportunity,
                "Official WNBA player-game result matched by slate and player",
                "UNREVIEWED",
            )
            connection.execute(upsert_sql, values)

    return counts


def export_audit(snapshot_id: str, report_path: Path) -> int:
    with connect() as connection:
        frame = pd.read_sql_query(
            """
            SELECT
                d.decision_id,
                d.snapshot_id,
                d.slate_date,
                d.sport,
                d.player,
                d.team,
                d.opponent,
                d.prop_type,
                d.line,
                d.direction,
                d.grade,
                d.model_score,
                d.opportunity_score,
                d.suppression_score,
                d.matchup_score,
                d.recommended,
                d.decision_reason,
                d.red_flags,
                r.status,
                r.actual_value,
                r.margin,
                r.minutes,
                r.opportunity_received,
                r.process_quality,
                r.error_classification,
                r.model_change_required,
                r.result_notes,
                r.resolved_at
            FROM model_decisions AS d
            LEFT JOIN prop_results AS r
                ON r.decision_id = d.decision_id
            WHERE d.snapshot_id = ?
            ORDER BY d.overall_rank IS NULL, d.overall_rank, d.decision_id
            """,
            connection,
            params=(snapshot_id,),
        )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(report_path, index=False)
    return len(frame)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve a saved WNBA model snapshot against player results."
    )
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    counts = resolve_snapshot(args.snapshot_id, args.results)
    print("=" * 70)
    print("WNBA RESULT RESOLVER")
    print("=" * 70)
    print(f"Snapshot: {args.snapshot_id}")
    for label in ("HIT", "MISS", "PUSH", "PASS", "PENDING", "UNSUPPORTED"):
        print(f"{label}: {counts[label]:,}")
    if args.report is not None:
        rows = export_audit(args.snapshot_id, args.report)
        print(f"Audit rows: {rows:,}")
        print(f"Audit report: {args.report}")
    print("Process-quality and error classifications remain UNREVIEWED.")


if __name__ == "__main__":
    main()
