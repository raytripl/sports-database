from pathlib import Path
import sqlite3
import pandas as pd

DB_PATH = Path("data/sports.db")
EXPORT_DIR = Path("data/exports")

def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)

def save_frame(df: pd.DataFrame, table: str, mode: str = "replace") -> None:
    if df is None or df.empty:
        print(f"[SKIP] {table}: no rows")
        return

    normalized = df.copy()
    normalized.columns = [
        str(c).strip().lower().replace(" ", "_").replace("/", "_")
        for c in normalized.columns
    ]

    with connect() as conn:
        normalized.to_sql(table, conn, if_exists=mode, index=False)

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(EXPORT_DIR / f"{table}.csv", index=False)
    print(f"[SAVED] {table}: {len(normalized):,} rows")
