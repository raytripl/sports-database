from __future__ import annotations

import argparse
import math
import re
import unicodedata
from pathlib import Path

import pandas as pd


PLAYER_COLUMNS = (
    "player",
    "player_name",
    "name",
    "athlete",
)

STAT_ALIASES = {
    "points": (
        "points",
        "pts",
        "point",
    ),
    "rebounds": (
        "rebounds",
        "rebs",
        "reb",
        "total_rebounds",
        "trb",
    ),
    "assists": (
        "assists",
        "asts",
        "ast",
    ),
    "steals": (
        "steals",
        "stl",
    ),
    "blocks": (
        "blocks",
        "blk",
    ),
    "turnovers": (
        "turnovers",
        "tov",
        "to",
    ),
    "three_pointers_made": (
        "three_pointers_made",
        "three_point_made",
        "three_pt_made",
        "3pt_made",
        "3pm",
        "fg3m",
        "threes_made",
    ),
    "field_goals_made": (
        "field_goals_made",
        "fgm",
    ),
    "field_goals_attempted": (
        "field_goals_attempted",
        "field_goal_attempts",
        "fga",
    ),
    "free_throws_made": (
        "free_throws_made",
        "ftm",
    ),
    "free_throws_attempted": (
        "free_throws_attempted",
        "free_throw_attempts",
        "fta",
    ),
    "offensive_rebounds": (
        "offensive_rebounds",
        "oreb",
        "orb",
    ),
    "defensive_rebounds": (
        "defensive_rebounds",
        "dreb",
        "drb",
    ),
    "minutes": (
        "minutes",
        "mins",
        "min",
    ),
    "fantasy_score": (
        "fantasy_score",
        "fantasy_points",
        "prizepicks_fantasy_score",
    ),
}


def normalize_column(value: object) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def normalize_name(value: object) -> str:
    if pd.isna(value):
        return ""

    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text)

    suffixes = {
        "jr",
        "sr",
        "ii",
        "iii",
        "iv",
    }

    parts = [
        part
        for part in text.split()
        if part not in suffixes
    ]

    return " ".join(parts)


def normalize_prop(value: object) -> str:
    text = str(value).lower().strip()

    replacements = {
        "&": "+",
        "three pointers": "3pt",
        "three pointer": "3pt",
        "three-point": "3pt",
        "3-point": "3pt",
        "3-pt": "3pt",
        "3 pt": "3pt",
        "fantasy points": "fantasy score",
        "fantasy pts": "fantasy score",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"\s+", " ", text)

    return text


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series,
        errors="coerce",
    )


def find_player_column(frame: pd.DataFrame) -> str:
    for column in PLAYER_COLUMNS:
        if column in frame.columns:
            return column

    raise ValueError(
        "Could not identify the player-name column. "
        f"Available columns: {list(frame.columns)}"
    )


def find_stat_column(
    frame: pd.DataFrame,
    stat: str,
) -> str | None:
    aliases = STAT_ALIASES[stat]

    for alias in aliases:
        if alias in frame.columns:
            return alias

    return None


def get_stat(
    row: pd.Series,
    stat_columns: dict[str, str | None],
    stat: str,
) -> float | None:
    column = stat_columns.get(stat)

    if not column:
        return None

    value = pd.to_numeric(
        pd.Series([row.get(column)]),
        errors="coerce",
    ).iloc[0]

    if pd.isna(value):
        return None

    return float(value)


def calculate_fantasy_score(
    row: pd.Series,
    stat_columns: dict[str, str | None],
) -> float | None:
    direct = get_stat(
        row,
        stat_columns,
        "fantasy_score",
    )

    if direct is not None:
        return direct

    points = get_stat(row, stat_columns, "points")
    rebounds = get_stat(row, stat_columns, "rebounds")
    assists = get_stat(row, stat_columns, "assists")
    steals = get_stat(row, stat_columns, "steals")
    blocks = get_stat(row, stat_columns, "blocks")
    turnovers = get_stat(row, stat_columns, "turnovers")

    required = (
        points,
        rebounds,
        assists,
        steals,
        blocks,
        turnovers,
    )

    if any(value is None for value in required):
        return None

    # Standard PrizePicks basketball fantasy scoring.
    return (
        points
        + 1.2 * rebounds
        + 1.5 * assists
        + 3.0 * blocks
        + 3.0 * steals
        - turnovers
    )


def calculate_actual(
    row: pd.Series,
    prop_type: object,
    stat_columns: dict[str, str | None],
) -> tuple[float | None, str]:
    prop = normalize_prop(prop_type)

    points = get_stat(row, stat_columns, "points")
    rebounds = get_stat(row, stat_columns, "rebounds")
    assists = get_stat(row, stat_columns, "assists")
    steals = get_stat(row, stat_columns, "steals")
    blocks = get_stat(row, stat_columns, "blocks")
    turnovers = get_stat(row, stat_columns, "turnovers")
    threes = get_stat(
        row,
        stat_columns,
        "three_pointers_made",
    )
    fgm = get_stat(
        row,
        stat_columns,
        "field_goals_made",
    )
    fga = get_stat(
        row,
        stat_columns,
        "field_goals_attempted",
    )
    ftm = get_stat(
        row,
        stat_columns,
        "free_throws_made",
    )
    fta = get_stat(
        row,
        stat_columns,
        "free_throws_attempted",
    )
    oreb = get_stat(
        row,
        stat_columns,
        "offensive_rebounds",
    )
    dreb = get_stat(
        row,
        stat_columns,
        "defensive_rebounds",
    )
    minutes = get_stat(row, stat_columns, "minutes")

    if prop in {"points", "pts"}:
        return points, "points"

    if prop in {"rebounds", "rebs"}:
        return rebounds, "rebounds"

    if prop in {"assists", "asts"}:
        return assists, "assists"

    if prop in {"steals", "stls"}:
        return steals, "steals"

    if prop in {"blocks", "blks"}:
        return blocks, "blocks"

    if prop in {"turnovers", "tos"}:
        return turnovers, "turnovers"

    if prop in {
        "3pt made",
        "3pt made shots",
        "3pt made",
        "3-pointers made",
        "3 pointers made",
    }:
        return threes, "three_pointers_made"

    if prop in {
        "field goals made",
        "fg made",
        "fgm",
    }:
        return fgm, "field_goals_made"

    if prop in {
        "field goals attempted",
        "field goal attempts",
        "fg attempts",
        "fga",
    }:
        return fga, "field_goals_attempted"

    if prop in {
        "free throws made",
        "ft made",
        "ftm",
    }:
        return ftm, "free_throws_made"

    if prop in {
        "free throws attempted",
        "free throw attempts",
        "ft attempts",
        "fta",
    }:
        return fta, "free_throws_attempted"

    if prop in {
        "offensive rebounds",
        "off rebounds",
        "oreb",
    }:
        return oreb, "offensive_rebounds"

    if prop in {
        "defensive rebounds",
        "def rebounds",
        "dreb",
    }:
        return dreb, "defensive_rebounds"

    if prop in {
        "minutes",
        "mins",
    }:
        return minutes, "minutes"

    if prop in {
        "pts+rebs",
        "points+rebounds",
        "points + rebounds",
    }:
        if points is None or rebounds is None:
            return None, "points_plus_rebounds"

        return points + rebounds, "points_plus_rebounds"

    if prop in {
        "pts+asts",
        "points+assists",
        "points + assists",
    }:
        if points is None or assists is None:
            return None, "points_plus_assists"

        return points + assists, "points_plus_assists"

    if prop in {
        "rebs+asts",
        "rebounds+assists",
        "rebounds + assists",
    }:
        if rebounds is None or assists is None:
            return None, "rebounds_plus_assists"

        return rebounds + assists, "rebounds_plus_assists"

    if prop in {
        "pts+rebs+asts",
        "pra",
        "points+rebounds+assists",
        "points + rebounds + assists",
    }:
        if (
            points is None
            or rebounds is None
            or assists is None
        ):
            return None, "pra"

        return points + rebounds + assists, "pra"

    if prop in {
        "blks+stls",
        "blocks+steals",
        "stocks",
    }:
        if blocks is None or steals is None:
            return None, "blocks_plus_steals"

        return blocks + steals, "blocks_plus_steals"

    if prop in {
        "fantasy score",
        "fantasy",
    }:
        return (
            calculate_fantasy_score(
                row,
                stat_columns,
            ),
            "fantasy_score",
        )

    return None, "unsupported_prop"


def grade_prediction(
    actual: float | None,
    line: float | None,
    direction: object,
) -> tuple[str, float | None]:
    if actual is None or line is None:
        return "UNRESOLVED", None

    normalized_direction = str(direction).strip().upper()

    raw_margin = actual - line

    if math.isclose(
        actual,
        line,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        return "PUSH", 0.0

    if normalized_direction == "OVER":
        result = "WIN" if actual > line else "LOSS"
        directional_margin = raw_margin
    elif normalized_direction == "UNDER":
        result = "WIN" if actual < line else "LOSS"
        directional_margin = -raw_margin
    else:
        return "UNRESOLVED", None

    return result, directional_margin


def wilson_lower_bound(
    wins: int,
    decisions: int,
    z: float = 1.96,
) -> float:
    if decisions <= 0:
        return 0.0

    proportion = wins / decisions

    numerator = (
        proportion
        + z * z / (2 * decisions)
        - z
        * math.sqrt(
            (
                proportion * (1 - proportion)
                + z * z / (4 * decisions)
            )
            / decisions
        )
    )

    denominator = 1 + z * z / decisions

    return numerator / denominator


def summarize_group(
    frame: pd.DataFrame,
    group_columns: list[str],
) -> pd.DataFrame:
    usable = frame[
        frame["grade_result"].isin(
            ["WIN", "LOSS", "PUSH"]
        )
    ].copy()

    if usable.empty:
        return pd.DataFrame()

    usable["win"] = (
        usable["grade_result"] == "WIN"
    ).astype(int)
    usable["loss"] = (
        usable["grade_result"] == "LOSS"
    ).astype(int)
    usable["push"] = (
        usable["grade_result"] == "PUSH"
    ).astype(int)

    grouped = (
        usable.groupby(
            group_columns,
            dropna=False,
        )
        .agg(
            graded_props=("grade_result", "size"),
            wins=("win", "sum"),
            losses=("loss", "sum"),
            pushes=("push", "sum"),
            average_directional_margin=(
                "directional_margin",
                "mean",
            ),
            average_projection_error=(
                "projection_absolute_error",
                "mean",
            ),
            average_research_score=(
                "research_score",
                "mean",
            ),
            average_direction_gap=(
                "research_direction_gap",
                "mean",
            ),
        )
        .reset_index()
    )

    grouped["decisions"] = (
        grouped["wins"] + grouped["losses"]
    )

    grouped["hit_rate"] = (
        grouped["wins"]
        / grouped["decisions"].replace(0, pd.NA)
    )

    grouped["wilson_lower"] = grouped.apply(
        lambda row: wilson_lower_bound(
            int(row["wins"]),
            int(row["decisions"]),
        ),
        axis=1,
    )

    return grouped.sort_values(
        [
            "wilson_lower",
            "hit_rate",
            "decisions",
        ],
        ascending=[
            False,
            False,
            False,
        ],
    )


def build_threshold_analysis(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    score_thresholds = [
        60,
        65,
        67.5,
        70,
        72.5,
        75,
        77.5,
        80,
    ]

    direction_thresholds = [
        0,
        5,
        7.5,
        10,
        12.5,
        15,
    ]

    opportunity_thresholds = [
        0,
        50,
        60,
        70,
        75,
        80,
    ]

    for score_min in score_thresholds:
        for direction_min in direction_thresholds:
            for opportunity_min in opportunity_thresholds:
                selected = frame[
                    numeric(frame["research_score"]).ge(
                        score_min
                    )
                    & numeric(
                        frame["research_direction_gap"]
                    ).ge(direction_min)
                    & numeric(
                        frame[
                            "research_opportunity_score_used"
                        ]
                    ).ge(opportunity_min)
                    & frame["grade_result"].isin(
                        ["WIN", "LOSS", "PUSH"]
                    )
                ]

                wins = int(
                    (
                        selected["grade_result"] == "WIN"
                    ).sum()
                )
                losses = int(
                    (
                        selected["grade_result"] == "LOSS"
                    ).sum()
                )
                pushes = int(
                    (
                        selected["grade_result"] == "PUSH"
                    ).sum()
                )
                decisions = wins + losses

                rows.append(
                    {
                        "research_score_min": score_min,
                        "direction_gap_min": direction_min,
                        "opportunity_score_min": (
                            opportunity_min
                        ),
                        "graded_props": len(selected),
                        "wins": wins,
                        "losses": losses,
                        "pushes": pushes,
                        "decisions": decisions,
                        "hit_rate": (
                            wins / decisions
                            if decisions
                            else pd.NA
                        ),
                        "wilson_lower": (
                            wilson_lower_bound(
                                wins,
                                decisions,
                            )
                            if decisions
                            else pd.NA
                        ),
                        "average_directional_margin": (
                            numeric(
                                selected[
                                    "directional_margin"
                                ]
                            ).mean()
                            if len(selected)
                            else pd.NA
                        ),
                    }
                )

    result = pd.DataFrame(rows)

    return result.sort_values(
        [
            "wilson_lower",
            "hit_rate",
            "decisions",
        ],
        ascending=[
            False,
            False,
            False,
        ],
        na_position="last",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Grade historical WNBA research-board "
            "predictions against completed results."
        )
    )

    parser.add_argument(
        "--date",
        required=True,
        help="Slate date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--board",
        default=None,
        help="Optional research-board CSV path.",
    )
    parser.add_argument(
        "--results",
        default=None,
        help="Optional completed-results CSV path.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional audit output directory.",
    )

    args = parser.parse_args()

    slate_date = args.date

    board_path = Path(
        args.board
        or (
            "data/backtests/historical_replay/"
            f"{slate_date}/wnba_research_board.csv"
        )
    )

    results_path = Path(
        args.results
        or f"data/wnba/WNBA_RESULTS_{slate_date}.csv"
    )

    output_dir = Path(
        args.output_dir
        or (
            "data/backtests/historical_replay/"
            f"{slate_date}/audit"
        )
    )

    if not board_path.exists():
        raise FileNotFoundError(
            f"Research board not found: {board_path}"
        )

    if not results_path.exists():
        raise FileNotFoundError(
            f"Results file not found: {results_path}"
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    board = pd.read_csv(
        board_path,
        low_memory=False,
    )
    results = pd.read_csv(
        results_path,
        low_memory=False,
    )

    board.columns = [
        normalize_column(column)
        for column in board.columns
    ]
    results.columns = [
        normalize_column(column)
        for column in results.columns
    ]

    board_player_column = find_player_column(board)
    results_player_column = find_player_column(results)

    board["player_key"] = board[
        board_player_column
    ].map(normalize_name)

    results["player_key"] = results[
        results_player_column
    ].map(normalize_name)

    duplicate_results = results[
        results["player_key"].duplicated(
            keep=False
        )
    ]

    if not duplicate_results.empty:
        print(
            "WARNING: Duplicate player rows found "
            "in completed results:"
        )
        print(
            duplicate_results[
                [
                    results_player_column,
                    "player_key",
                ]
            ].to_string(index=False)
        )

    result_lookup = (
        results.drop_duplicates(
            subset=["player_key"],
            keep="last",
        )
        .set_index("player_key")
    )

    stat_columns = {
        stat: find_stat_column(
            results,
            stat,
        )
        for stat in STAT_ALIASES
    }

    graded_rows: list[dict[str, object]] = []

    for _, board_row in board.iterrows():
        output = board_row.to_dict()
        player_key = output["player_key"]

        if player_key not in result_lookup.index:
            output.update(
                {
                    "result_player_matched": 0,
                    "actual_result": pd.NA,
                    "actual_stat_source": (
                        "PLAYER_NOT_MATCHED"
                    ),
                    "grade_result": "UNRESOLVED",
                    "raw_margin": pd.NA,
                    "directional_margin": pd.NA,
                    "projection_error": pd.NA,
                    "projection_absolute_error": pd.NA,
                }
            )
            graded_rows.append(output)
            continue

        result_row = result_lookup.loc[player_key]

        actual, source = calculate_actual(
            result_row,
            board_row.get("prop_type"),
            stat_columns,
        )

        line_value = pd.to_numeric(
            pd.Series(
                [board_row.get("line")]
            ),
            errors="coerce",
        ).iloc[0]

        line = (
            None
            if pd.isna(line_value)
            else float(line_value)
        )

        grade_result, directional_margin = (
            grade_prediction(
                actual,
                line,
                board_row.get(
                    "research_direction"
                ),
            )
        )

        raw_margin = (
            actual - line
            if actual is not None
            and line is not None
            else None
        )

        projection_value = pd.to_numeric(
            pd.Series(
                [
                    board_row.get(
                        "projected_prop_result"
                    )
                ]
            ),
            errors="coerce",
        ).iloc[0]

        projection = (
            None
            if pd.isna(projection_value)
            else float(projection_value)
        )

        projection_error = (
            actual - projection
            if actual is not None
            and projection is not None
            else None
        )

        output.update(
            {
                "result_player_matched": 1,
                "actual_result": actual,
                "actual_stat_source": source,
                "grade_result": grade_result,
                "raw_margin": raw_margin,
                "directional_margin": (
                    directional_margin
                ),
                "projection_error": (
                    projection_error
                ),
                "projection_absolute_error": (
                    abs(projection_error)
                    if projection_error is not None
                    else None
                ),
            }
        )

        graded_rows.append(output)

    graded = pd.DataFrame(graded_rows)

    graded_path = (
        output_dir / "graded_predictions.csv"
    )
    graded.to_csv(
        graded_path,
        index=False,
    )

    overall = summarize_group(
        graded.assign(
            scorecard_scope="ALL_PROPS"
        ),
        ["scorecard_scope"],
    )
    overall.to_csv(
        output_dir / "model_scorecard.csv",
        index=False,
    )

    if "prop_family" in graded.columns:
        family = summarize_group(
            graded,
            ["prop_family"],
        )
    else:
        family = summarize_group(
            graded,
            ["prop_type"],
        )

    family.to_csv(
        output_dir / "prop_family_scorecard.csv",
        index=False,
    )

    player = summarize_group(
        graded,
        [board_player_column],
    )
    player.to_csv(
        output_dir / "player_scorecard.csv",
        index=False,
    )

    direction = summarize_group(
        graded,
        ["research_direction"],
    )
    direction.to_csv(
        output_dir / "direction_scorecard.csv",
        index=False,
    )

    threshold = build_threshold_analysis(
        graded
    )
    threshold.to_csv(
        output_dir / "threshold_analysis.csv",
        index=False,
    )

    unsupported = (
        graded[
            graded["actual_stat_source"].eq(
                "unsupported_prop"
            )
        ][
            [
                board_player_column,
                "prop_type",
                "line",
                "research_direction",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            [
                "prop_type",
                board_player_column,
            ]
        )
    )

    unsupported.to_csv(
        output_dir / "unsupported_props.csv",
        index=False,
    )

    unmatched = (
        graded[
            graded["result_player_matched"].eq(0)
        ][
            [
                board_player_column,
                "team",
                "opponent",
            ]
        ]
        .drop_duplicates()
        .sort_values(board_player_column)
    )

    unmatched.to_csv(
        output_dir / "unmatched_players.csv",
        index=False,
    )

    print("=" * 80)
    print("WNBA RESEARCH GRADER")
    print("=" * 80)
    print("Date:", slate_date)
    print("Board rows:", len(board))
    print("Results rows:", len(results))
    print(
        "Matched board rows:",
        int(
            graded[
                "result_player_matched"
            ].sum()
        ),
    )
    print()
    print("Grade results:")
    print(
        graded["grade_result"]
        .value_counts(dropna=False)
        .to_string()
    )

    print()
    print("Detected result columns:")
    for stat, column in stat_columns.items():
        print(f"  {stat}: {column}")

    print()
    print("Overall scorecard:")
    if overall.empty:
        print("No gradeable props.")
    else:
        print(
            overall.to_string(
                index=False
            )
        )

    print()
    print("Unsupported prop types:")
    if unsupported.empty:
        print("None")
    else:
        print(
            unsupported["prop_type"]
            .value_counts()
            .to_string()
        )

    print()
    print("Outputs:")
    for path in sorted(
        output_dir.glob("*.csv")
    ):
        print(" ", path)


if __name__ == "__main__":
    main()
