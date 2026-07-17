from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Iterable

import pandas as pd


DECISION_RESULTS = {"WIN", "LOSS"}


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


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


def summarize_decisions(
    frame: pd.DataFrame,
) -> dict[str, object]:
    decided = frame[
        frame["grade_result"].isin(DECISION_RESULTS)
    ].copy()

    wins = int(
        decided["grade_result"].eq("WIN").sum()
    )
    losses = int(
        decided["grade_result"].eq("LOSS").sum()
    )
    decisions = wins + losses

    pushes = int(
        frame["grade_result"].eq("PUSH").sum()
    )
    unresolved = int(
        frame["grade_result"].eq("UNRESOLVED").sum()
    )

    return {
        "rows": int(len(frame)),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "unresolved": unresolved,
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
                decided["directional_margin"]
            ).mean()
            if (
                decisions
                and "directional_margin"
                in decided.columns
            )
            else pd.NA
        ),
        "average_projection_absolute_error": (
            numeric(
                decided[
                    "projection_absolute_error"
                ]
            ).mean()
            if (
                decisions
                and "projection_absolute_error"
                in decided.columns
            )
            else pd.NA
        ),
        "average_research_score": (
            numeric(
                decided["research_score"]
            ).mean()
            if (
                decisions
                and "research_score"
                in decided.columns
            )
            else pd.NA
        ),
    }


def find_first_column(
    frame: pd.DataFrame,
    candidates: Iterable[str],
) -> str | None:
    for column in candidates:
        if column in frame.columns:
            return column

    return None


def ranking_report(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    rank_column = find_first_column(
        frame,
        (
            "research_rank",
            "rank",
            "overall_rank",
        ),
    )

    score_column = find_first_column(
        frame,
        (
            "research_score",
            "score",
        ),
    )

    working = frame.copy()

    if rank_column:
        working["_sort_rank"] = numeric(
            working[rank_column]
        )
        working = working.sort_values(
            "_sort_rank",
            ascending=True,
            na_position="last",
        )
    elif score_column:
        working["_sort_score"] = numeric(
            working[score_column]
        )
        working = working.sort_values(
            "_sort_score",
            ascending=False,
            na_position="last",
        )
    else:
        raise ValueError(
            "No ranking or research-score column found."
        )

    cutoffs = [
        5,
        10,
        15,
        20,
        25,
        30,
        40,
        50,
        75,
        100,
        len(working),
    ]

    cutoffs = sorted(
        {
            cutoff
            for cutoff in cutoffs
            if cutoff <= len(working)
        }
    )

    rows: list[dict[str, object]] = []

    for cutoff in cutoffs:
        selected = working.head(cutoff)
        summary = summarize_decisions(selected)

        rows.append(
            {
                "ranking_scope": f"TOP_{cutoff}",
                "cutoff": cutoff,
                **summary,
            }
        )

    return pd.DataFrame(rows)


def score_bucket_report(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    if "research_score" not in frame.columns:
        return pd.DataFrame()

    working = frame.copy()
    working["research_score_numeric"] = numeric(
        working["research_score"]
    )

    bins = [
        -float("inf"),
        40,
        50,
        55,
        60,
        65,
        70,
        75,
        80,
        85,
        90,
        float("inf"),
    ]

    labels = [
        "<40",
        "40-49.99",
        "50-54.99",
        "55-59.99",
        "60-64.99",
        "65-69.99",
        "70-74.99",
        "75-79.99",
        "80-84.99",
        "85-89.99",
        "90+",
    ]

    working["research_score_bucket"] = pd.cut(
        working["research_score_numeric"],
        bins=bins,
        labels=labels,
        right=False,
    )

    rows: list[dict[str, object]] = []

    for bucket, group in working.groupby(
        "research_score_bucket",
        observed=False,
        dropna=False,
    ):
        if group.empty:
            continue

        rows.append(
            {
                "research_score_bucket": str(bucket),
                **summarize_decisions(group),
            }
        )

    return pd.DataFrame(rows)


def opportunity_bucket_report(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    opportunity_column = find_first_column(
        frame,
        (
            "research_opportunity_score_used",
            "research_blended_opportunity_score",
            "research_projection_opportunity_score",
            "opportunity_component",
        ),
    )

    if not opportunity_column:
        return pd.DataFrame()

    working = frame.copy()
    working["opportunity_numeric"] = numeric(
        working[opportunity_column]
    )

    bins = [
        -float("inf"),
        40,
        50,
        60,
        70,
        75,
        80,
        85,
        90,
        float("inf"),
    ]

    labels = [
        "<40",
        "40-49.99",
        "50-59.99",
        "60-69.99",
        "70-74.99",
        "75-79.99",
        "80-84.99",
        "85-89.99",
        "90+",
    ]

    working["opportunity_bucket"] = pd.cut(
        working["opportunity_numeric"],
        bins=bins,
        labels=labels,
        right=False,
    )

    rows: list[dict[str, object]] = []

    for bucket, group in working.groupby(
        "opportunity_bucket",
        observed=False,
        dropna=False,
    ):
        if group.empty:
            continue

        rows.append(
            {
                "opportunity_column": opportunity_column,
                "opportunity_bucket": str(bucket),
                **summarize_decisions(group),
            }
        )

    return pd.DataFrame(rows)


def direction_gap_report(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    if "research_direction_gap" not in frame.columns:
        return pd.DataFrame()

    working = frame.copy()
    working["direction_gap_numeric"] = numeric(
        working["research_direction_gap"]
    )

    bins = [
        -float("inf"),
        5,
        7.5,
        10,
        12.5,
        15,
        20,
        30,
        50,
        float("inf"),
    ]

    labels = [
        "<5",
        "5-7.49",
        "7.5-9.99",
        "10-12.49",
        "12.5-14.99",
        "15-19.99",
        "20-29.99",
        "30-49.99",
        "50+",
    ]

    working["direction_gap_bucket"] = pd.cut(
        working["direction_gap_numeric"],
        bins=bins,
        labels=labels,
        right=False,
    )

    rows: list[dict[str, object]] = []

    for bucket, group in working.groupby(
        "direction_gap_bucket",
        observed=False,
        dropna=False,
    ):
        if group.empty:
            continue

        rows.append(
            {
                "direction_gap_bucket": str(bucket),
                **summarize_decisions(group),
            }
        )

    return pd.DataFrame(rows)


def projection_error_report(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    required = {
        "prop_type",
        "grade_result",
        "projection_error",
        "projection_absolute_error",
    }

    if not required.issubset(frame.columns):
        return pd.DataFrame()

    working = frame[
        frame["grade_result"].isin(
            ["WIN", "LOSS", "PUSH"]
        )
    ].copy()

    rows: list[dict[str, object]] = []

    group_columns = [
        "prop_type",
    ]

    if "prop_family" in working.columns:
        group_columns.insert(0, "prop_family")

    for keys, group in working.groupby(
        group_columns,
        dropna=False,
    ):
        if not isinstance(keys, tuple):
            keys = (keys,)

        key_values = dict(
            zip(
                group_columns,
                keys,
            )
        )

        rows.append(
            {
                **key_values,
                **summarize_decisions(group),
                "mean_projection_error": numeric(
                    group["projection_error"]
                ).mean(),
                "median_projection_error": numeric(
                    group["projection_error"]
                ).median(),
                "mean_absolute_error": numeric(
                    group[
                        "projection_absolute_error"
                    ]
                ).mean(),
                "median_absolute_error": numeric(
                    group[
                        "projection_absolute_error"
                    ]
                ).median(),
                "projection_bias_direction": (
                    "TOO_LOW"
                    if numeric(
                        group["projection_error"]
                    ).mean() > 0
                    else "TOO_HIGH"
                ),
            }
        )

    return pd.DataFrame(rows).sort_values(
        [
            "decisions",
            "mean_absolute_error",
        ],
        ascending=[
            False,
            True,
        ],
    )


def component_columns(
    frame: pd.DataFrame,
) -> list[str]:
    explicit_candidates = [
        "statistical_edge_component",
        "opportunity_component",
        "directional_matchup_component",
        "line_value_component",
        "data_quality_component",
        "research_score",
        "research_confidence",
        "research_direction_gap",
        "research_projection_opportunity_score",
        "research_blended_opportunity_score",
        "research_opportunity_score_used",
        "projected_prop_result",
        "projection_edge",
        "projection_edge_pct",
        "minutes_projection",
        "usage_projection",
        "matchup_score",
        "role_score",
        "market_score",
    ]

    columns = [
        column
        for column in explicit_candidates
        if column in frame.columns
    ]

    for column in frame.columns:
        lowered = column.lower()

        if (
            column not in columns
            and (
                lowered.endswith("_component")
                or lowered.endswith("_score")
                or lowered.endswith("_gap")
                or lowered.endswith("_edge")
            )
        ):
            columns.append(column)

    excluded = {
        "actual_result",
        "raw_margin",
        "directional_margin",
        "projection_error",
        "projection_absolute_error",
    }

    return [
        column
        for column in columns
        if column not in excluded
    ]


def component_lift_report(
    frame: pd.DataFrame,
    *,
    minimum_valid_rows: int = 10,
) -> pd.DataFrame:
    decided = frame[
        frame["grade_result"].isin(
            DECISION_RESULTS
        )
    ].copy()

    if decided.empty:
        return pd.DataFrame()

    decided["win_binary"] = (
        decided["grade_result"].eq("WIN")
    ).astype(int)

    baseline_hit_rate = float(
        decided["win_binary"].mean()
    )

    rows: list[dict[str, object]] = []

    for column in component_columns(decided):
        values = numeric(decided[column])
        valid = decided.loc[
            values.notna()
        ].copy()

        if len(valid) < minimum_valid_rows:
            continue

        valid["_component_numeric"] = numeric(
            valid[column]
        )

        valid = valid.sort_values(
            "_component_numeric",
            ascending=True,
        )

        try:
            valid["_quartile"] = pd.qcut(
                valid["_component_numeric"],
                q=4,
                duplicates="drop",
            )
        except ValueError:
            continue

        correlation = valid[
            [
                "_component_numeric",
                "win_binary",
            ]
        ].corr().iloc[0, 1]

        quartiles = list(
            valid.groupby(
                "_quartile",
                observed=False,
            )
        )

        if len(quartiles) < 2:
            continue

        bottom_group = quartiles[0][1]
        top_group = quartiles[-1][1]

        top_summary = summarize_decisions(
            top_group
        )
        bottom_summary = summarize_decisions(
            bottom_group
        )

        top_hit_rate = top_summary["hit_rate"]
        bottom_hit_rate = bottom_summary["hit_rate"]

        lift_vs_baseline = (
            float(top_hit_rate) - baseline_hit_rate
            if pd.notna(top_hit_rate)
            else pd.NA
        )

        top_vs_bottom_lift = (
            float(top_hit_rate)
            - float(bottom_hit_rate)
            if (
                pd.notna(top_hit_rate)
                and pd.notna(bottom_hit_rate)
            )
            else pd.NA
        )

        rows.append(
            {
                "component": column,
                "valid_rows": len(valid),
                "correlation_with_win": correlation,
                "baseline_hit_rate": baseline_hit_rate,
                "bottom_quartile_hit_rate": (
                    bottom_hit_rate
                ),
                "top_quartile_hit_rate": (
                    top_hit_rate
                ),
                "top_quartile_lift_vs_baseline": (
                    lift_vs_baseline
                ),
                "top_vs_bottom_lift": (
                    top_vs_bottom_lift
                ),
                "bottom_quartile_decisions": (
                    bottom_summary["decisions"]
                ),
                "top_quartile_decisions": (
                    top_summary["decisions"]
                ),
                "top_quartile_wilson_lower": (
                    top_summary["wilson_lower"]
                ),
            }
        )

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values(
        [
            "top_quartile_lift_vs_baseline",
            "top_quartile_wilson_lower",
        ],
        ascending=[
            False,
            False,
        ],
        na_position="last",
    )


def confidence_calibration_report(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    confidence_column = find_first_column(
        frame,
        (
            "research_confidence",
            "predicted_probability",
            "win_probability",
            "probability",
        ),
    )

    if not confidence_column:
        return pd.DataFrame()

    working = frame[
        frame["grade_result"].isin(
            DECISION_RESULTS
        )
    ].copy()

    working["confidence_numeric"] = numeric(
        working[confidence_column]
    )

    if working["confidence_numeric"].dropna().empty:
        return pd.DataFrame()

    max_confidence = (
        working["confidence_numeric"]
        .dropna()
        .max()
    )

    if max_confidence <= 1.0:
        working["confidence_probability"] = (
            working["confidence_numeric"]
        )
    else:
        working["confidence_probability"] = (
            working["confidence_numeric"] / 100.0
        )

    bins = [
        0.0,
        0.50,
        0.55,
        0.60,
        0.65,
        0.70,
        0.75,
        0.80,
        0.85,
        0.90,
        0.95,
        1.01,
    ]

    labels = [
        "<50%",
        "50-54.99%",
        "55-59.99%",
        "60-64.99%",
        "65-69.99%",
        "70-74.99%",
        "75-79.99%",
        "80-84.99%",
        "85-89.99%",
        "90-94.99%",
        "95%+",
    ]

    working["confidence_bucket"] = pd.cut(
        working["confidence_probability"],
        bins=bins,
        labels=labels,
        right=False,
    )

    working["win_binary"] = (
        working["grade_result"].eq("WIN")
    ).astype(int)

    rows: list[dict[str, object]] = []

    for bucket, group in working.groupby(
        "confidence_bucket",
        observed=False,
        dropna=False,
    ):
        if group.empty:
            continue

        summary = summarize_decisions(group)

        average_predicted_probability = (
            group[
                "confidence_probability"
            ].mean()
        )

        actual_hit_rate = (
            group["win_binary"].mean()
        )

        rows.append(
            {
                "confidence_column": confidence_column,
                "confidence_bucket": str(bucket),
                **summary,
                "average_predicted_probability": (
                    average_predicted_probability
                ),
                "actual_hit_rate": actual_hit_rate,
                "calibration_error": (
                    actual_hit_rate
                    - average_predicted_probability
                ),
                "absolute_calibration_error": abs(
                    actual_hit_rate
                    - average_predicted_probability
                ),
            }
        )

    return pd.DataFrame(rows)


def classify_failure(
    row: pd.Series,
) -> str:
    if row.get("grade_result") != "LOSS":
        return ""

    projection_error = pd.to_numeric(
        pd.Series(
            [row.get("projection_error")]
        ),
        errors="coerce",
    ).iloc[0]

    absolute_error = pd.to_numeric(
        pd.Series(
            [
                row.get(
                    "projection_absolute_error"
                )
            ]
        ),
        errors="coerce",
    ).iloc[0]

    directional_margin = pd.to_numeric(
        pd.Series(
            [row.get("directional_margin")]
        ),
        errors="coerce",
    ).iloc[0]

    direction = str(
        row.get("research_direction", "")
    ).upper()

    if pd.notna(directional_margin):
        if directional_margin >= -1.0:
            return "NEAR_MISS_VARIANCE"

    if pd.notna(absolute_error):
        if absolute_error >= 8:
            return "SEVERE_PROJECTION_MISS"

        if absolute_error >= 5:
            return "LARGE_PROJECTION_MISS"

    if pd.notna(projection_error):
        if direction == "OVER":
            if projection_error <= -3:
                return "OVER_PROJECTION_TOO_HIGH"

        if direction == "UNDER":
            if projection_error >= 3:
                return "UNDER_PROJECTION_TOO_LOW"

    opportunity_eligible = row.get(
        "research_opportunity_eligible"
    )

    if str(opportunity_eligible).lower() in {
        "false",
        "0",
        "no",
    }:
        return "OPPORTUNITY_GATE_WARNING"

    risk_status = str(
        row.get(
            "research_slate_risk_status",
            "",
        )
    ).upper()

    if risk_status not in {
        "",
        "OK",
        "PASS",
        "CLEAR",
        "ELIGIBLE",
        "NAN",
    }:
        return "SLATE_RISK_WARNING"

    return "UNCLASSIFIED_MODEL_MISS"


def failure_report(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    losses = frame[
        frame["grade_result"].eq("LOSS")
    ].copy()

    if losses.empty:
        return pd.DataFrame()

    losses["failure_category"] = losses.apply(
        classify_failure,
        axis=1,
    )

    player_column = find_first_column(
        losses,
        (
            "player",
            "player_name",
            "name",
            "athlete",
        ),
    )

    preferred_columns = [
        player_column,
        "team",
        "opponent",
        "prop_type",
        "line",
        "research_direction",
        "actual_result",
        "projected_prop_result",
        "projection_error",
        "projection_absolute_error",
        "directional_margin",
        "research_rank",
        "research_score",
        "research_confidence",
        "research_direction_gap",
        "research_opportunity_score_used",
        "research_blended_opportunity_score",
        "research_opportunity_eligible",
        "research_slate_risk_status",
        "research_slate_risk_reason",
        "failure_category",
    ]

    selected_columns = [
        column
        for column in preferred_columns
        if column
        and column in losses.columns
    ]

    return losses[
        selected_columns
    ].sort_values(
        [
            "failure_category",
            "projection_absolute_error",
        ],
        ascending=[
            True,
            False,
        ],
        na_position="last",
    )


def failure_summary_report(
    failures: pd.DataFrame,
) -> pd.DataFrame:
    if (
        failures.empty
        or "failure_category"
        not in failures.columns
    ):
        return pd.DataFrame()

    return (
        failures.groupby(
            "failure_category",
            dropna=False,
        )
        .agg(
            losses=("failure_category", "size"),
            average_projection_absolute_error=(
                "projection_absolute_error",
                "mean",
            ),
            average_directional_margin=(
                "directional_margin",
                "mean",
            ),
            average_research_score=(
                "research_score",
                "mean",
            ),
        )
        .reset_index()
        .sort_values(
            "losses",
            ascending=False,
        )
    )


def under_ranked_winners_report(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    winners = frame[
        frame["grade_result"].eq("WIN")
    ].copy()

    if winners.empty:
        return pd.DataFrame()

    score = (
        numeric(winners["research_score"])
        if "research_score" in winners.columns
        else pd.Series(
            pd.NA,
            index=winners.index,
        )
    )

    rank = (
        numeric(winners["research_rank"])
        if "research_rank" in winners.columns
        else pd.Series(
            pd.NA,
            index=winners.index,
        )
    )

    low_score = score.lt(60)
    low_rank = rank.gt(50)

    winners["under_ranked_reason"] = ""

    winners.loc[
        low_score,
        "under_ranked_reason",
    ] = "LOW_RESEARCH_SCORE"

    winners.loc[
        low_rank,
        "under_ranked_reason",
    ] = winners.loc[
        low_rank,
        "under_ranked_reason",
    ].replace(
        "",
        "LOW_RESEARCH_RANK",
    )

    winners.loc[
        low_score & low_rank,
        "under_ranked_reason",
    ] = "LOW_SCORE_AND_LOW_RANK"

    under_ranked = winners[
        low_score | low_rank
    ].copy()

    player_column = find_first_column(
        under_ranked,
        (
            "player",
            "player_name",
            "name",
            "athlete",
        ),
    )

    preferred_columns = [
        player_column,
        "team",
        "opponent",
        "prop_type",
        "line",
        "research_direction",
        "actual_result",
        "directional_margin",
        "research_rank",
        "research_score",
        "research_confidence",
        "research_direction_gap",
        "research_opportunity_score_used",
        "research_blended_opportunity_score",
        "under_ranked_reason",
    ]

    selected_columns = [
        column
        for column in preferred_columns
        if column
        and column in under_ranked.columns
    ]

    return under_ranked[
        selected_columns
    ].sort_values(
        [
            "research_score",
            "research_rank",
        ],
        ascending=[
            True,
            False,
        ],
        na_position="last",
    )


def feature_correlation_report(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    decided = frame[
        frame["grade_result"].isin(
            DECISION_RESULTS
        )
    ].copy()

    if decided.empty:
        return pd.DataFrame()

    decided["win_binary"] = (
        decided["grade_result"].eq("WIN")
    ).astype(int)

    components = component_columns(decided)

    numeric_frame = pd.DataFrame(
        {
            column: numeric(decided[column])
            for column in components
        }
    )

    numeric_frame["win_binary"] = decided[
        "win_binary"
    ]

    correlations = numeric_frame.corr(
        min_periods=10
    )

    if correlations.empty:
        return pd.DataFrame()

    correlations.index.name = "feature"

    return correlations.reset_index()


def high_correlation_pairs_report(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    components = component_columns(frame)

    numeric_frame = pd.DataFrame(
        {
            column: numeric(frame[column])
            for column in components
        }
    )

    correlations = numeric_frame.corr(
        min_periods=10
    )

    rows: list[dict[str, object]] = []

    for index, first in enumerate(
        correlations.columns
    ):
        for second in correlations.columns[
            index + 1:
        ]:
            value = correlations.loc[
                first,
                second,
            ]

            if pd.isna(value):
                continue

            if abs(value) < 0.70:
                continue

            rows.append(
                {
                    "feature_1": first,
                    "feature_2": second,
                    "correlation": value,
                    "absolute_correlation": abs(
                        value
                    ),
                    "possible_issue": (
                        "POSSIBLE_DOUBLE_COUNTING"
                        if abs(value) >= 0.85
                        else "HIGH_REDUNDANCY"
                    ),
                }
            )

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values(
        "absolute_correlation",
        ascending=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build research-only calibration and "
            "diagnostic reports from graded WNBA props."
        )
    )

    parser.add_argument(
        "--date",
        required=True,
        help="Slate date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--graded",
        default=None,
        help="Optional graded_predictions.csv path.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional calibration output directory.",
    )

    args = parser.parse_args()

    slate_date = args.date

    graded_path = Path(
        args.graded
        or (
            "data/backtests/historical_replay/"
            f"{slate_date}/audit/"
            "graded_predictions.csv"
        )
    )

    output_dir = Path(
        args.output_dir
        or (
            "data/backtests/historical_replay/"
            f"{slate_date}/calibration"
        )
    )

    if not graded_path.exists():
        raise FileNotFoundError(
            f"Graded predictions not found: "
            f"{graded_path}"
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    graded = pd.read_csv(
        graded_path,
        low_memory=False,
    )

    reports: dict[str, pd.DataFrame] = {
        "ranking_report.csv": (
            ranking_report(graded)
        ),
        "score_bucket_report.csv": (
            score_bucket_report(graded)
        ),
        "opportunity_bucket_report.csv": (
            opportunity_bucket_report(graded)
        ),
        "direction_gap_report.csv": (
            direction_gap_report(graded)
        ),
        "projection_error_report.csv": (
            projection_error_report(graded)
        ),
        "component_lift_report.csv": (
            component_lift_report(graded)
        ),
        "confidence_calibration_report.csv": (
            confidence_calibration_report(
                graded
            )
        ),
        "feature_correlation_report.csv": (
            feature_correlation_report(
                graded
            )
        ),
        "high_correlation_pairs.csv": (
            high_correlation_pairs_report(
                graded
            )
        ),
        "under_ranked_winners.csv": (
            under_ranked_winners_report(
                graded
            )
        ),
    }

    failures = failure_report(graded)

    reports["failure_report.csv"] = failures
    reports["failure_summary.csv"] = (
        failure_summary_report(failures)
    )

    for filename, report in reports.items():
        report.to_csv(
            output_dir / filename,
            index=False,
        )

    print("=" * 88)
    print("WNBA RESEARCH CALIBRATION SUITE")
    print("=" * 88)
    print("Date:", slate_date)
    print("Input:", graded_path)
    print("Input rows:", len(graded))
    print()

    print("RANKING PERFORMANCE")
    ranking = reports["ranking_report.csv"]

    if ranking.empty:
        print("No ranking report generated.")
    else:
        print(
            ranking.to_string(
                index=False
            )
        )

    print()
    print("TOP COMPONENT LIFT")
    component_lift = reports[
        "component_lift_report.csv"
    ]

    if component_lift.empty:
        print(
            "No component lift report generated."
        )
    else:
        columns = [
            "component",
            "valid_rows",
            "correlation_with_win",
            "baseline_hit_rate",
            "bottom_quartile_hit_rate",
            "top_quartile_hit_rate",
            "top_quartile_lift_vs_baseline",
            "top_vs_bottom_lift",
            "top_quartile_wilson_lower",
        ]

        print(
            component_lift[
                columns
            ]
            .head(20)
            .to_string(index=False)
        )

    print()
    print("FAILURE SUMMARY")
    failure_summary = reports[
        "failure_summary.csv"
    ]

    if failure_summary.empty:
        print("No losses to classify.")
    else:
        print(
            failure_summary.to_string(
                index=False
            )
        )

    print()
    print("OUTPUTS")

    for path in sorted(
        output_dir.glob("*.csv")
    ):
        print(" ", path)


if __name__ == "__main__":
    main()
