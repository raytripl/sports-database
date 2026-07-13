from __future__ import annotations

import argparse
import shutil
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from nba_api.stats.endpoints import leaguegamelog

from src.wnba.results import add_model_columns


KEEP_COLUMNS = [
    "GAME_ID", "GAME_DATE", "PLAYER_ID", "PLAYER_NAME", "TEAM_ID",
    "TEAM_ABBREVIATION", "MATCHUP", "MIN", "PTS", "REB", "AST", "PRA",
    "PTS_REB", "PTS_AST", "REB_AST", "OREB", "DREB", "FGM", "FGA",
    "FG3M", "FG3A", "FG2M", "FG2A", "FTM", "FTA", "STL", "BLK",
    "STOCKS", "TOV", "FANTASY_SCORE_PP",
]


def download_history(
    season: str,
    date_from: str,
    date_to: str,
    attempts: int = 3,
) -> pd.DataFrame:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = leaguegamelog.LeagueGameLog(
                league_id="10",
                season=season,
                season_type_all_star="Regular Season",
                player_or_team_abbreviation="P",
                date_from_nullable=date_from,
                date_to_nullable=date_to,
                timeout=90,
            )
            return response.get_data_frames()[0]
        except Exception as exc:  # pragma: no cover - network behavior
            last_error = exc
            if attempt < attempts:
                time.sleep(attempt * 3)
    raise RuntimeError(f"WNBA history download failed after {attempts} attempts") from last_error


def prepare_history(frame: pd.DataFrame, through: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError("WNBA endpoint returned no player games")
    result = add_model_columns(frame)
    result["FG2M"] = result["FGM"] - result["FG3M"]
    result["FG2A"] = result["FGA"] - result["FG3A"]
    for column in KEEP_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
    result = result[KEEP_COLUMNS].copy()
    result["GAME_DATE"] = pd.to_datetime(result["GAME_DATE"], errors="coerce")
    result = result[result["GAME_DATE"].notna()].copy()
    result = result[result["GAME_DATE"] <= pd.Timestamp(through)].copy()
    result = result.drop_duplicates(subset=["GAME_ID", "PLAYER_ID"], keep="last")
    result = result.sort_values(["GAME_DATE", "GAME_ID", "PLAYER_NAME"])
    result["GAME_DATE"] = result["GAME_DATE"].dt.strftime("%Y-%m-%d")
    if result.empty:
        raise ValueError("No valid pre-cutoff WNBA player games remained")
    return result


def write_history(frame: pd.DataFrame, output: Path, backup_dir: Path) -> Path | None:
    output.parent.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if output.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = backup_dir / f"{output.stem}_{stamp}{output.suffix}"
        shutil.copy2(output, backup)
    temporary = output.with_suffix(output.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(output)
    return backup


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill WNBA player-game history.")
    parser.add_argument("--season", required=True)
    parser.add_argument("--from-date", required=True, help="MM/DD/YYYY")
    parser.add_argument("--through", required=True, help="MM/DD/YYYY")
    parser.add_argument(
        "--output", type=Path, default=Path("data/wnba/WNBA_RESULTS_HISTORY.csv")
    )
    parser.add_argument(
        "--backup-dir", type=Path, default=Path("backups/wnba_history")
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raw = download_history(args.season, args.from_date, args.through)
    history = prepare_history(raw, args.through)
    backup = write_history(history, args.output, args.backup_dir)
    dates = pd.to_datetime(history["GAME_DATE"])
    print("=" * 70)
    print("WNBA HISTORICAL BACKFILL")
    print("=" * 70)
    print(f"Player games: {len(history):,}")
    print(f"Players: {history['PLAYER_ID'].nunique():,}")
    print(f"Games: {history['GAME_ID'].nunique():,}")
    print(f"Range: {dates.min().date()} through {dates.max().date()}")
    print(f"Saved: {args.output}")
    print(f"Backup: {backup or 'none'}")


if __name__ == "__main__":
    main()
