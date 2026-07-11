from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "mlb"
DATA_DIR.mkdir(parents=True, exist_ok=True)


BATTING_FILE = DATA_DIR / "MLB_BATTING_RESULTS.csv"
PITCHING_FILE = DATA_DIR / "MLB_PITCHING_RESULTS.csv"
HISTORY_FILE = DATA_DIR / "MLB_RESULTS_HISTORY.csv"
MODEL_FILE = DATA_DIR / "MLB_MODEL_DATABASE.csv"


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(" ", "_")
        .str.replace("-", "_")
        .str.replace("+", "_PLUS_", regex=False)
    )

    return df.loc[:, ~df.columns.duplicated()].copy()


def find_column(
    df: pd.DataFrame,
    candidates: list[str],
) -> str | None:
    for column in candidates:
        if column in df.columns:
            return column

    return None


def standardize_player_name(
    df: pd.DataFrame,
    candidates: list[str],
) -> pd.DataFrame:
    df = df.copy()
    column = find_column(df, candidates)

    if column is None:
        raise ValueError(
            f"Could not find player name column. "
            f"Available columns: {list(df.columns)}"
        )

    if column != "PLAYER_NAME":
        if "PLAYER_NAME" in df.columns:
            df = df.drop(columns=[column])
        else:
            df = df.rename(columns={column: "PLAYER_NAME"})

    df["PLAYER_NAME"] = (
        df["PLAYER_NAME"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    return df


def numeric_series(
    df: pd.DataFrame,
    candidates: list[str],
) -> pd.Series:
    column = find_column(df, candidates)

    if column is None:
        return pd.Series(0.0, index=df.index)

    return pd.to_numeric(
        df[column],
        errors="coerce",
    ).fillna(0)


def ip_to_outs(value) -> int:
    """
    Convert baseball IP notation to outs.

    Examples:
    5.0 -> 15 outs
    5.1 -> 16 outs
    5.2 -> 17 outs
    """
    if pd.isna(value):
        return 0

    text = str(value).strip()

    try:
        if "." not in text:
            return int(float(text)) * 3

        whole_text, fraction_text = text.split(".", 1)

        whole = int(whole_text)
        fraction = int(fraction_text[:1] or 0)

        if fraction not in (0, 1, 2):
            # Handles true decimal innings if a source uses them.
            return round(float(text) * 3)

        return whole * 3 + fraction

    except (TypeError, ValueError):
        return 0


def get_result_date(df: pd.DataFrame) -> pd.Series:
    date_column = find_column(
        df,
        [
            "GAME_DATE",
            "DATE",
            "RESULT_DATE",
        ],
    )

    if date_column is not None:
        parsed = pd.to_datetime(
            df[date_column],
            errors="coerce",
        )

        fallback = pd.Timestamp(
            date.today() - timedelta(days=1)
        )

        return parsed.fillna(fallback).dt.strftime("%Y-%m-%d")

    yesterday = (
        date.today() - timedelta(days=1)
    ).isoformat()

    return pd.Series(
        yesterday,
        index=df.index,
    )


def build_hitter_history(
    raw: pd.DataFrame,
) -> pd.DataFrame:
    df = standardize_player_name(
        clean_columns(raw),
        [
            "PLAYER_NAME",
            "NAME",
            "PLAYER",
            "BATTER",
        ],
    )

    result = pd.DataFrame(index=df.index)

    result["RESULT_DATE"] = get_result_date(df)
    result["PLAYER_NAME"] = df["PLAYER_NAME"]
    result["PLAYER_TYPE"] = "HITTER"

    team_column = find_column(
        df,
        ["TEAM", "TEAM_NAME", "TEAM_ABBREVIATION"]
    )

    opponent_column = find_column(
        df,
        ["OPP", "OPPONENT", "MATCHUP"]
    )

    if team_column:
        result["TEAM"] = df[team_column]

    if opponent_column:
        result["OPPONENT"] = df[opponent_column]

    result["PA"] = numeric_series(df, ["PA"])
    result["AB"] = numeric_series(df, ["AB"])
    result["H"] = numeric_series(df, ["H", "HITS"])
    result["R"] = numeric_series(df, ["R", "RUNS"])
    result["RBI"] = numeric_series(df, ["RBI", "RBIS"])
    result["HR"] = numeric_series(df, ["HR", "HOME_RUNS"])
    result["BB"] = numeric_series(df, ["BB", "WALKS"])
    result["HBP"] = numeric_series(df, ["HBP"])
    result["SO"] = numeric_series(
        df,
        ["SO", "K", "STRIKEOUTS"]
    )
    result["SB"] = numeric_series(
        df,
        ["SB", "STOLEN_BASES"]
    )

    result["DOUBLES"] = numeric_series(
        df,
        ["2B", "DOUBLES"]
    )

    result["TRIPLES"] = numeric_series(
        df,
        ["3B", "TRIPLES"]
    )

    singles_column = find_column(
        df,
        ["1B", "SINGLES"]
    )

    if singles_column:
        result["SINGLES"] = numeric_series(
            df,
            ["1B", "SINGLES"]
        )
    else:
        result["SINGLES"] = (
            result["H"]
            - result["DOUBLES"]
            - result["TRIPLES"]
            - result["HR"]
        ).clip(lower=0)

    tb_column = find_column(
        df,
        ["TB", "TOTAL_BASES"]
    )

    if tb_column:
        result["TOTAL_BASES"] = numeric_series(
            df,
            ["TB", "TOTAL_BASES"]
        )
    else:
        result["TOTAL_BASES"] = (
            result["SINGLES"]
            + 2 * result["DOUBLES"]
            + 3 * result["TRIPLES"]
            + 4 * result["HR"]
        )

    result["H_PLUS_R_PLUS_RBI"] = (
        result["H"]
        + result["R"]
        + result["RBI"]
    )

    result["HITTER_FANTASY_PP"] = (
        3 * result["SINGLES"]
        + 5 * result["DOUBLES"]
        + 8 * result["TRIPLES"]
        + 10 * result["HR"]
        + 2 * result["R"]
        + 2 * result["RBI"]
        + 2 * result["BB"]
        + 2 * result["HBP"]
        + 5 * result["SB"]
    )

    result["SOURCE_FILE"] = BATTING_FILE.name

    return result


def build_pitcher_history(
    raw: pd.DataFrame,
) -> pd.DataFrame:
    df = standardize_player_name(
        clean_columns(raw),
        [
            "PLAYER_NAME",
            "NAME",
            "PLAYER",
            "PITCHER",
        ],
    )

    result = pd.DataFrame(index=df.index)

    result["RESULT_DATE"] = get_result_date(df)
    result["PLAYER_NAME"] = df["PLAYER_NAME"]
    result["PLAYER_TYPE"] = "PITCHER"

    team_column = find_column(
        df,
        ["TEAM", "TEAM_NAME", "TEAM_ABBREVIATION"]
    )

    opponent_column = find_column(
        df,
        ["OPP", "OPPONENT", "MATCHUP"]
    )

    if team_column:
        result["TEAM"] = df[team_column]

    if opponent_column:
        result["OPPONENT"] = df[opponent_column]

    ip_column = find_column(
        df,
        ["IP", "INNINGS_PITCHED"]
    )

    if ip_column:
        result["IP"] = df[ip_column]
        result["OUTS"] = df[ip_column].apply(ip_to_outs)
    else:
        result["IP"] = 0
        result["OUTS"] = 0

    result["K"] = numeric_series(
        df,
        ["SO", "K", "STRIKEOUTS"]
    )

    result["ER"] = numeric_series(
        df,
        ["ER", "EARNED_RUNS"]
    )

    result["BB"] = numeric_series(
        df,
        ["BB", "WALKS"]
    )

    result["HITS_ALLOWED"] = numeric_series(
        df,
        ["H", "HITS_ALLOWED"]
    )

    result["HR_ALLOWED"] = numeric_series(
        df,
        ["HR", "HOME_RUNS_ALLOWED"]
    )

    result["PITCHES"] = numeric_series(
        df,
        ["PITCHES", "PC", "PITCH_COUNT"]
    )

    result["WIN"] = numeric_series(
        df,
        ["W", "WIN", "WINS"]
    ).clip(upper=1)

    gs = numeric_series(
        df,
        ["GS", "GAMES_STARTED"]
    )

    result["QUALITY_START"] = (
        (result["OUTS"] >= 18)
        & (result["ER"] <= 3)
        & ((gs >= 1) | (gs.eq(0)))
    ).astype(int)

    result["PITCHER_FANTASY_PP"] = (
        6 * result["WIN"]
        + 4 * result["QUALITY_START"]
        - 3 * result["ER"]
        + 3 * result["K"]
        + result["OUTS"]
    )

    result["SOURCE_FILE"] = PITCHING_FILE.name

    return result


def append_history(
    new_rows: pd.DataFrame,
) -> pd.DataFrame:
    if HISTORY_FILE.exists():
        old = clean_columns(
            pd.read_csv(HISTORY_FILE)
        )

        combined = pd.concat(
            [old, new_rows],
            ignore_index=True,
            sort=False,
        )
    else:
        combined = new_rows.copy()

    combined = combined.drop_duplicates(
        subset=[
            "RESULT_DATE",
            "PLAYER_NAME",
            "PLAYER_TYPE",
        ],
        keep="last",
    )

    combined = combined.sort_values(
        [
            "RESULT_DATE",
            "PLAYER_TYPE",
            "PLAYER_NAME",
        ]
    )

    combined.to_csv(
        HISTORY_FILE,
        index=False,
    )

    return combined


def attach_latest_to_model(
    history: pd.DataFrame,
) -> None:
    if not MODEL_FILE.exists():
        print(
            "MLB_MODEL_DATABASE.csv was not found. "
            "Run merge_mlb_model.py first."
        )
        return

    model = standardize_player_name(
        clean_columns(
            pd.read_csv(MODEL_FILE)
        ),
        [
            "PLAYER_NAME",
            "NAME",
            "PLAYER",
        ],
    )

    history = history.copy()

    history["RESULT_DATE_SORT"] = pd.to_datetime(
        history["RESULT_DATE"],
        errors="coerce",
    )

    latest_hitters = (
        history[
            history["PLAYER_TYPE"] == "HITTER"
        ]
        .sort_values("RESULT_DATE_SORT")
        .drop_duplicates(
            subset=["PLAYER_NAME"],
            keep="last",
        )
        .drop(columns=["RESULT_DATE_SORT"])
    )

    latest_pitchers = (
        history[
            history["PLAYER_TYPE"] == "PITCHER"
        ]
        .sort_values("RESULT_DATE_SORT")
        .drop_duplicates(
            subset=["PLAYER_NAME"],
            keep="last",
        )
        .drop(columns=["RESULT_DATE_SORT"])
    )

    hitter_keep = [
        "PLAYER_NAME",
        "RESULT_DATE",
        "TEAM",
        "OPPONENT",
        "PA",
        "AB",
        "H",
        "R",
        "RBI",
        "HR",
        "BB",
        "HBP",
        "SO",
        "SB",
        "SINGLES",
        "DOUBLES",
        "TRIPLES",
        "TOTAL_BASES",
        "H_PLUS_R_PLUS_RBI",
        "HITTER_FANTASY_PP",
    ]

    pitcher_keep = [
        "PLAYER_NAME",
        "RESULT_DATE",
        "TEAM",
        "OPPONENT",
        "IP",
        "OUTS",
        "K",
        "ER",
        "BB",
        "HITS_ALLOWED",
        "HR_ALLOWED",
        "PITCHES",
        "WIN",
        "QUALITY_START",
        "PITCHER_FANTASY_PP",
    ]

    hitter_keep = [
        column
        for column in hitter_keep
        if column in latest_hitters.columns
    ]

    pitcher_keep = [
        column
        for column in pitcher_keep
        if column in latest_pitchers.columns
    ]

    latest_hitters = latest_hitters[hitter_keep].rename(
        columns={
            column: f"LAST_HIT_{column}"
            for column in hitter_keep
            if column != "PLAYER_NAME"
        }
    )

    latest_pitchers = latest_pitchers[pitcher_keep].rename(
        columns={
            column: f"LAST_PIT_{column}"
            for column in pitcher_keep
            if column != "PLAYER_NAME"
        }
    )

    # Remove old LAST columns before rebuilding.
    old_last_columns = [
        column
        for column in model.columns
        if column.startswith("LAST_HIT_")
        or column.startswith("LAST_PIT_")
    ]

    if old_last_columns:
        model = model.drop(
            columns=old_last_columns
        )

    model = model.merge(
        latest_hitters,
        on="PLAYER_NAME",
        how="outer",
    )

    model = model.merge(
        latest_pitchers,
        on="PLAYER_NAME",
        how="outer",
    )

    model.to_csv(
        MODEL_FILE,
        index=False,
    )

    print(
        f"Updated {MODEL_FILE.name} with latest box-score results."
    )


def history_update() -> None:
    if not BATTING_FILE.exists():
        raise FileNotFoundError(
            f"Missing {BATTING_FILE.name}"
        )

    if not PITCHING_FILE.exists():
        raise FileNotFoundError(
            f"Missing {PITCHING_FILE.name}"
        )

    batting_raw = pd.read_csv(
        BATTING_FILE
    )

    pitching_raw = pd.read_csv(
        PITCHING_FILE
    )

    hitters = build_hitter_history(
        batting_raw
    )

    pitchers = build_pitcher_history(
        pitching_raw
    )

    new_rows = pd.concat(
        [hitters, pitchers],
        ignore_index=True,
        sort=False,
    )

    history = append_history(
        new_rows
    )

    attach_latest_to_model(
        history
    )

    print("DONE")
    print(
        f"Created/updated: {HISTORY_FILE.name}"
    )
    print(
        f"History rows: {len(history)}"
    )


if __name__ == "__main__":
    history_update()