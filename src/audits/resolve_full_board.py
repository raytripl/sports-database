from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.db import connect
from src.decisions.schema import initialize_schema


WNBA_PROP_COLUMNS = {
    "points": "PTS",
    "rebounds": "REB",
    "assists": "AST",
    "ptsrebsasts": "PRA",
    "ptsrebs": "PTS_REB",
    "ptsasts": "PTS_AST",
    "rebsasts": "REB_AST",
    "fantasyscore": "FANTASY_SCORE_PP",
    "3ptmade": "FG3M",
    "3ptattempted": "FG3A",
    "fgmade": "FGM",
    "fgattempted": "FGA",
    "freethrowsmade": "FTM",
    "freethrowsattempted": "FTA",
    "offensiverebounds": "OREB",
    "defensiverebounds": "DREB",
    "steals": "STL",
    "blocks": "BLK",
    "stocks": "STOCKS",
    "turnovers": "TOV",
}

MLB_PROP_COLUMNS = {
    "hits": "H",
    "singles": "SINGLES",
    "totalbases": "TOTAL_BASES",
    "hitsrunsrbis": "H_PLUS_R_PLUS_RBI",
    "hitterfantasyscore": "HITTER_FANTASY_PP",
    "runs": "R",
    "rbis": "RBI",
    "batterwalks": "BB",
    "walks": "BB",
    "stolenbases": "SB",
    "homeruns": "HR",
    "pitcherstrikeouts": "K",
    "strikeouts": "K",
    "pitchingouts": "OUTS",
    "totalpitches": "PITCHES",
    "pitcherfantasyscore": "PITCHER_FANTASY_PP",
    "earnedrunsallowed": "ER",
    "hitsallowed": "HITS_ALLOWED",
}

MLB_PITCHER_COLUMNS = {
    "K", "OUTS", "PITCHES", "PITCHER_FANTASY_PP", "ER", "HITS_ALLOWED"
}


def normalize_token(value: object) -> str:
    token = re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())
    return token.replace("pp", "").replace("ud", "")


def normalize_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def result_column(sport: str, prop_type: object) -> str | None:
    token = normalize_token(prop_type)
    if sport.upper() == "WNBA":
        return WNBA_PROP_COLUMNS.get(token)
    if sport.upper() == "MLB":
        return MLB_PROP_COLUMNS.get(token)
    return None


def classify_status(direction: str, actual: float, line: float) -> str:
    direction = str(direction).upper()
    if direction not in {"OVER", "UNDER"}:
        return "PASS"
    if actual == line:
        return "PUSH"
    if direction == "OVER":
        return "HIT" if actual > line else "MISS"
    return "HIT" if actual < line else "MISS"


def load_results(path: Path, sport: str, slate_date: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Results file not found: {path}")
    frame = pd.read_csv(path)
    date_column = "GAME_DATE" if sport == "WNBA" else "RESULT_DATE"
    name_column = "PLAYER_NAME"
    required = {date_column, name_column}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("Results file is missing columns: " + ", ".join(missing))
    dates = pd.to_datetime(frame[date_column], errors="coerce").dt.strftime("%Y-%m-%d")
    frame = frame.loc[dates == slate_date].copy()
    frame["_player_key"] = frame[name_column].map(normalize_name)
    if sport == "WNBA":
        keys = ["GAME_ID", "PLAYER_ID"] if {"GAME_ID", "PLAYER_ID"}.issubset(frame) else [date_column, "_player_key"]
    else:
        keys = [date_column, "_player_key", "PLAYER_TYPE"]
    return frame.drop_duplicates(keys, keep="last").copy()


def select_result_rows(
    results: pd.DataFrame,
    player: object,
    sport: str,
    column: str,
) -> pd.DataFrame:
    rows = results.loc[results["_player_key"] == normalize_name(player)].copy()
    if sport == "MLB" and "PLAYER_TYPE" in rows.columns:
        expected = "PITCHER" if column in MLB_PITCHER_COLUMNS else "HITTER"
        rows = rows.loc[rows["PLAYER_TYPE"].astype(str).str.upper() == expected]
    return rows


def numeric_value(row: pd.Series, column: str) -> float | None:
    if column not in row.index:
        return None
    value = pd.to_numeric(pd.Series([row[column]]), errors="coerce").iloc[0]
    return None if pd.isna(value) else float(value)


def opportunity_fields(sport: str, row: pd.Series) -> dict[str, object]:
    if sport == "WNBA":
        minutes = numeric_value(row, "MIN")
        return {
            "minutes": minutes,
            "plate_appearances": None,
            "innings": None,
            "pitch_count": None,
            "batters_faced": None,
            "opportunity_received": f"MIN={minutes:g}" if minutes is not None else "MIN=UNKNOWN",
        }
    player_type = str(row.get("PLAYER_TYPE", "")).upper()
    pa = numeric_value(row, "PA") if player_type == "HITTER" else None
    innings = numeric_value(row, "IP") if player_type == "PITCHER" else None
    pitches = numeric_value(row, "PITCHES") if player_type == "PITCHER" else None
    if player_type == "PITCHER":
        details = f"IP={innings:g};PITCHES={pitches:g}" if innings is not None and pitches is not None else "PITCHER_WORKLOAD_PARTIAL"
    else:
        details = f"PA={pa:g}" if pa is not None else "PA=UNKNOWN"
    return {
        "minutes": None,
        "plate_appearances": pa,
        "innings": innings,
        "pitch_count": pitches,
        "batters_faced": None,
        "opportunity_received": details,
    }


def resolve_snapshot(snapshot_id: str, results_path: Path) -> dict[str, int]:
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
    dates = decisions["slate_date"].dropna().astype(str).unique()
    sports = decisions["sport"].dropna().astype(str).str.upper().unique()
    if len(dates) != 1 or len(sports) != 1:
        raise ValueError("Snapshot must contain exactly one slate date and sport")
    sport, slate_date = sports[0], dates[0]
    if sport not in {"WNBA", "MLB"}:
        raise ValueError(f"Unsupported sport: {sport}")
    results = load_results(results_path, sport, slate_date)
    counts = {label: 0 for label in ("HIT", "MISS", "PUSH", "PASS", "PENDING", "UNSUPPORTED")}
    resolved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sql = """
        INSERT INTO prop_results (
            decision_id, resolved_at, status, actual_value, margin,
            minutes, plate_appearances, innings, pitch_count, batters_faced,
            opportunity_received, result_notes, process_quality,
            model_change_required
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        ON CONFLICT(decision_id) DO UPDATE SET
            resolved_at=excluded.resolved_at, status=excluded.status,
            actual_value=excluded.actual_value, margin=excluded.margin,
            minutes=excluded.minutes, plate_appearances=excluded.plate_appearances,
            innings=excluded.innings, pitch_count=excluded.pitch_count,
            batters_faced=excluded.batters_faced,
            opportunity_received=excluded.opportunity_received,
            result_notes=excluded.result_notes,
            process_quality=excluded.process_quality
    """
    with connect() as connection:
        for _, decision in decisions.iterrows():
            column = result_column(sport, decision["prop_type"])
            if column is None:
                status = "UNSUPPORTED"
                values = (int(decision["decision_id"]), resolved_at, status, None, None,
                          None, None, None, None, None, "RESULT_MAPPING_UNAVAILABLE",
                          f"Unsupported {sport} prop type: {decision['prop_type']}", "UNREVIEWED")
                counts[status] += 1
                connection.execute(sql, values)
                continue
            rows = select_result_rows(results, decision["player"], sport, column)
            if len(rows) != 1:
                status = "PENDING"
                reason = "NO_RESULT_FOUND" if rows.empty else "AMBIGUOUS_RESULT"
                values = (int(decision["decision_id"]), resolved_at, status, None, None,
                          None, None, None, None, None, reason,
                          "No unique player result was matched; no result was guessed", "UNREVIEWED")
                counts[status] += 1
                connection.execute(sql, values)
                continue
            result = rows.iloc[0]
            actual = numeric_value(result, column)
            if actual is None:
                status = "UNSUPPORTED"
                values = (int(decision["decision_id"]), resolved_at, status, None, None,
                          None, None, None, None, None, "RESULT_COLUMN_UNAVAILABLE",
                          f"Missing result column/value: {column}", "UNREVIEWED")
                counts[status] += 1
                connection.execute(sql, values)
                continue
            line = float(decision["line"])
            status = classify_status(decision["direction"], actual, line)
            opportunity = opportunity_fields(sport, result)
            values = (
                int(decision["decision_id"]), resolved_at, status, actual, actual - line,
                opportunity["minutes"], opportunity["plate_appearances"], opportunity["innings"],
                opportunity["pitch_count"], opportunity["batters_faced"],
                opportunity["opportunity_received"],
                f"Official {sport} player result matched by slate and player/type",
                "UNREVIEWED",
            )
            counts[status] += 1
            connection.execute(sql, values)
    return counts


def export_audit(snapshot_id: str, report_path: Path) -> int:
    with connect() as connection:
        frame = pd.read_sql_query(
            """
            SELECT d.*, r.status, r.actual_value, r.margin, r.minutes,
                   r.plate_appearances, r.innings, r.pitch_count,
                   r.opportunity_received, r.process_quality,
                   r.error_classification, r.model_change_required,
                   r.result_notes, r.resolved_at
            FROM model_decisions d
            LEFT JOIN prop_results r ON r.decision_id=d.decision_id
            WHERE d.snapshot_id=?
            ORDER BY d.overall_rank IS NULL, d.overall_rank, d.decision_id
            """,
            connection,
            params=(snapshot_id,),
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(report_path, index=False)
    return len(frame)


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve a full WNBA or MLB model snapshot")
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    counts = resolve_snapshot(args.snapshot_id, args.results)
    print("=" * 70)
    print("FULL-BOARD RESULT RESOLVER")
    print("=" * 70)
    print(f"Snapshot: {args.snapshot_id}")
    for label, count in counts.items():
        print(f"{label}: {count:,}")
    if args.report:
        print(f"Audit rows: {export_audit(args.snapshot_id, args.report):,}")
        print(f"Audit report: {args.report}")
    print("Process classifications remain UNREVIEWED; model weights are unchanged.")


if __name__ == "__main__":
    main()
