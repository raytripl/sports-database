from __future__ import annotations

from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "mlb"
DATA_DIR.mkdir(parents=True, exist_ok=True)


OUTPUT_FILE = DATA_DIR / "MLB_MODEL_DATABASE.csv"


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(" ", "_")
        .str.replace("-", "_")
    )

    df = df.loc[:, ~df.columns.duplicated()].copy()
    return df


def find_first_file(patterns: list[str]) -> Path | None:
    files: list[Path] = []

    for pattern in patterns:
        files.extend(DATA_DIR.glob(pattern))

    files = [
        file
        for file in files
        if file.name != OUTPUT_FILE.name
    ]

    if not files:
        return None

    return max(
        files,
        key=lambda file: file.stat().st_mtime,
    )


def find_name_column(
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

    name_column = find_name_column(df, candidates)

    if name_column is None:
        return df

    if name_column != "PLAYER_NAME":
        if "PLAYER_NAME" not in df.columns:
            df = df.rename(
                columns={name_column: "PLAYER_NAME"}
            )

    df["PLAYER_NAME"] = (
        df["PLAYER_NAME"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    return df


def convert_numeric(
    df: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    df = df.copy()

    for column in columns:
        if column in df.columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

    return df


def prefix_columns(
    df: pd.DataFrame,
    prefix: str,
    key: str = "PLAYER_NAME",
) -> pd.DataFrame:
    return df.rename(
        columns={
            column: f"{prefix}_{column}"
            for column in df.columns
            if column != key
        }
    )


def load_csv(path: Path | None, label: str) -> pd.DataFrame:
    if path is None:
        print(f"Warning: no {label} file found.")
        return pd.DataFrame()

    print(f"Using {label}: {path.name}")
    return clean_columns(pd.read_csv(path))


def build_batting_results(
    df: pd.DataFrame,
) -> pd.DataFrame:
    if df.empty:
        return df

    df = standardize_player_name(
        df,
        [
            "PLAYER_NAME",
            "NAME",
            "PLAYER",
            "BATTER",
        ],
    )

    if "PLAYER_NAME" not in df.columns:
        print("Warning: no hitter player-name column found.")
        return pd.DataFrame()

    numeric = [
        "PA",
        "AB",
        "H",
        "R",
        "RBI",
        "HR",
        "BB",
        "SO",
        "K",
        "1B",
        "2B",
        "3B",
        "TB",
        "AVG",
        "OBP",
        "SLG",
        "OPS",
    ]

    df = convert_numeric(df, numeric)

    if "TB" not in df.columns:
        singles = df["1B"] if "1B" in df.columns else 0
        doubles = df["2B"] if "2B" in df.columns else 0
        triples = df["3B"] if "3B" in df.columns else 0
        homers = df["HR"] if "HR" in df.columns else 0

        df["TB"] = (
            singles
            + 2 * doubles
            + 3 * triples
            + 4 * homers
        )

    if all(column in df.columns for column in ["H", "R", "RBI"]):
        df["H_R_RBI"] = (
            df["H"]
            + df["R"]
            + df["RBI"]
        )

    if all(column in df.columns for column in ["H", "BB", "R", "RBI", "HR"]):
        df["HITTER_FANTASY_EST"] = (
            df["H"] * 3
            + df["BB"] * 2
            + df["R"] * 2
            + df["RBI"] * 2
            + df["HR"] * 4
        )

    df = (
        df
        .drop_duplicates(
            subset=["PLAYER_NAME"],
            keep="last",
        )
        .copy()
    )

    return prefix_columns(df, "BAT")


def build_pitching_results(
    df: pd.DataFrame,
) -> pd.DataFrame:
    if df.empty:
        return df

    df = standardize_player_name(
        df,
        [
            "PLAYER_NAME",
            "NAME",
            "PLAYER",
            "PITCHER",
        ],
    )

    if "PLAYER_NAME" not in df.columns:
        print("Warning: no pitcher player-name column found.")
        return pd.DataFrame()

    numeric = [
        "IP",
        "SO",
        "K",
        "BB",
        "ER",
        "H",
        "HR",
        "PITCHES",
        "PC",
        "ERA",
        "WHIP",
    ]

    df = convert_numeric(df, numeric)

    strikeout_column = None

    if "SO" in df.columns:
        strikeout_column = "SO"
    elif "K" in df.columns:
        strikeout_column = "K"

    pitch_column = None

    if "PITCHES" in df.columns:
        pitch_column = "PITCHES"
    elif "PC" in df.columns:
        pitch_column = "PC"

    if strikeout_column and "IP" in df.columns:
        df["K_PER_IP"] = (
            df[strikeout_column]
            / df["IP"].replace(0, pd.NA)
        )

    if strikeout_column and pitch_column:
        df["K_PER_100_PITCHES"] = (
            df[strikeout_column]
            / df[pitch_column].replace(0, pd.NA)
            * 100
        )

    df = (
        df
        .drop_duplicates(
            subset=["PLAYER_NAME"],
            keep="last",
        )
        .copy()
    )

    return prefix_columns(df, "PIT")

def build_statcast_batters(
    df: pd.DataFrame,
    batting_results: pd.DataFrame,
) -> pd.DataFrame:
    if df.empty:
        return df

    df = clean_columns(df)

    # Raw Statcast PLAYER_NAME is usually the pitcher.
    # BATTER is the hitter's MLB ID.
    if "BATTER" not in df.columns:
        print("Warning: Statcast file has no BATTER ID column.")
        return pd.DataFrame()

    df["BATTER"] = pd.to_numeric(
        df["BATTER"],
        errors="coerce",
    )
     # Remove Statcast's PLAYER_NAME column because it is usually the pitcher.
    # The hitter name will be added from the BATTER ID lookup.
    if "PLAYER_NAME" in df.columns:
        df = df.drop(columns=["PLAYER_NAME"])
        
    batting_results = standardize_player_name(
        batting_results,
        [
            "PLAYER_NAME",
            "NAME",
            "PLAYER",
            "BATTER",
        ],
    )

    if (
        batting_results.empty
        or "PLAYER_NAME" not in batting_results.columns
        or "MLBID" not in batting_results.columns
    ):
        print("Warning: could not build batter ID/name lookup.")
        return pd.DataFrame()

    player_lookup = batting_results[
        ["MLBID", "PLAYER_NAME"]
    ].copy()

    player_lookup["MLBID"] = pd.to_numeric(
        player_lookup["MLBID"],
        errors="coerce",
    )

    player_lookup = (
        player_lookup
        .dropna(
            subset=["MLBID", "PLAYER_NAME"]
        )
        .drop_duplicates(
            subset=["MLBID"],
            keep="last",
        )
    )

    df = df.merge(
        player_lookup,
        left_on="BATTER",
        right_on="MLBID",
        how="left",
    )

    df = df.dropna(
        subset=["PLAYER_NAME"]
    ).copy()

    numeric = [
        "LAUNCH_SPEED",
        "LAUNCH_ANGLE",
        "ESTIMATED_BA_USING_SPEEDANGLE",
        "ESTIMATED_SLG_USING_SPEEDANGLE",
    ]

    df = convert_numeric(
        df,
        numeric,
    )

    if "LAUNCH_SPEED" in df.columns:
        df["HARD_HIT"] = (
            df["LAUNCH_SPEED"] >= 95
        ).astype(int)

    if (
        "LAUNCH_SPEED" in df.columns
        and "LAUNCH_ANGLE" in df.columns
    ):
        df["BARREL_EST"] = (
            (df["LAUNCH_SPEED"] >= 98)
            & df["LAUNCH_ANGLE"].between(26, 30)
        ).astype(int)

    agg_map: dict[str, str] = {}

    for column in [
        "LAUNCH_SPEED",
        "LAUNCH_ANGLE",
        "ESTIMATED_BA_USING_SPEEDANGLE",
        "ESTIMATED_SLG_USING_SPEEDANGLE",
        "HARD_HIT",
        "BARREL_EST",
    ]:
        if column in df.columns:
            agg_map[column] = "mean"

    if not agg_map:
        return (
            df[["PLAYER_NAME"]]
            .drop_duplicates()
            .copy()
        )

    statcast = (
        df
        .groupby(
            "PLAYER_NAME",
            as_index=False,
        )
        .agg(agg_map)
    )

    statcast = statcast.rename(
        columns={
            "LAUNCH_SPEED": "AVG_EXIT_VELO",
            "LAUNCH_ANGLE": "AVG_LAUNCH_ANGLE",
            "ESTIMATED_BA_USING_SPEEDANGLE": "XBA",
            "ESTIMATED_SLG_USING_SPEEDANGLE": "XSLG",
            "HARD_HIT": "HARD_HIT_RATE",
            "BARREL_EST": "BARREL_RATE_EST",
        }
    )

    return prefix_columns(
        statcast,
        "SC",
    )

def merge_model_update() -> None:
    batting_file = find_first_file(
        [
            "MLB_BATTING_RESULTS*.csv",
        ]
    )

    pitching_file = find_first_file(
        [
            "MLB_PITCHING_RESULTS*.csv",
        ]
    )

    statcast_file = find_first_file(
        [
            "MLB_RECENT_UPDATE*.csv",
            "MLB_2026_ALL_STATCAST_v2*.csv",
            "MLB_2026_ALL_STATCAST*.csv",
        ]
    )

    batter_summary_file = find_first_file(
        [
            "MLB_2026_BATTERS_FROM_STATCAST*.csv",
        ]
    )

    batting_raw = load_csv(
        batting_file,
        "batting results",
    )

    pitching_raw = load_csv(
        pitching_file,
        "pitching results",
    )

    statcast_raw = load_csv(
        statcast_file,
        "recent Statcast",
    )

    batter_summary_raw = load_csv(
        batter_summary_file,
        "Statcast batter summary",
    )

    batting = build_batting_results(
        batting_raw
    )

    pitching = build_pitching_results(
        pitching_raw
    )

    statcast = build_statcast_batters(
    statcast_raw,
    batting_raw,
    )

    batter_summary = pd.DataFrame()

    if not batter_summary_raw.empty:
        batter_summary_raw = standardize_player_name(
            batter_summary_raw,
            [
                "PLAYER_NAME",
                "PLAYER",
                "NAME",
                "BATTER_NAME",
            ],
        )

        if "PLAYER_NAME" in batter_summary_raw.columns:
            batter_summary_raw = (
                batter_summary_raw
                .drop_duplicates(
                    subset=["PLAYER_NAME"],
                    keep="last",
                )
                .copy()
            )

            batter_summary = prefix_columns(
                batter_summary_raw,
                "SEASON_SC",
            )

    frames = [
        frame
        for frame in [
            batting,
            pitching,
            statcast,
            batter_summary,
        ]
        if not frame.empty
    ]

    if not frames:
        raise RuntimeError(
            "No usable MLB files were found."
        )

    model = frames[0]

    for frame in frames[1:]:
        model = model.merge(
            frame,
            on="PLAYER_NAME",
            how="outer",
        )

    model = model.sort_values(
        "PLAYER_NAME",
        na_position="last",
    )

    model.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print("DONE")
    print(f"Created: {OUTPUT_FILE}")
    print(f"Players: {len(model)}")
    print(f"Columns: {len(model.columns)}")


if __name__ == "__main__":
    merge_model_update()
