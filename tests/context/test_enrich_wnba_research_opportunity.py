from pathlib import Path

import pandas as pd

from src.context.enrich_wnba_research_opportunity import (
    enrich_file,
    merge_projection,
)


def scored_board() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player": [
                "Test Guard",
                "Unavailable Player",
            ],
            "team": ["AAA", "AAA"],
            "opponent": ["BBB", "BBB"],
            "prop_type": [
                "Assists",
                "Points",
            ],
            "line": [5.5, 12.5],
            "opportunity_score": [60.0, 75.0],
            "direction": ["OVER", "OVER"],
            "grade": ["B", "B+"],
            "model_score": [70.0, 80.0],
            "recommended": [0, 0],
            "final_selection": ["NO PICK", "NO PICK"],
            "final_model_version": [
                "v22-control",
                "v22-control",
            ],
        }
    )


def projection_board() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player": [
                "Test Guard",
                "Unavailable Player",
            ],
            "expected_minutes": [34.0, 0.0],
            "minutes_floor": [30.0, 0.0],
            "minutes_ceiling": [38.0, 0.0],
            "minutes_confidence": [0.85, 0.90],
            "rotation_rank": [2, 10],
            "expected_usage_rate": [24.0, 0.0],
            "expected_fga": [14.0, 0.0],
            "expected_fg2a": [8.0, 0.0],
            "expected_fg3a": [6.0, 0.0],
            "expected_fta": [4.0, 0.0],
            "expected_rebound_chances": [8.0, 0.0],
            "expected_offensive_rebound_chances": [1.0, 0.0],
            "expected_defensive_rebound_chances": [7.0, 0.0],
            "expected_assist_chances": [10.0, 0.0],
            "expected_potential_assists": [13.0, 0.0],
            "expected_touches": [72.0, 0.0],
            "expected_steal_opportunities": [4.0, 0.0],
            "expected_block_opportunities": [1.0, 0.0],
            "expected_turnover_opportunities": [5.0, 0.0],
            "projection_confidence": [0.88, 0.90],
            "injury_status": ["ACTIVE", "OUT"],
            "lineup_confirmed": [1, 0],
            "starter_confirmed": [1, 0],
            "team_rotation_status": ["COMPLETE", "COMPLETE"],
        }
    )


def test_merge_adds_research_opportunity_without_changing_production() -> None:
    scored = scored_board()
    projection = projection_board()

    result = merge_projection(
        scored,
        projection,
    )

    assert len(result) == 2

    assert (
        result.loc[0, "opportunity_projection_matched"]
        == 1
    )

    assert (
        result.loc[
            0,
            "research_projection_opportunity_score",
        ]
        > 0
    )

    assert (
        result.loc[
            0,
            "research_blended_opportunity_score",
        ]
        != result.loc[0, "opportunity_score"]
    )

    assert (
        result.loc[
            0,
            "research_opportunity_eligible",
        ]
        == 1
    )

    assert (
        result.loc[
            1,
            "research_opportunity_eligible",
        ]
        == 0
    )

    assert (
        result.loc[
            1,
            "research_projection_opportunity_score",
        ]
        == 0
    )

    assert result["direction"].tolist() == [
        "OVER",
        "OVER",
    ]

    assert result["grade"].tolist() == [
        "B",
        "B+",
    ]

    assert result["model_score"].tolist() == [
        70.0,
        80.0,
    ]

    assert result["final_model_version"].tolist() == [
        "v22-control",
        "v22-control",
    ]

    assert (
        result["production_fields_unchanged"]
        .eq(1)
        .all()
    )


def test_enrich_file_writes_output(
    tmp_path: Path,
) -> None:
    scored_path = tmp_path / "scored.csv"
    projection_path = tmp_path / "projection.csv"
    output_path = tmp_path / "enriched.csv"

    scored_board().to_csv(
        scored_path,
        index=False,
    )

    projection_board().to_csv(
        projection_path,
        index=False,
    )

    result = enrich_file(
        scored_path,
        projection_path,
        output_path,
    )

    assert result["status"] == "COMPLETE"
    assert result["matched_rows"] == 2
    assert output_path.exists()

    output = pd.read_csv(output_path)

    assert (
        "research_blended_opportunity_score"
        in output.columns
    )

    assert (
        output["production_fields_unchanged"]
        .eq(1)
        .all()
    )
