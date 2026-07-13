from __future__ import annotations

import argparse
import hashlib
import re
import unicodedata
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.db import connect
from src.tennis.schema import initialize_tennis_schema


REQUIRED = {
    "projection_id", "league", "player_name", "stat_type", "line_score",
    "odds_type", "start_time",
}


def player_key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def clean(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def find_latest_tennis_export(directory: Path) -> Path:
    candidates = sorted(directory.rglob("*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            frame = pd.read_csv(path, usecols=lambda column: str(column).strip().lower() == "league")
        except (OSError, ValueError, pd.errors.ParserError):
            continue
        if not frame.empty and frame.iloc[:, 0].fillna("").astype(str).str.upper().eq("TENNIS").any():
            return path
    raise FileNotFoundError(f"No Tennis PrizePicks CSV found under {directory}")


def load_tennis_rows(pool_path: Path) -> pd.DataFrame:
    frame = pd.read_csv(pool_path, low_memory=False)
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    if missing := sorted(REQUIRED - set(frame.columns)):
        raise ValueError("Tennis pool missing columns: " + ", ".join(missing))
    frame = frame[frame["league"].fillna("").astype(str).str.upper().eq("TENNIS")].copy()
    frame["line_score"] = pd.to_numeric(frame["line_score"], errors="coerce")
    frame = frame[
        frame["player_name"].fillna("").astype(str).str.strip().ne("")
        & frame["stat_type"].fillna("").astype(str).str.strip().ne("")
        & frame["line_score"].notna()
    ].copy()
    if frame.empty:
        raise ValueError("No usable Tennis rows found")
    return frame.drop_duplicates("projection_id", keep="last")


def capture_pool(pool_path: Path) -> dict[str, object]:
    initialize_tennis_schema()
    frame = load_tennis_rows(pool_path)
    digest = hashlib.sha256(pool_path.read_bytes()).hexdigest()
    capture_id = digest[:16]
    captured = pd.to_datetime(frame.get("captured_at_utc"), errors="coerce", utc=True)
    captured_at = (
        captured.dropna().max().isoformat()
        if captured is not None and captured.notna().any()
        else datetime.fromtimestamp(pool_path.stat().st_mtime, tz=timezone.utc).isoformat()
    )
    starts = pd.to_datetime(frame["start_time"], errors="coerce", utc=True)
    frame["_slate_date"] = starts.dt.tz_convert("America/Chicago").dt.strftime("%Y-%m-%d")
    standard = frame["odds_type"].fillna("").astype(str).str.lower().eq("standard")

    with closing(connect()) as connection:
        with connection:
            connection.execute(
                """INSERT OR IGNORE INTO tennis_captures
                   (capture_id, captured_at, source_file, source_sha256, total_rows, standard_rows,
                    model_status, recommendations_enabled)
                   VALUES (?, ?, ?, ?, ?, ?, 'RESEARCH_ONLY', 0)""",
                (capture_id, captured_at, pool_path.name, digest, len(frame), int(standard.sum())),
            )
            inserted = 0
            for index, row in frame.iterrows():
                name = str(row["player_name"]).strip()
                opponent = clean(row.get("game_description")) or clean(row.get("description"))
                key = player_key(name)
                opponent_key = player_key(opponent) if opponent else None
                connection.execute(
                    """INSERT INTO tennis_players
                       (player_key, display_name, prizepicks_player_id, first_seen_at, last_seen_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(player_key) DO UPDATE SET
                         display_name=excluded.display_name,
                         prizepicks_player_id=COALESCE(excluded.prizepicks_player_id, tennis_players.prizepicks_player_id),
                         last_seen_at=excluded.last_seen_at""",
                    (key, name, clean(row.get("player_id")), captured_at, captured_at),
                )
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO tennis_prop_lines
                       (capture_id, projection_id, captured_at, slate_date, start_time,
                        player_key, player_name, prizepicks_player_id, opponent_key, opponent_name,
                        prop_type, line, odds_type, line_tier, is_standard_line, projection_type,
                        status, direction, grade, recommended, decision_reason, source_file)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                               'PASS', 'UNSUPPORTED', 0,
                               'Tennis research capture only; no validated scoring model', ?)""",
                    (
                        capture_id, str(row["projection_id"]), captured_at, clean(row["_slate_date"]),
                        clean(row.get("start_time")), key, name, clean(row.get("player_id")),
                        opponent_key, opponent, str(row["stat_type"]).strip(), float(row["line_score"]),
                        clean(row.get("odds_type")), str(row.get("odds_type") or "").upper(),
                        int(str(row.get("odds_type") or "").lower() == "standard"),
                        clean(row.get("projection_type")), clean(row.get("status")), pool_path.name,
                    ),
                )
                inserted += cursor.rowcount
    return {
        "capture_id": capture_id, "pool": str(pool_path), "rows": len(frame),
        "standard_rows": int(standard.sum()), "players": frame["player_name"].nunique(),
        "rows_inserted": inserted, "recommendations_enabled": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture Tennis PrizePicks lines for research")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pool", type=Path)
    group.add_argument("--directory", type=Path)
    args = parser.parse_args()
    pool = args.pool or find_latest_tennis_export(args.directory)
    result = capture_pool(pool)
    print("=" * 70)
    print("SPORTS HUB TENNIS PROP FOUNDATION")
    print("=" * 70)
    for key, value in result.items():
        print(f"{key}: {value}")
    print("All Tennis rows remain PASS/UNSUPPORTED; recommendations are disabled.")


if __name__ == "__main__":
    main()
