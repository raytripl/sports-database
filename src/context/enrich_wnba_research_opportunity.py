"""Merge WNBA opportunity projections into research-only scored outputs.

This module runs after the protected v22-control scorer. It does not change
production fields, production grades, production selections, recommendation
flags, model registry values, or promotion gates.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


VERSION = "WNBA_RESEARCH_OPPORTUNITY_ENRICHMENT_V1"

PROJECTION_COLUMNS = (
    "expected_minutes",
    "minutes_floor",
    "minutes_ceiling",
    "minutes_confidence",
    "rotation_rank",
    "expected_usage_rate",
    "usage_delta",
    "expected_fga",
    "expected_fg2a",
    "expected_fg3a",
    "expected_fta",
    "expected_rebound_chances",
    "expected_offensive_rebound_chances",
    "expected_defensive_rebound_chances",
    "expected_assist_chances",
    "expected_potential_assists",
    "expected_touches",
    "expected_steal_opportunities",
    "expected_block_opportunities",
    "expected_turnover_opportunities",
    "teammate_out_count",
    "teammate_questionable_count",
    "teammate_on_off_sample",
    "source_freshness_minutes",
    "projection_confidence",
    "team_projected_minutes",
    "team_active_projection_count",
    "team_minutes_gap_to_200",
)

PROJECTION_TEXT_COLUMNS = (
    "lineup_status",
    "teammate_context",
    "projection_source",
    "projection_notes",
    "team_rotation_status",
)

PROTECTED_COLUMNS = {
    "direction",
    "grade",
    "model_score",
    "recommended",
    "entry_type",
    "pick_level",
    "final_selection",
    "final_rank",
    "overall_rank",
    "same_player_rank",
    "candidate_action",
    "decision_flow",
    "eligibility_status",
    "final_model_version",
    "production_status",
    "production_approved",
    "recommendations_enabled",
}


def normalize_name(value: object) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def first_existing(
    frame: pd.DataFrame,
    candidates: Iterable[str],
) -> str | None:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate

    return None


def numeric(
    frame: pd.DataFrame,
    candidates: Iterable[str],
    default: float = 0.0,
) -> pd.Series:
    column = first_existing(frame, candidates)

    if column is None:
        return pd.Series(
            default,
            index=frame.index,
            dtype="float64",
        )

    return pd.to_numeric(
        frame[column],
        errors="coerce",
    ).fillna(default)


def bounded(
    values: pd.Series,
    low: float = 0.0,
    high: float = 100.0,
) -> pd.Series:
    return pd.to_numeric(
        values,
        errors="coerce",
    ).fillna(0.0).clip(low, high)


def expected_stat_for_prop(
    board: pd.DataFrame,
) -> pd.Series:
    prop = (
        board.get(
            "prop_type",
            pd.Series("", index=board.index),
        )
        .fillna("")
        .astype(str)
        .str.lower()
    )

    points_proxy = (
        numeric(board, ["expected_fg2a"]) * 0.96
        + numeric(board, ["expected_fg3a"]) * 1.02
        + numeric(board, ["expected_fta"]) * 0.78
    )

    rebound_proxy = (
        numeric(
            board,
            ["expected_rebound_chances"],
        )
        * 0.58
    )

    assist_proxy = (
        numeric(
            board,
            ["expected_potential_assists"],
        )
        * 0.46
    )

    steal_proxy = (
        numeric(
            board,
            ["expected_steal_opportunities"],
        )
        * 0.32
    )

    block_proxy = (
        numeric(
            board,
            ["expected_block_opportunities"],
        )
        * 0.38
    )

    turnover_proxy = (
        numeric(
            board,
            ["expected_turnover_opportunities"],
        )
        * 0.55
    )

    expected = pd.Series(
        np.nan,
        index=board.index,
        dtype="float64",
    )

    expected.loc[prop.eq("points")] = points_proxy
    expected.loc[prop.eq("rebounds")] = rebound_proxy
    expected.loc[prop.eq("assists")] = assist_proxy

    expected.loc[
        prop.isin(
            {
                "pts+rebs",
                "points+rebounds",
            }
        )
    ] = points_proxy + rebound_proxy

    expected.loc[
        prop.isin(
            {
                "pts+asts",
                "points+assists",
            }
        )
    ] = points_proxy + assist_proxy

    expected.loc[
        prop.isin(
            {
                "rebs+asts",
                "rebounds+assists",
            }
        )
    ] = rebound_proxy + assist_proxy

    expected.loc[
        prop.isin(
            {
                "pts+rebs+asts",
                "pra",
                "points+rebounds+assists",
            }
        )
    ] = (
        points_proxy
        + rebound_proxy
        + assist_proxy
    )

    expected.loc[
        prop.str.contains(
            "fantasy",
            regex=False,
        )
    ] = (
        points_proxy
        + 1.2 * rebound_proxy
        + 1.5 * assist_proxy
        + 3.0 * steal_proxy
        + 3.0 * block_proxy
        - turnover_proxy
    )

    expected.loc[
        prop.isin(
            {
                "fg attempted",
                "field goals attempted",
            }
        )
    ] = numeric(board, ["expected_fga"])

    expected.loc[
        prop.isin(
            {
                "2-pt attempted",
                "two pointers attempted",
            }
        )
    ] = numeric(board, ["expected_fg2a"])

    expected.loc[
        prop.isin(
            {
                "3-pt attempted",
                "three pointers attempted",
            }
        )
    ] = numeric(board, ["expected_fg3a"])

    expected.loc[
        prop.isin(
            {
                "free throws attempted",
                "ft attempted",
            }
        )
    ] = numeric(board, ["expected_fta"])

    expected.loc[
        prop.isin(
            {
                "def rebounds",
                "defensive rebounds",
            }
        )
    ] = (
        numeric(
            board,
            ["expected_defensive_rebound_chances"],
        )
        * 0.58
    )

    expected.loc[
        prop.isin(
            {
                "off rebounds",
                "offensive rebounds",
            }
        )
    ] = (
        numeric(
            board,
            ["expected_offensive_rebound_chances"],
        )
        * 0.48
    )

    expected.loc[prop.eq("steals")] = steal_proxy
    expected.loc[prop.eq("blocked shots")] = block_proxy
    expected.loc[prop.eq("turnovers")] = turnover_proxy

    expected.loc[
        prop.isin(
            {
                "blks+stls",
                "blocks+steals",
                "stocks",
            }
        )
    ] = steal_proxy + block_proxy

    return expected.round(3)


def calculate_projection_opportunity_score(
    board: pd.DataFrame,
) -> pd.Series:
    minutes = numeric(
        board,
        ["expected_minutes"],
    )

    confidence = numeric(
        board,
        [
            "projection_confidence",
            "minutes_confidence",
        ],
        0.0,
    )

    fga = numeric(
        board,
        ["expected_fga"],
    )

    touches = numeric(
        board,
        ["expected_touches"],
    )

    rebound_chances = numeric(
        board,
        ["expected_rebound_chances"],
    )

    potential_assists = numeric(
        board,
        ["expected_potential_assists"],
    )

    usage = numeric(
        board,
        ["expected_usage_rate"],
    )

    starter = numeric(
        board,
        [
            "opportunity_starter_confirmed",
            "starter_confirmed",
        ],
    )

    lineup = numeric(
        board,
        [
            "opportunity_lineup_confirmed",
            "lineup_confirmed",
        ],
    )

    rotation_rank = numeric(
        board,
        ["rotation_rank"],
        20.0,
    )

    injury = (
        board.get(
            "opportunity_injury_status",
            board.get(
                "injury_status",
                pd.Series("", index=board.index),
            ),
        )
        .fillna("")
        .astype(str)
        .str.upper()
    )

    base = (
        minutes.div(40.0).clip(0.0, 1.0) * 28.0
        + fga.div(18.0).clip(0.0, 1.0) * 13.0
        + touches.div(80.0).clip(0.0, 1.0) * 12.0
        + rebound_chances.div(20.0).clip(0.0, 1.0) * 10.0
        + potential_assists.div(15.0).clip(0.0, 1.0) * 10.0
        + usage.div(30.0).clip(0.0, 1.0) * 10.0
        + confidence.clip(0.0, 1.0) * 9.0
        + starter.clip(0.0, 1.0) * 4.0
        + lineup.clip(0.0, 1.0) * 2.0
        + rotation_rank.le(5).astype(float) * 2.0
    )

    base = base.where(
        ~injury.isin(
            {
                "OUT",
                "INACTIVE",
                "SUSPENDED",
            }
        ),
        0.0,
    )

    base = base.where(
        ~injury.eq("DOUBTFUL"),
        base * 0.35,
    )

    base = base.where(
        ~injury.isin(
            {
                "QUESTIONABLE",
                "GTD",
                "GAME TIME DECISION",
            }
        ),
        base * 0.82,
    )

    return bounded(base).round(1)


def calculate_role_score(
    board: pd.DataFrame,
) -> pd.Series:
    minutes = numeric(
        board,
        ["expected_minutes"],
    )

    starter = numeric(
        board,
        [
            "opportunity_starter_confirmed",
            "starter_confirmed",
        ],
    )

    lineup = numeric(
        board,
        [
            "opportunity_lineup_confirmed",
            "lineup_confirmed",
        ],
    )

    rotation_rank = numeric(
        board,
        ["rotation_rank"],
        20.0,
    )

    touches = numeric(
        board,
        ["expected_touches"],
    )

    usage = numeric(
        board,
        ["expected_usage_rate"],
    )

    score = (
        minutes.div(36.0).clip(0.0, 1.0) * 45.0
        + starter.clip(0.0, 1.0) * 15.0
        + lineup.clip(0.0, 1.0) * 8.0
        + rotation_rank.le(5).astype(float) * 12.0
        + touches.div(70.0).clip(0.0, 1.0) * 10.0
        + usage.div(28.0).clip(0.0, 1.0) * 10.0
    )

    return bounded(score).round(1)


def calculate_workload_score(
    board: pd.DataFrame,
) -> pd.Series:
    minutes = numeric(
        board,
        ["expected_minutes"],
    )

    floor = numeric(
        board,
        ["minutes_floor"],
    )

    ceiling = numeric(
        board,
        ["minutes_ceiling"],
    )

    confidence = numeric(
        board,
        [
            "projection_confidence",
            "minutes_confidence",
        ],
    )

    spread = (
        ceiling - floor
    ).clip(lower=0.0)

    stability = (
        1.0
        - spread.div(
            minutes.clip(lower=10.0)
        )
    ).clip(0.0, 1.0)

    score = (
        minutes.div(38.0).clip(0.0, 1.0) * 55.0
        + confidence.clip(0.0, 1.0) * 25.0
        + stability * 20.0
    )

    return bounded(score).round(1)


def merge_projection(
    scored: pd.DataFrame,
    projections: pd.DataFrame,
) -> pd.DataFrame:
    output = scored.copy()
    original_protected = {
        column: output[column].copy()
        for column in PROTECTED_COLUMNS
        if column in output.columns
    }

    output["_opportunity_player_key"] = (
        output["player"].map(normalize_name)
    )

    projections = projections.copy()

    projections["_opportunity_player_key"] = (
        projections["player"].map(normalize_name)
    )

    projections = (
        projections.sort_values(
            [
                "_opportunity_player_key",
                "projection_confidence",
                "expected_minutes",
            ],
            ascending=[True, False, False],
        )
        .drop_duplicates(
            "_opportunity_player_key",
            keep="first",
        )
    )

    available_columns = [
        "_opportunity_player_key",
        *[
            column
            for column in PROJECTION_COLUMNS
            if column in projections.columns
        ],
        *[
            column
            for column in PROJECTION_TEXT_COLUMNS
            if column in projections.columns
        ],
    ]

    for optional in (
        "injury_status",
        "lineup_confirmed",
        "starter_confirmed",
        "projected_starter",
    ):
        if optional in projections.columns:
            available_columns.append(optional)

    projection_subset = projections[
        list(dict.fromkeys(available_columns))
    ].copy()

    projection_subset = projection_subset.rename(
        columns={
            "injury_status": (
                "opportunity_injury_status"
            ),
            "lineup_confirmed": (
                "opportunity_lineup_confirmed"
            ),
            "starter_confirmed": (
                "opportunity_starter_confirmed"
            ),
            "projected_starter": (
                "opportunity_projected_starter"
            ),
        }
    )

    output = output.merge(
        projection_subset,
        on="_opportunity_player_key",
        how="left",
        validate="many_to_one",
    )

    output["opportunity_projection_matched"] = (
        output["expected_minutes"].notna().astype(int)
    )

    output["projected_prop_result"] = (
        expected_stat_for_prop(output)
    )

    line = numeric(
        output,
        ["line"],
        np.nan,
    )

    output["projected_prop_edge"] = (
        output["projected_prop_result"] - line
    ).round(3)

    output["projected_prop_edge_percent"] = (
        output["projected_prop_edge"]
        .div(
            line.abs().clip(lower=1.0)
        )
        .mul(100.0)
        .round(3)
    )

    output[
        "research_projection_opportunity_score"
    ] = calculate_projection_opportunity_score(
        output
    )

    output[
        "research_projection_role_score"
    ] = calculate_role_score(output)

    output[
        "research_projection_workload_score"
    ] = calculate_workload_score(output)

    historical_opportunity = numeric(
        output,
        ["opportunity_score"],
    )

    projection_opportunity = numeric(
        output,
        [
            "research_projection_opportunity_score"
        ],
    )

    projection_confidence = numeric(
        output,
        ["projection_confidence"],
    ).clip(0.0, 1.0)

    matched = output[
        "opportunity_projection_matched"
    ].eq(1)

    projection_weight = (
        0.25
        + projection_confidence * 0.35
    ).clip(0.25, 0.60)

    blended = (
        historical_opportunity
        * (1.0 - projection_weight)
        + projection_opportunity
        * projection_weight
    )

    output[
        "research_blended_opportunity_score"
    ] = historical_opportunity

    output.loc[
        matched,
        "research_blended_opportunity_score",
    ] = blended.loc[matched]

    output[
        "research_blended_opportunity_score"
    ] = bounded(
        output[
            "research_blended_opportunity_score"
        ]
    ).round(1)

    output["research_opportunity_delta"] = (
        output[
            "research_blended_opportunity_score"
        ]
        - historical_opportunity
    ).round(1)

    projected_edge = numeric(
        output,
        ["projected_prop_edge_percent"],
    ).clip(-50.0, 50.0)

    output[
        "research_projection_edge_score"
    ] = (
        50.0 + projected_edge
    ).clip(0.0, 100.0).round(1)

    injury = (
        output.get(
            "opportunity_injury_status",
            pd.Series("", index=output.index),
        )
        .fillna("")
        .astype(str)
        .str.upper()
    )

    confidence = numeric(
        output,
        ["projection_confidence"],
    )

    rotation_status = (
        output.get(
            "team_rotation_status",
            pd.Series("", index=output.index),
        )
        .fillna("")
        .astype(str)
        .str.upper()
    )

    reasons = []

    for index in output.index:
        row_reasons: list[str] = []

        if not matched.at[index]:
            row_reasons.append(
                "NO_OPPORTUNITY_PROJECTION_MATCH"
            )

        if confidence.at[index] < 0.55:
            row_reasons.append(
                "LOW_PROJECTION_CONFIDENCE"
            )

        if injury.at[index] in {
            "OUT",
            "INACTIVE",
            "SUSPENDED",
        }:
            row_reasons.append(
                "PLAYER_UNAVAILABLE"
            )

        if injury.at[index] in {
            "QUESTIONABLE",
            "DOUBTFUL",
            "GTD",
            "GAME TIME DECISION",
        }:
            row_reasons.append(
                "INJURY_UNCERTAINTY"
            )

        if (
            rotation_status.at[index]
            and rotation_status.at[index]
            not in {
                "COMPLETE",
                "BALANCED",
                "VALID",
            }
        ):
            row_reasons.append(
                f"ROTATION_{rotation_status.at[index]}"
            )

        reasons.append(
            "|".join(row_reasons)
        )

    output[
        "research_opportunity_exclusion_reason"
    ] = reasons

    output[
        "research_opportunity_eligible"
    ] = (
        matched
        & confidence.ge(0.55)
        & ~injury.isin(
            {
                "OUT",
                "INACTIVE",
                "SUSPENDED",
                "DOUBTFUL",
            }
        )
    ).astype(int)

    output["research_opportunity_version"] = VERSION
    output["research_only"] = 1
    output["research_opportunity_production_approved"] = 0
    output["production_fields_unchanged"] = 1

    for column, original in original_protected.items():
        output[column] = original.values

    output = output.drop(
        columns=["_opportunity_player_key"],
        errors="ignore",
    )

    return output


def enrich_file(
    scored_path: Path,
    projection_path: Path,
    output_path: Path,
) -> dict[str, object]:
    if not scored_path.exists():
        raise FileNotFoundError(
            f"WNBA scored board not found: {scored_path}"
        )

    if not projection_path.exists():
        raise FileNotFoundError(
            "WNBA opportunity projection not found: "
            f"{projection_path}"
        )

    scored = pd.read_csv(
        scored_path,
        low_memory=False,
    )

    projections = pd.read_csv(
        projection_path,
        low_memory=False,
    )

    if "player" not in scored.columns:
        raise ValueError(
            "WNBA scored board is missing player"
        )

    if "player" not in projections.columns:
        raise ValueError(
            "WNBA opportunity projection is missing player"
        )

    enriched = merge_projection(
        scored,
        projections,
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    enriched.to_csv(
        output_path,
        index=False,
    )

    matched_rows = int(
        enriched[
            "opportunity_projection_matched"
        ].sum()
    )

    eligible_rows = int(
        enriched[
            "research_opportunity_eligible"
        ].sum()
    )

    return {
        "status": "COMPLETE",
        "version": VERSION,
        "input_rows": len(scored),
        "projection_rows": len(projections),
        "output_rows": len(enriched),
        "matched_rows": matched_rows,
        "unmatched_rows": len(enriched) - matched_rows,
        "research_opportunity_eligible_rows": (
            eligible_rows
        ),
        "output_path": str(output_path),
        "research_only": True,
        "production_approved": False,
        "production_fields_unchanged": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--scored",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--projections",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    result = enrich_file(
        scored_path=args.scored,
        projection_path=args.projections,
        output_path=args.output,
    )

    print("=" * 72)
    print("WNBA RESEARCH OPPORTUNITY ENRICHMENT")
    print("=" * 72)

    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
