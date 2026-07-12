from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "sports.db"


SQLITE_REQUIREMENTS = {
    "nba_player_game_logs": 100,
    "nba_players": 100,
    "nba_teams": 30,
    "nfl_weekly_player_stats": 100,
    "nfl_schedules": 100,
    "nfl_rosters": 100,
    "soccer_matches": 1,
    "tennis_matches": 1,
    "nhl_schedule": 1,
}


CSV_REQUIREMENTS = {
    DATA_DIR / "mlb" / "MLB_BATTING_RESULTS.csv": 1,
    DATA_DIR / "mlb" / "MLB_PITCHING_RESULTS.csv": 1,
    DATA_DIR / "mlb" / "MLB_RECENT_UPDATE.csv": 1,
    DATA_DIR / "mlb" / "MLB_MODEL_DATABASE.csv": 1,
    DATA_DIR / "mlb" / "MLB_RESULTS_HISTORY.csv": 1,
    DATA_DIR / "wnba" / "WNBA_RESULTS_HISTORY.csv": 1,
}


def validate_sqlite() -> list[str]:
    errors: list[str] = []

    print()
    print("=" * 72)
    print("VALIDATING SQLITE TABLES")
    print("=" * 72)

    if not DB_PATH.exists():
        errors.append(f"Missing database: {DB_PATH}")
        print(f"[FAILED] Missing database: {DB_PATH}")
        return errors

    with sqlite3.connect(DB_PATH) as connection:
        existing_tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        }

        for table_name, minimum_rows in SQLITE_REQUIREMENTS.items():
            if table_name not in existing_tables:
                message = f"Missing SQLite table: {table_name}"
                errors.append(message)
                print(f"[FAILED] {message}")
                continue

            row_count = connection.execute(
                f'SELECT COUNT(*) FROM "{table_name}"'
            ).fetchone()[0]

            if row_count < minimum_rows:
                message = (
                    f"{table_name} has {row_count:,} rows; "
                    f"minimum required is {minimum_rows:,}"
                )
                errors.append(message)
                print(f"[FAILED] {message}")
            else:
                print(
                    f"[PASS] {table_name}: "
                    f"{row_count:,} rows"
                )

    return errors


def validate_csv_files() -> list[str]:
    errors: list[str] = []

    print()
    print("=" * 72)
    print("VALIDATING MLB AND WNBA CSV FILES")
    print("=" * 72)

    for file_path, minimum_rows in CSV_REQUIREMENTS.items():
        relative_path = file_path.relative_to(PROJECT_ROOT)

        if not file_path.exists():
            message = f"Missing CSV file: {relative_path}"
            errors.append(message)
            print(f"[FAILED] {message}")
            continue

        if file_path.stat().st_size == 0:
            message = f"Empty CSV file: {relative_path}"
            errors.append(message)
            print(f"[FAILED] {message}")
            continue

        try:
            dataframe = pd.read_csv(file_path)
        except Exception as error:
            message = f"Could not read {relative_path}: {error}"
            errors.append(message)
            print(f"[FAILED] {message}")
            continue

        row_count = len(dataframe)

        if row_count < minimum_rows:
            message = (
                f"{relative_path} has {row_count:,} rows; "
                f"minimum required is {minimum_rows:,}"
            )
            errors.append(message)
            print(f"[FAILED] {message}")
        else:
            print(
                f"[PASS] {relative_path}: "
                f"{row_count:,} rows"
            )

    return errors


def main() -> int:
    print()
    print("=" * 72)
    print("RAYMOND SPORTS DATABASE VALIDATION")
    print("=" * 72)

    errors = []
    errors.extend(validate_sqlite())
    errors.extend(validate_csv_files())

    print()
    print("=" * 72)
    print("VALIDATION SUMMARY")
    print("=" * 72)

    if errors:
        print(f"Validation failed with {len(errors)} problem(s):")

        for error in errors:
            print(f" - {error}")

        return 1

    print("All required datasets passed validation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
