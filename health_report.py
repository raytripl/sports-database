from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "sports.db"
EXPORT_DIR = DATA_DIR / "exports"


def format_size(size_bytes: int) -> str:
    size = float(size_bytes)

    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024

    return f"{size:.1f} TB"


def sqlite_tables() -> list[tuple[str, int]]:
    if not DB_PATH.exists():
        return []

    rows: list[tuple[str, int]] = []

    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()

        table_names = cursor.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
            """
        ).fetchall()

        for (table_name,) in table_names:
            count = cursor.execute(
                f'SELECT COUNT(*) FROM "{table_name}"'
            ).fetchone()[0]

            rows.append((table_name, count))

    return rows


def print_file_report() -> None:
    print()
    print("=" * 78)
    print("GENERATED FILES")
    print("=" * 78)

    files = sorted(
        file
        for file in DATA_DIR.rglob("*")
        if file.is_file() and file.name != ".gitkeep"
    )

    if not files:
        print("No generated files found.")
        return

    for file in files:
        stat = file.stat()
        modified = datetime.fromtimestamp(
            stat.st_mtime
        ).strftime("%Y-%m-%d %I:%M:%S %p")

        relative_path = file.relative_to(PROJECT_ROOT)

        print(
            f"{str(relative_path):55} "
            f"{format_size(stat.st_size):>10}  "
            f"{modified}"
        )


def main() -> None:
    print()
    print("=" * 78)
    print("RAYMOND SPORTS DATABASE HEALTH REPORT")
    print("=" * 78)

    print(f"Project: {PROJECT_ROOT}")
    print(f"Database: {DB_PATH}")

    if DB_PATH.exists():
        print(f"Database size: {format_size(DB_PATH.stat().st_size)}")
    else:
        print("Database status: MISSING")

    print()
    print("=" * 78)
    print("SQLITE TABLES")
    print("=" * 78)

    tables = sqlite_tables()

    if not tables:
        print("No SQLite tables found.")
    else:
        for table_name, row_count in tables:
            print(f"{table_name:40} {row_count:>12,} rows")

    print_file_report()


if __name__ == "__main__":
    main()
