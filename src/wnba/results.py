from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from nba_api.stats.endpoints import leaguegamelog


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "wnba"


def get_wnba_results(game_date: str, season: str) -> pd.DataFrame:
    print(f"Downloading WNBA results for {game_date}...")

    data = leaguegamelog.LeagueGameLog(
        league_id="10",
        season=season,
        season_type_all_star="Regular Season",
        player_or_team_abbreviation="P",
        date_from_nullable=game_date,
        date_to_nullable=game_date,
        timeout=60,
    )

    return data.get_data_frames()[0]


def add_model_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    numeric_columns = [
        "PTS",
        "REB",
        "AST",
        "OREB",
        "DREB",
        "FGM",
        "FGA",
        "FG3M",
        "FG3A",
        "FTM",
        "FTA",
        "STL",
        "BLK",
        "TOV",
    ]

    for column in numeric_columns:
        if column not in df.columns:
            df[column] = 0

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        ).fillna(0)

    df["PRA"] = df["PTS"] + df["REB"] + df["AST"]
    df["PTS_REB"] = df["PTS"] + df["REB"]
    df["PTS_AST"] = df["PTS"] + df["AST"]
    df["REB_AST"] = df["REB"] + df["AST"]

    df["STOCKS"] = df["STL"] + df["BLK"]

    df["FANTASY_SCORE_PP"] = (
        df["PTS"]
        + (df["REB"] * 1.2)
        + (df["AST"] * 1.5)
        + (df["STL"] * 3)
        + (df["BLK"] * 3)
        - df["TOV"]
    )

    return df


def results_update() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    target_date = date.today() - timedelta(days=1)
    game_date = target_date.strftime("%m/%d/%Y")
    season = str(target_date.year)

    df = get_wnba_results(
        game_date=game_date,
        season=season,
    )

    if df.empty:
        print(f"No WNBA games found for {target_date}.")
        return

    df = add_model_columns(df)

    keep_columns = [
        "GAME_ID",
        "GAME_DATE",
        "PLAYER_ID",
        "PLAYER_NAME",
        "TEAM_ID",
        "TEAM_ABBREVIATION",
        "MATCHUP",
        "MIN",
        "PTS",
        "REB",
        "AST",
        "PRA",
        "PTS_REB",
        "PTS_AST",
        "REB_AST",
        "OREB",
        "DREB",
        "FGM",
        "FGA",
        "FG3M",
        "FG3A",
        "FTM",
        "FTA",
        "STL",
        "BLK",
        "STOCKS",
        "TOV",
        "FANTASY_SCORE_PP",
    ]

    keep_columns = [
        column
        for column in keep_columns
        if column in df.columns
    ]

    daily_results = df[keep_columns].copy()

    daily_file = DATA_DIR / f"WNBA_RESULTS_{target_date}.csv"
    daily_results.to_csv(daily_file, index=False)

    history_file = DATA_DIR / "WNBA_RESULTS_HISTORY.csv"

    if history_file.exists():
        history = pd.read_csv(history_file)
        combined = pd.concat(
            [history, daily_results],
            ignore_index=True,
        )
    else:
        combined = daily_results.copy()

    duplicate_columns = [
        column
        for column in [
            "GAME_ID",
            "PLAYER_ID",
            "PLAYER_NAME",
            "GAME_DATE",
        ]
        if column in combined.columns
    ]

    if duplicate_columns:
        combined = combined.drop_duplicates(
            subset=duplicate_columns,
            keep="last",
        )

    combined.to_csv(history_file, index=False)

    print("WNBA update complete.")
    print(f"Daily file: {daily_file}")
    print(f"History file: {history_file}")
    print(f"Players downloaded: {len(daily_results)}")


if __name__ == "__main__":
    results_update()
