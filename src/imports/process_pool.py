from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INCOMING_DIR = PROJECT_ROOT / "data" / "pools" / "incoming"
PROCESSED_DIR = PROJECT_ROOT / "data" / "pools" / "processed"
ARCHIVE_DIR = PROJECT_ROOT / "data" / "pools" / "archive"

REQUIRED_COLUMNS = {
    "projection_id",
    "league",
    "player_name",
    "team",
    "stat_type",
    "line_score",
    "odds_type",
    "start_time",
}

SUPPORTED_SPORTS = {"MLB", "WNBA"}


def newest_csv() -> Path:
    files = list(INCOMING_DIR.glob("*.csv"))

    if not files:
        raise FileNotFoundError(
            f"No CSV files found in {INCOMING_DIR}"
        )

    return max(files, key=lambda path: path.stat().st_mtime)


def normalize_text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def process_pool(source_file: Path) -> tuple[Path, Path, pd.DataFrame]:
    dataframe = pd.read_csv(source_file)

    missing = REQUIRED_COLUMNS.difference(dataframe.columns)

    if missing:
        raise ValueError(
            "Pool is missing required columns: "
            + ", ".join(sorted(missing))
        )

    dataframe.columns = [
        column.strip().lower()
        for column in dataframe.columns
    ]

    for column in [
        "league",
        "player_name",
        "team",
        "position",
        "stat_type",
        "projection_type",
        "odds_type",
        "status",
    ]:
        if column in dataframe.columns:
            dataframe[column] = normalize_text(dataframe[column])

    dataframe["league"] = dataframe["league"].str.upper()
    dataframe["team"] = dataframe["team"].str.upper()
    dataframe["odds_type"] = dataframe["odds_type"].str.lower()

    dataframe["line_score"] = pd.to_numeric(
        dataframe["line_score"],
        errors="coerce",
    )

    dataframe["start_time"] = pd.to_datetime(
        dataframe["start_time"],
        errors="coerce",
        utc=True,
    )

    dataframe["captured_at_utc"] = pd.to_datetime(
        dataframe.get("captured_at_utc"),
        errors="coerce",
        utc=True,
    )

    dataframe = dataframe[
        dataframe["league"].isin(SUPPORTED_SPORTS)
    ].copy()

    dataframe = dataframe[
        dataframe["player_name"].ne("")
        & dataframe["stat_type"].ne("")
        & dataframe["line_score"].notna()
    ].copy()

    dataframe["line_tier"] = dataframe["odds_type"].map(
        {
            "standard": "STANDARD",
            "goblin": "GOBLIN",
            "demon": "DEMON",
        }
    ).fillna(dataframe["odds_type"].str.upper())

    dataframe["is_standard_line"] = (
        dataframe["odds_type"].eq("standard")
    )

    dataframe["slate_date"] = (
        dataframe["start_time"]
        .dt.tz_convert("America/Chicago")
        .dt.strftime("%Y-%m-%d")
    )

    dataframe["prop_key"] = (
        dataframe["league"]
        + "|"
        + dataframe["player_name"].str.lower()
        + "|"
        + dataframe["stat_type"].str.lower()
        + "|"
        + dataframe["line_score"].astype(str)
        + "|"
        + dataframe["odds_type"]
    )

    dataframe = dataframe.drop_duplicates(
        subset=["projection_id"],
        keep="last",
    )

    dataframe = dataframe.sort_values(
        [
            "league",
            "start_time",
            "player_name",
            "stat_type",
            "line_score",
        ],
        na_position="last",
    )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    processed_file = (
        PROCESSED_DIR
        / f"raymond_pool_{timestamp}.csv"
    )

    latest_file = PROCESSED_DIR / "raymond_pool_latest.csv"

    archive_file = (
        ARCHIVE_DIR
        / f"original_pool_{timestamp}.csv"
    )

    dataframe.to_csv(processed_file, index=False)
dataframe.to_csv(latest_file, index=False)

standard_columns = [
    "slate_date",
    "league",
    "player_name",
    "team",
    "position",
    "stat_type",
    "line_score",
    "start_time",
    "game_description",
    "projection_id",
    "player_id",
    "prop_key",
]

standard_board = dataframe[
    dataframe["is_standard_line"].eq(True)
].copy()

standard_board = standard_board[
    [
        column
        for column in standard_columns
        if column in standard_board.columns
    ]
]

standard_file = (
    PROCESSED_DIR
    / f"raymond_standard_board_{timestamp}.csv"
)

standard_latest_file = (
    PROCESSED_DIR
    / "raymond_standard_board_latest.csv"
)

standard_board.to_csv(standard_file, index=False)
standard_board.to_csv(standard_latest_file, index=False)

shutil.copy2(source_file, archive_file)

return (
    processed_file,
    latest_file,
    standard_file,
    standard_latest_file,
    dataframe,
    standard_board,
)

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize the newest PrizePicks CSV for Sports Hub."
    )

    parser.add_argument(
        "--file",
        type=Path,
        help="Optional specific CSV file. Defaults to newest incoming file.",
    )

    arguments = parser.parse_args()

    try:
        source_file = arguments.file or newest_csv()

        print(f"[INFO] Processing: {source_file}")

        (
   	 processed_file,
    	latest_file,
    	standard_file,
   	 standard_latest_file,
    	dataframe,
    		standard_board,
	) = process_pool(source_file)

        print(f"[SUCCESS] Imported {len(dataframe):,} MLB/WNBA projections.")

        print("\nSPORT COUNTS")
        print(dataframe["league"].value_counts().to_string())

        print("\nLINE-TIER COUNTS")
        print(dataframe["line_tier"].value_counts().to_string())

        print(f"\n[SAVED] {processed_file}")
        print(f"[LATEST] {latest_file}")

        return 0

    except Exception as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
