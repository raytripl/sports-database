from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from src.db import connect
from src.decisions.schema import initialize_schema
from src.decisions.score_mlb_decision_board import PITCHER_COLUMNS, result_column


LIVE_PATTERN = re.compile(r"(?:^|; )MLB_LIVE\[[^]]*\]")
POSTPONED = {"POSTPONED", "CANCELLED", "SUSPENDED"}


def normalize_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def clean(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def optional_int(value: object) -> int | None:
    if pd.isna(value) or clean(value) is None:
        return None
    return int(float(value))


def replace_flags(existing: object, flags: list[str]) -> str | None:
    text = LIVE_PATTERN.sub("", clean(existing) or "").strip("; ")
    live = "MLB_LIVE[" + "|".join(flags) + "]"
    return f"{text}; {live}" if text else live


def live_flags(role: str, row: pd.Series) -> list[str]:
    flags: list[str] = []
    status = (clean(row.get("game_status")) or "UNKNOWN").upper()
    if status in POSTPONED:
        flags.append("HARD_VETO_GAME_STATUS")
    if role == "PITCHER":
        if optional_int(row.get("starter_confirmed")) != 1:
            flags.append("HARD_VETO_UNCONFIRMED_STARTER")
        flags.append("HARD_VETO_K_RATE_NOT_VERIFIED")
    else:
        if optional_int(row.get("lineup_confirmed")) != 1:
            flags.append("HARD_VETO_UNCONFIRMED_LINEUP")
        if optional_int(row.get("batting_order")) is None:
            flags.append("HARD_VETO_MISSING_BATTING_ORDER")
    if clean(row.get("weather_condition")) is None:
        flags.append("WEATHER_NOT_AVAILABLE")
    return flags


def initialize_live_schema() -> None:
    initialize_schema()
    with connect() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS mlb_live_context_snapshots (
                context_id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT NOT NULL, slate_date TEXT NOT NULL,
                captured_at TEXT NOT NULL, game_id TEXT, game_status TEXT,
                player TEXT NOT NULL, player_id TEXT, player_role TEXT NOT NULL,
                team TEXT, opponent TEXT, lineup_confirmed INTEGER,
                batting_order INTEGER, starter_confirmed INTEGER, venue TEXT,
                weather_condition TEXT, temperature REAL, wind TEXT,
                source TEXT NOT NULL,
                UNIQUE(snapshot_id, player, captured_at, source)
            )
        """)


def enrich_snapshot(snapshot_id: str, context_path: Path) -> dict[str, int]:
    initialize_live_schema()
    context = pd.read_csv(context_path)
    required = {"slate_date", "captured_at", "player", "player_role", "source"}
    if missing := sorted(required - set(context.columns)):
        raise ValueError("MLB context missing columns: " + ", ".join(missing))
    with connect() as connection:
        decisions = pd.read_sql_query(
            "SELECT decision_id, player, prop_type, red_flags, sport FROM model_decisions WHERE snapshot_id = ?",
            connection, params=(snapshot_id,),
        )
    if decisions.empty:
        raise ValueError(f"No decisions found for snapshot: {snapshot_id}")
    if set(decisions["sport"].str.upper()) != {"MLB"}:
        raise ValueError("MLB live enrichment only supports MLB snapshots")

    context["_key"] = context["player"].map(normalize_name)
    lookup = {key: group.iloc[-1] for key, group in context.groupby("_key", sort=False)}
    counts = {"players_matched": 0, "props_updated": 0, "props_unmatched": 0}

    with connect() as connection:
        for _, row in context.iterrows():
            connection.execute("""
                INSERT INTO mlb_live_context_snapshots (
                    snapshot_id, slate_date, captured_at, game_id, game_status,
                    player, player_id, player_role, team, opponent,
                    lineup_confirmed, batting_order, starter_confirmed, venue,
                    weather_condition, temperature, wind, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_id, player, captured_at, source) DO NOTHING
            """, (
                snapshot_id, clean(row.get("slate_date")), clean(row.get("captured_at")),
                clean(row.get("game_id")), clean(row.get("game_status")), clean(row.get("player")),
                clean(row.get("player_id")), clean(row.get("player_role")), clean(row.get("team")),
                clean(row.get("opponent")), optional_int(row.get("lineup_confirmed")),
                optional_int(row.get("batting_order")), optional_int(row.get("starter_confirmed")),
                clean(row.get("venue")), clean(row.get("weather_condition")),
                row.get("temperature") if not pd.isna(row.get("temperature")) else None,
                clean(row.get("wind")), clean(row.get("source")),
            ))

        for _, decision in decisions.iterrows():
            live = lookup.get(normalize_name(decision["player"]))
            column = result_column(decision["prop_type"])
            role = "PITCHER" if column in PITCHER_COLUMNS else "HITTER"
            if live is None or str(live.get("player_role", "")).upper() != role:
                flags = ["HARD_VETO_MISSING_LIVE_CONTEXT"]
                if role == "PITCHER":
                    flags.append("HARD_VETO_K_RATE_NOT_VERIFIED")
                counts["props_unmatched"] += 1
                lineup = order = starter = None
            else:
                flags = live_flags(role, live)
                lineup = optional_int(live.get("lineup_confirmed"))
                order = optional_int(live.get("batting_order"))
                starter = optional_int(live.get("starter_confirmed"))
                counts["players_matched"] += 1
            red_flags = replace_flags(decision["red_flags"], flags)
            cursor = connection.execute("""
                UPDATE model_decisions SET lineup_confirmed = ?, batting_order = ?,
                    starter_confirmed = ?, red_flags = ?, recommended = 0
                WHERE decision_id = ?
            """, (lineup, order, starter, red_flags, int(decision["decision_id"])))
            counts["props_updated"] += cursor.rowcount
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply official MLB live context")
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--context", required=True, type=Path)
    args = parser.parse_args()
    counts = enrich_snapshot(args.snapshot_id, args.context)
    for key, value in counts.items():
        print(f"{key}: {value:,}")
    print("Recommendations remain disabled.")


if __name__ == "__main__":
    main()
