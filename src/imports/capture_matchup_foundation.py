from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.db import connect
from src.decisions.schema import initialize_schema


REQUIRED_COLUMNS = {
    "player_name",
    "team",
    "position",
    "stat_type",
    "line_score",
    "game_description",
    "captured_at_utc",
    "slate_date",
    "source",
}


def clean_text(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def prepare_pool(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError("Pool is missing columns: " + ", ".join(missing))
    result = frame.copy()
    result["line_score"] = pd.to_numeric(result["line_score"], errors="coerce")
    result = result.dropna(subset=["player_name", "stat_type", "line_score"])
    return result.drop_duplicates(
        subset=[
            "captured_at_utc",
            "slate_date",
            "player_name",
            "stat_type",
            "line_score",
            "source",
        ],
        keep="last",
    ).copy()


def ensure_foundation_schema() -> None:
    initialize_schema()
    with connect() as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(model_decisions)")
        }
        if "player_position" not in columns:
            connection.execute(
                "ALTER TABLE model_decisions ADD COLUMN player_position TEXT"
            )
        connection.execute("DROP INDEX IF EXISTS idx_unique_historical_prop_capture")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_historical_prop_capture
            ON historical_prop_lines (
                captured_at, slate_date, sport, player, prop_type, line,
                COALESCE(line_tier, ''), COALESCE(capture_id, ''), source
            )
            """
        )
        # Conservative legacy backfill: only copy metadata when the decision log
        # has one unambiguous tier for the exact captured market.
        connection.execute(
            """
            UPDATE historical_prop_lines AS h
            SET line_tier = (
                    SELECT MIN(d.line_tier) FROM model_decisions d
                    WHERE d.slate_date = h.slate_date AND d.sport = h.sport
                      AND d.player = h.player AND d.prop_type = h.prop_type
                      AND d.line = h.line
                ),
                is_standard_line = COALESCE((
                    SELECT MIN(d.is_standard_line) FROM model_decisions d
                    WHERE d.slate_date = h.slate_date AND d.sport = h.sport
                      AND d.player = h.player AND d.prop_type = h.prop_type
                      AND d.line = h.line
                    HAVING COUNT(DISTINCT COALESCE(d.line_tier, '')) = 1
                ), 0),
                projection_type = (
                    SELECT MIN(d.projection_type) FROM model_decisions d
                    WHERE d.slate_date = h.slate_date AND d.sport = h.sport
                      AND d.player = h.player AND d.prop_type = h.prop_type
                      AND d.line = h.line
                    HAVING COUNT(DISTINCT COALESCE(d.line_tier, '')) = 1
                )
            WHERE h.line_tier IS NULL
              AND EXISTS (
                  SELECT COUNT(*) FROM model_decisions d
                  WHERE d.slate_date = h.slate_date AND d.sport = h.sport
                    AND d.player = h.player AND d.prop_type = h.prop_type
                    AND d.line = h.line
                  HAVING COUNT(DISTINCT COALESCE(d.line_tier, '')) = 1
              )
            """
        )


def capture(snapshot_id: str, pool_path: Path, sport: str) -> dict[str, int]:
    if not pool_path.exists():
        raise FileNotFoundError(f"Pool not found: {pool_path}")
    frame = prepare_pool(pd.read_csv(pool_path))
    if "league" in frame.columns:
        frame = frame[
            frame["league"].fillna("").astype(str).str.upper() == sport.upper()
        ].copy()
        if frame.empty:
            raise ValueError(f"Pool contains no rows for sport: {sport}")
    ensure_foundation_schema()

    positions_updated = 0
    lines_inserted = 0
    insert_line = """
        INSERT OR IGNORE INTO historical_prop_lines (
            captured_at, slate_date, sport, player, team, opponent,
            prop_type, line, over_odds, under_odds, source,
            line_tier, is_standard_line, projection_type, odds_type,
            payout_modifier, capture_id, is_opening_line, is_closing_line
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
    """

    with connect() as connection:
        snapshot_count = connection.execute(
            "SELECT COUNT(*) FROM model_decisions WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()[0]
        if snapshot_count == 0:
            raise ValueError(f"No decisions found for snapshot: {snapshot_id}")

        for _, row in frame.iterrows():
            player = clean_text(row["player_name"])
            prop_type = clean_text(row["stat_type"])
            position = clean_text(row["position"])
            line = float(row["line_score"])
            cursor = connection.execute(
                """
                UPDATE model_decisions
                SET player_position = ?
                WHERE snapshot_id = ? AND player = ?
                  AND prop_type = ? AND line = ?
                """,
                (position, snapshot_id, player, prop_type, line),
            )
            positions_updated += cursor.rowcount

            cursor = connection.execute(
                insert_line,
                (
                    clean_text(row["captured_at_utc"]),
                    clean_text(row["slate_date"]),
                    sport.upper(),
                    player,
                    clean_text(row["team"]),
                    clean_text(row["game_description"]),
                    prop_type,
                    line,
                    clean_text(row.get("over_odds")),
                    clean_text(row.get("under_odds")),
                    clean_text(row["source"]) or str(pool_path),
                    clean_text(row.get("line_tier")),
                    int(bool(row.get("is_standard_line", False))),
                    clean_text(row.get("projection_type")),
                    clean_text(row.get("odds_type")),
                    pd.to_numeric(row.get("payout_modifier"), errors="coerce")
                    if pd.notna(row.get("payout_modifier")) else None,
                    clean_text(row.get("capture_id"))
                    or clean_text(row.get("source_export_file"))
                    or snapshot_id,
                ),
            )
            lines_inserted += cursor.rowcount

    return {
        "pool_rows": len(frame),
        "positions_updated": positions_updated,
        "lines_inserted": lines_inserted,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture player positions and historical prop lines."
    )
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--pool", required=True, type=Path)
    parser.add_argument("--sport", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    counts = capture(args.snapshot_id, args.pool, args.sport)
    print("=" * 70)
    print("MATCHUP DATA FOUNDATION")
    print("=" * 70)
    for key, value in counts.items():
        print(f"{key}: {value:,}")
    print("No matchup grades were created; this phase captures prerequisites only.")


if __name__ == "__main__":
    main()
