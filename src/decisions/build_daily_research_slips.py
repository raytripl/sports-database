"""Build research-only daily MLB/WNBA Power and Flex slips."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]


def numeric(
    frame: pd.DataFrame,
    column: str,
    default: float = 0.0,
) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)

    return pd.to_numeric(
        frame[column],
        errors="coerce",
    ).fillna(default)


def text(
    frame: pd.DataFrame,
    column: str,
    default: str = "",
) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=str)

    return (
        frame[column]
        .fillna(default)
        .astype(str)
        .str.strip()
    )


def first_available(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    default: float = 0.0,
) -> pd.Series:
    for column in columns:
        if column in frame.columns:
            return numeric(frame, column, default)

    return pd.Series(default, index=frame.index, dtype=float)


def normalize_board(
    path: Path,
    sport: str,
) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    frame = pd.read_csv(path, low_memory=False)

    if frame.empty:
        return frame

    output = frame.copy()
    output["sport"] = sport

    output["player"] = text(
        output,
        "player",
        "",
    )

    output["prop_type"] = text(
        output,
        "prop_type",
        "",
    )

    output["team"] = text(
        output,
        "team",
        "",
    )

    output["opponent"] = text(
        output,
        "opponent",
        "",
    )

    output["line"] = first_available(
        output,
        (
            "line",
            "line_score",
            "projection",
        ),
    )

    direction = text(
        output,
        "model_direction",
        "",
    ).str.upper()

    fallback_direction = text(
        output,
        "direction",
        "",
    ).str.upper()

    research_direction = text(
        output,
        "research_direction",
        "",
    ).str.upper()

    direction = direction.where(
        direction.isin(["OVER", "UNDER"]),
        fallback_direction,
    )

    direction = direction.where(
        direction.isin(["OVER", "UNDER"]),
        research_direction,
    )

    over_score = numeric(output, "over_score", 0.0)
    under_score = numeric(output, "under_score", 0.0)

    inferred = pd.Series(
        "OVER",
        index=output.index,
        dtype=str,
    )

    inferred.loc[under_score.gt(over_score)] = "UNDER"

    direction = direction.where(
        direction.isin(["OVER", "UNDER"]),
        inferred,
    )

    output["research_direction"] = direction

    output["research_score"] = first_available(
        output,
        (
            "research_score",
            "player_comparison_score",
            "model_score",
            "statistical_score",
        ),
    )

    output["direction_gap"] = first_available(
        output,
        (
            "direction_gap",
            "research_direction_gap",
        ),
    )

    missing_gap = output["direction_gap"].eq(0)

    output.loc[
        missing_gap,
        "direction_gap",
    ] = (
        over_score - under_score
    ).abs()[missing_gap]

    output["decision_strength"] = first_available(
        output,
        (
            "decision_strength",
            "model_score",
            "research_score",
        ),
    )

    output["opportunity_score"] = first_available(
        output,
        (
            "opportunity_score",
            "opportunity_component",
        ),
        50.0,
    )

    output["matchup_score"] = first_available(
        output,
        (
            "matchup_score",
            "directional_matchup_component",
        ),
        50.0,
    )

    output["data_quality"] = first_available(
        output,
        (
            "data_quality",
            "data_quality_component",
        ),
        50.0,
    )

    output["line_value_score"] = first_available(
        output,
        (
            "line_value_score",
            "line_value_component",
        ),
        50.0,
    )

    output["probability"] = first_available(
        output,
        (
            "selected_probability",
            "calibrated_probability",
            "raw_probability",
        ),
        0.50,
    )

    output["selection_path"] = text(
        output,
        "selection_path",
        "RESEARCH_CANDIDATE",
    ).str.upper()

    output["research_degrader_status"] = text(
        output,
        "research_degrader_status",
        "NONE",
    ).str.upper()

    output["injury_status"] = text(
        output,
        "injury_status",
        "",
    ).str.upper()

    output["lineup_confirmed"] = numeric(
        output,
        "lineup_confirmed",
        0,
    )

    output["starter_confirmed"] = numeric(
        output,
        "starter_confirmed",
        0,
    )

    output["research_only"] = 1
    output["production_approved"] = 0
    output["slip_builder_version"] = (
        "SPORTS_HUB_RESEARCH_SLIP_V1"
    )

    output["composite_score"] = (
        output["research_score"] * 0.30
        + output["decision_strength"] * 0.20
        + output["direction_gap"].clip(upper=40) * 0.35
        + output["opportunity_score"] * 0.08
        + output["matchup_score"] * 0.04
        + output["data_quality"] * 0.03
    ).round(3)

    return output


def remove_duplicate_players(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    if frame.empty:
        return frame

    ordered = frame.sort_values(
        [
            "composite_score",
            "probability",
            "research_score",
        ],
        ascending=False,
    )

    return ordered.drop_duplicates(
        ["sport", "player"],
        keep="first",
    )


def select_diversified(
    candidates: pd.DataFrame,
    size: int,
) -> pd.DataFrame:
    if candidates.empty:
        return candidates

    selected_rows: list[pd.Series] = []
    used_players: set[tuple[str, str]] = set()
    used_games: dict[str, int] = {}

    for _, row in candidates.iterrows():
        player_key = (
            str(row.get("sport", "")),
            str(row.get("player", "")).lower(),
        )

        game_key = "|".join(
            sorted(
                [
                    str(row.get("team", "")),
                    str(row.get("opponent", "")),
                ]
            )
        )

        if player_key in used_players:
            continue

        if used_games.get(game_key, 0) >= 2:
            continue

        selected_rows.append(row)
        used_players.add(player_key)
        used_games[game_key] = (
            used_games.get(game_key, 0) + 1
        )

        if len(selected_rows) >= size:
            break

    if not selected_rows:
        return candidates.iloc[0:0].copy()

    return pd.DataFrame(selected_rows).reset_index(drop=True)


def prepare_candidates(
    combined: pd.DataFrame,
) -> pd.DataFrame:
    if combined.empty:
        return combined

    available = ~combined["injury_status"].isin(
        [
            "OUT",
            "INACTIVE",
            "DOUBTFUL",
            "SUSPENDED",
        ]
    )

    valid_direction = combined[
        "research_direction"
    ].isin(["OVER", "UNDER"])

    hard_blocked = combined[
        "research_degrader_status"
    ].eq("HARD_BLOCK")

    candidate = combined[
        available
        & valid_direction
        & ~hard_blocked
        & combined["player"].ne("")
        & combined["prop_type"].ne("")
        & combined["line"].notna()
    ].copy()

    candidate = remove_duplicate_players(candidate)

    return candidate.sort_values(
        [
            "composite_score",
            "probability",
            "research_score",
        ],
        ascending=False,
    )


def write_slip(
    frame: pd.DataFrame,
    output: Path,
    slip_name: str,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)

    result = frame.copy()
    result["slip_name"] = slip_name
    result["leg_number"] = range(1, len(result) + 1)
    result["slip_mode"] = "RESEARCH_ONLY"
    result["production_approved"] = 0

    preferred = [
        "slip_name",
        "leg_number",
        "sport",
        "player",
        "team",
        "opponent",
        "prop_type",
        "line",
        "research_direction",
        "composite_score",
        "research_score",
        "decision_strength",
        "direction_gap",
        "probability",
        "opportunity_score",
        "matchup_score",
        "data_quality",
        "line_value_score",
        "selection_path",
        "research_degrader_status",
        "injury_status",
        "lineup_confirmed",
        "starter_confirmed",
        "slip_mode",
        "production_approved",
        "slip_builder_version",
    ]

    columns = [
        column
        for column in preferred
        if column in result.columns
    ]

    result[columns].to_csv(output, index=False)


def build_daily_slips(
    live_directory: Path,
) -> dict[str, object]:
    wnba = normalize_board(
        live_directory / "wnba_selection_path_board.csv",
        "WNBA",
    )

    if wnba.empty:
        wnba = normalize_board(
            live_directory / "wnba_research_board.csv",
            "WNBA",
        )

    mlb = normalize_board(
        live_directory / "mlb_scored_board.csv",
        "MLB",
    )

    combined = pd.concat(
        [
            frame
            for frame in [wnba, mlb]
            if not frame.empty
        ],
        ignore_index=True,
        sort=False,
    )

    candidates = prepare_candidates(combined)

    power_candidates = candidates[
        candidates["composite_score"].ge(68)
        & candidates["research_score"].ge(65)
        & candidates["direction_gap"].ge(10)
        & candidates["data_quality"].ge(55)
    ].copy()

    flex_candidates = candidates[
        candidates["composite_score"].ge(60)
        & candidates["research_score"].ge(58)
        & candidates["direction_gap"].ge(7)
    ].copy()

    power_2 = select_diversified(
        power_candidates,
        2,
    )

    power_4 = select_diversified(
        power_candidates,
        4,
    )

    flex_4 = select_diversified(
        flex_candidates,
        4,
    )

    flex_6 = select_diversified(
        flex_candidates,
        6,
    )

    all_candidates_path = (
        live_directory
        / "research_slip_candidates.csv"
    )

    candidates.to_csv(
        all_candidates_path,
        index=False,
    )

    outputs = {
        "research_power_2": (
            live_directory
            / "research_power_2_leg.csv"
        ),
        "research_power_4": (
            live_directory
            / "research_power_4_leg.csv"
        ),
        "research_flex_4": (
            live_directory
            / "research_flex_4_leg.csv"
        ),
        "research_flex_6": (
            live_directory
            / "research_flex_6_leg.csv"
        ),
    }

    write_slip(
        power_2,
        outputs["research_power_2"],
        "RESEARCH_POWER_2",
    )

    write_slip(
        power_4,
        outputs["research_power_4"],
        "RESEARCH_POWER_4",
    )

    write_slip(
        flex_4,
        outputs["research_flex_4"],
        "RESEARCH_FLEX_4",
    )

    write_slip(
        flex_6,
        outputs["research_flex_6"],
        "RESEARCH_FLEX_6",
    )

    return {
        "status": "COMPLETE",
        "research_only": True,
        "production_approved": False,
        "candidate_rows": len(candidates),
        "power_candidate_rows": len(power_candidates),
        "flex_candidate_rows": len(flex_candidates),
        "outputs": {
            key: str(value)
            for key, value in outputs.items()
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--date",
        default=pd.Timestamp.now().strftime("%Y-%m-%d"),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    live_directory = (
        ROOT
        / "data"
        / "live"
        / args.date
    )

    result = build_daily_slips(live_directory)

    print("SPORTS HUB RESEARCH SLIP BUILDER")
    print("Date:", args.date)
    print("Status:", result["status"])
    print("Candidate rows:", result["candidate_rows"])

    for name, output in result["outputs"].items():
        print(f"{name}: {output}")


if __name__ == "__main__":
    main()
