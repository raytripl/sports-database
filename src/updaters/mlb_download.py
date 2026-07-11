from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from pybaseball import statcast


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "mlb"


def download_recent_statcast(days_back: int = 10) -> pd.DataFrame:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    today = date.today()
    start_date = today - timedelta(days=days_back)

    print(
        f"Downloading MLB Statcast data "
        f"from {start_date} through {today}..."
    )

    df = statcast(
        str(start_date),
        str(today),
        verbose=True,
    )

    if df.empty:
        raise RuntimeError("No MLB Statcast data was downloaded.")

    df["game_date"] = df["game_date"].astype(str)

    latest_date = df["game_date"].max()
    expected_date = str(today - timedelta(days=1))

    print(f"Latest Statcast date: {latest_date}")
    print(f"Expected completed date: {expected_date}")
    print(f"Rows downloaded: {len(df):,}")

    if latest_date < expected_date:
        raise RuntimeError(
            f"Statcast is not current. Expected {expected_date}, "
            f"but newest date is {latest_date}."
        )

    output_file = DATA_DIR / "MLB_RECENT_UPDATE.csv"
    df.to_csv(output_file, index=False)

    print(f"Saved: {output_file}")

    return df


if __name__ == "__main__":
    download_recent_statcast()
