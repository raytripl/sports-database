from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from src.db import connect
from src.decisions.schema import initialize_schema


VALID_STATUSES = {
    "ACTIVE",
    "AVAILABLE",
    "PROBABLE",
    "QUESTIONABLE",
    "DOUBTFUL",
    "OUT",
    "UNKNOWN",
}

REQUIRED_COLUMNS = {
    "player",
    "team",
    "injury_status",
    "captured_at",
    "source",
}

LIVE_FLAG_PATTERN = re.compile(r"(?:^|; )LIVE_AVAILABILITY\[[^]]*\]")


def normalize_name(value: object) -> str:
    text = str(value).strip().lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def clean_text(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def optional_bool(value: object) -> int | None:
    text = clean_text(value)
    if text is None:
        return None
    normalized = text.lower()
    if normalized in {"1", "true", "yes", "y", "confirmed"}:
        return 1
    if normalized in {"0", "false", "no", "n", "unconfirmed"}:
        return 0
    raise ValueError(f"Invalid boolean value: {value}")


def optional_float(value: object) -> float | None:
    if pd.isna(value) or clean_text(value) is None:
        return None
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        raise ValueError(f"Invalid numeric value: {value}")
    return float(number)


def availability_flags(
    injury_status: str,
    lineup_confirmed: int | None,
    minutes_restriction: str | None,
) -> list[str]:
    flags: list[str] = []
    if injury_status == "OUT":
        flags.append("HARD_VETO_OUT")
    elif injury_status == "DOUBTFUL":
        flags.append("HARD_VETO_DOUBTFUL")
    elif injury_status == "QUESTIONABLE":
        flags.append("HARD_VETO_QUESTIONABLE")
    elif injury_status == "UNKNOWN":
        flags.append("HARD_VETO_UNKNOWN_STATUS")

    if lineup_confirmed != 1:
        flags.append("HARD_VETO_UNCONFIRMED_LINEUP")
    if minutes_restriction:
        flags.append("HARD_VETO_MINUTES_RESTRICTION")
    return flags


def replace_live_flag(existing: object, flags: list[str]) -> str | None:
    text = clean_text(existing) or ""
    text = LIVE_FLAG_PATTERN.sub("", text).strip("; ")
    if flags:
        live = "LIVE_AVAILABILITY[" + "|".join(flags) + "]"
        text = f"{text}; {live}" if text else live
    return text or None


def load_availability(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Availability file not found: {path}")
    frame = pd.read_csv(path)
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError("Availability file is missing columns: " + ", ".join(missing))
    for optional in (
        "lineup_confirmed",
        "starter_confirmed",
        "expected_minutes",
        "minutes_restriction",
        "notes",
    ):
        if optional not in frame.columns:
            frame[optional] = pd.NA
    return frame


def filter_availability_to_slate(frame: pd.DataFrame, slate_date: str) -> pd.DataFrame:
    if "game_date" not in frame.columns:
        return frame.copy()
    dates = pd.to_datetime(frame["game_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return frame.loc[dates.eq(slate_date)].copy()


def enrich_snapshot(snapshot_id: str, availability_path: Path) -> dict[str, int]:
    initialize_schema()
    availability = load_availability(availability_path)

    with connect() as connection:
        decisions = pd.read_sql_query(
            """
            SELECT decision_id, slate_date, sport, player, team, red_flags
            FROM model_decisions
            WHERE snapshot_id = ?
            """,
            connection,
            params=(snapshot_id,),
        )

    if decisions.empty:
        raise ValueError(f"No decisions found for snapshot: {snapshot_id}")
    if set(decisions["sport"].str.upper()) != {"WNBA"}:
        raise ValueError("This enrichment currently supports WNBA snapshots only")
    slate_dates = decisions["slate_date"].astype(str).unique()
    if len(slate_dates) != 1:
        raise ValueError("Snapshot must contain one slate date")
    slate_date = slate_dates[0]
    availability = filter_availability_to_slate(availability, slate_date)

    decisions["_player_key"] = decisions["player"].map(normalize_name)
    key_to_decisions = {
        key: group for key, group in decisions.groupby("_player_key", sort=False)
    }

    counts = {
        "official_rows": len(availability),
        "players_matched": 0,
        "props_updated": 0,
        "players_unmatched": 0,
    }

    with connect() as connection:
        for _, row in availability.iterrows():
            player = clean_text(row["player"])
            team = clean_text(row["team"])
            source = clean_text(row["source"])
            captured_at = clean_text(row["captured_at"])
            if not all((player, source, captured_at)):
                raise ValueError("player, captured_at, and source cannot be blank")

            status = (clean_text(row["injury_status"]) or "UNKNOWN").upper()
            if status not in VALID_STATUSES:
                raise ValueError(f"Invalid injury status for {player}: {status}")

            lineup = optional_bool(row["lineup_confirmed"])
            starter = optional_bool(row["starter_confirmed"])
            expected_minutes = optional_float(row["expected_minutes"])
            restriction = clean_text(row["minutes_restriction"])
            notes = clean_text(row["notes"])

            connection.execute(
                """
                INSERT INTO wnba_availability_snapshots (
                    snapshot_id, slate_date, captured_at, player, team,
                    injury_status, lineup_confirmed, starter_confirmed,
                    expected_minutes, minutes_restriction, source, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_id, player, captured_at, source) DO UPDATE SET
                    team = excluded.team,
                    injury_status = excluded.injury_status,
                    lineup_confirmed = excluded.lineup_confirmed,
                    starter_confirmed = excluded.starter_confirmed,
                    expected_minutes = excluded.expected_minutes,
                    minutes_restriction = excluded.minutes_restriction,
                    notes = excluded.notes
                """,
                (
                    snapshot_id, slate_date, captured_at, player, team, status,
                    lineup, starter, expected_minutes, restriction, source, notes,
                ),
            )

            matches = key_to_decisions.get(normalize_name(player))
            if matches is None or matches.empty:
                counts["players_unmatched"] += 1
                continue

            counts["players_matched"] += 1
            flags = availability_flags(status, lineup, restriction)
            for _, decision in matches.iterrows():
                red_flags = replace_live_flag(decision["red_flags"], flags)
                cursor = connection.execute(
                    """
                    UPDATE model_decisions
                    SET lineup_confirmed = ?, starter_confirmed = ?,
                        injury_status = ?, minutes_restriction = ?,
                        expected_minutes = COALESCE(?, expected_minutes),
                        red_flags = ?, recommended = 0
                    WHERE decision_id = ?
                    """,
                    (
                        lineup, starter, status, restriction, expected_minutes,
                        red_flags, int(decision["decision_id"]),
                    ),
                )
                counts["props_updated"] += cursor.rowcount

    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply verified WNBA availability to a decision snapshot."
    )
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--availability", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    counts = enrich_snapshot(args.snapshot_id, args.availability)
    print("=" * 70)
    print("WNBA LIVE AVAILABILITY ENRICHMENT")
    print("=" * 70)
    for key, value in counts.items():
        print(f"{key}: {value:,}")
    print("Recommendations remain disabled; this phase never raises grades.")


if __name__ == "__main__":
    main()
