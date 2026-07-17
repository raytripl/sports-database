from __future__ import annotations

import pandas as pd

from src.audit.research_calibration_suite import (
    component_lift_report,
    ranking_report,
    summarize_decisions,
    wilson_lower_bound,
)


def sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player": [
                "A",
                "B",
                "C",
                "D",
                "E",
                "F",
            ],
            "research_rank": [
                1,
                2,
                3,
                4,
                5,
                6,
            ],
            "research_score": [
                90,
                85,
                80,
                70,
                60,
                50,
            ],
            "opportunity_component": [
                95,
                90,
                85,
                40,
                35,
                30,
            ],
            "grade_result": [
                "WIN",
                "WIN",
                "WIN",
                "LOSS",
                "LOSS",
                "LOSS",
            ],
            "directional_margin": [
                3.5,
                2.5,
                1.0,
                -1.0,
                -2.0,
                -3.0,
            ],
            "projection_absolute_error": [
                1.0,
                1.5,
                2.0,
                4.0,
                5.0,
                6.0,
            ],
        }
    )


def test_wilson_lower_bound_is_valid() -> None:
    result = wilson_lower_bound(
        wins=7,
        decisions=10,
    )

    assert 0.0 < result < 0.70


def test_summarize_decisions_counts_results() -> None:
    summary = summarize_decisions(
        sample_frame()
    )

    assert summary["wins"] == 3
    assert summary["losses"] == 3
    assert summary["decisions"] == 6
    assert summary["hit_rate"] == 0.5


def test_ranking_report_includes_full_board() -> None:
    report = ranking_report(
        sample_frame()
    )

    assert not report.empty
    assert report.iloc[-1]["cutoff"] == 6
    assert report.iloc[-1]["decisions"] == 6


def test_component_lift_identifies_signal() -> None:
    report = component_lift_report(
        sample_frame(),
        minimum_valid_rows=4,
    )

    assert not report.empty

    opportunity = report[
        report["component"].eq(
            "opportunity_component"
        )
    ]

    assert not opportunity.empty
    assert (
        opportunity.iloc[0][
            "top_vs_bottom_lift"
        ]
        > 0
    )
