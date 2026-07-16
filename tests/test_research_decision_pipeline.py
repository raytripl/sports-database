from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from src.workflows.audit_completed_slate import parse_slate_date
from src.workflows.research_decision_pipeline import (
    run_research_decision_pipeline,
)


def sample_scored_board() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player": "Player One",
                "team": "AAA",
                "opponent": "BBB",
                "prop_type": "Points",
                "line": 15.5,
                "over_score": 72.0,
                "under_score": 40.0,
                "model_score": 72.0,
                "opportunity_score": 80.0,
                "matchup_score": 65.0,
                "line_value_score": 60.0,
                "evidence_agreement_score": 70.0,
                "ceiling_risk_score": 20.0,
                "sample_size": 20,
                "final_selection": "",
                "pick_level": "",
                "eligibility_status": "ELIGIBLE",
                "candidate_action": "REVIEW",
                "decision_flow": "RESEARCH",
                "final_model_version": "v22-control",
                "snapshot_id": "snapshot-1",
                "shadow_parlay_eligible": 0,
                "injury_status": "ACTIVE",
            },
            {
                "player": "Player Two",
                "team": "CCC",
                "opponent": "DDD",
                "prop_type": "Rebounds",
                "line": 7.5,
                "over_score": 38.0,
                "under_score": 70.0,
                "model_score": 70.0,
                "opportunity_score": 75.0,
                "matchup_score": 35.0,
                "line_value_score": 62.0,
                "evidence_agreement_score": 68.0,
                "ceiling_risk_score": 25.0,
                "sample_size": 18,
                "final_selection": "",
                "pick_level": "",
                "eligibility_status": "ELIGIBLE",
                "candidate_action": "REVIEW",
                "decision_flow": "RESEARCH",
                "final_model_version": "v22-control",
                "snapshot_id": "snapshot-2",
                "shadow_parlay_eligible": 0,
                "injury_status": "ACTIVE",
            },
        ]
    )


def test_research_pipeline_creates_manifest_and_outputs(
    tmp_path: Path,
) -> None:
    scored = tmp_path / "wnba_scored_board.csv"
    live = tmp_path / "live"

    original = sample_scored_board()
    original.to_csv(scored, index=False)
    original_from_disk = pd.read_csv(scored)

    manifest = run_research_decision_pipeline(
        slate_date="2026-07-15",
        scored_board=scored,
        live_directory=live,
        root=tmp_path,
    )

    assert manifest["overall_status"] == "SUCCESS"
    assert manifest["research_only"] is True
    assert manifest["production_unchanged"] is True
    assert manifest["error_messages"] == []

    expected = [
        "wnba_decision_engine_board.csv",
        "wnba_player_comparison_board.csv",
        "wnba_selection_path_board.csv",
        "wnba_correlation_board.csv",
        "wnba_relationships.csv",
        "wnba_diversified_candidates.csv",
        "wnba_optimized_research_slips.csv",
        "wnba_probability_board.csv",
        "wnba_research_pipeline_manifest.json",
    ]

    for filename in expected:
        assert (live / filename).exists(), filename

    decision = pd.read_csv(
        live / "wnba_decision_engine_board.csv"
    )

    directions = dict(
        zip(decision["player"], decision["model_direction"])
    )

    assert directions["Player One"] == "OVER"
    assert directions["Player Two"] == "UNDER"

    gaps = dict(
        zip(decision["player"], decision["direction_gap"])
    )

    assert gaps["Player One"] == pytest.approx(32.0)
    assert gaps["Player Two"] == pytest.approx(32.0)

    probability = pd.read_csv(
        live / "wnba_probability_board.csv"
    )

    assert probability["over_probability"].between(0, 1).all()
    assert probability["under_probability"].between(0, 1).all()
    assert probability["selected_probability"].between(0, 1).all()

    sums = (
        probability["over_probability"]
        + probability["under_probability"]
    )

    assert all(abs(value - 1.0) <= 0.0001 for value in sums)

    original_after = pd.read_csv(scored)

    pd.testing.assert_frame_equal(
        original_from_disk,
        original_after,
        check_dtype=False,
    )


def test_missing_scored_board_writes_blocked_manifest(
    tmp_path: Path,
) -> None:
    live = tmp_path / "live"

    manifest = run_research_decision_pipeline(
        slate_date="2026-07-15",
        scored_board=tmp_path / "missing.csv",
        live_directory=live,
        root=tmp_path,
    )

    assert (
        manifest["overall_status"]
        == "BLOCKED_NO_SCORED_BOARD"
    )
    assert manifest["research_only"] is True
    assert manifest["production_unchanged"] is True

    manifest_path = (
        live / "wnba_research_pipeline_manifest.json"
    )

    assert manifest_path.exists()

    saved = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    assert (
        saved["overall_status"]
        == "BLOCKED_NO_SCORED_BOARD"
    )


def test_future_audit_date_is_rejected() -> None:
    future = date.today() + timedelta(days=1)

    with pytest.raises(
        ValueError,
        match="Future slate dates are not allowed",
    ):
        parse_slate_date(future.isoformat())


def test_valid_completed_date_is_accepted() -> None:
    completed = date.today() - timedelta(days=1)

    assert parse_slate_date(
        completed.isoformat()
    ) == completed


def test_weak_direction_becomes_no_direction(
    tmp_path: Path,
) -> None:
    scored = tmp_path / "weak_scored_board.csv"
    live = tmp_path / "weak_live"

    weak = sample_scored_board().iloc[[0]].copy()

    weak["over_score"] = 53.0
    weak["under_score"] = 49.0
    weak["model_score"] = 53.0
    weak["final_selection"] = ""
    weak["pick_level"] = ""

    weak.to_csv(scored, index=False)

    manifest = run_research_decision_pipeline(
        slate_date="2026-07-15",
        scored_board=scored,
        live_directory=live,
        root=tmp_path,
    )

    assert manifest["overall_status"] == "SUCCESS"

    decision = pd.read_csv(
        live / "wnba_decision_engine_board.csv"
    )

    assert decision.loc[0, "model_direction"] == "NO_DIRECTION"
    assert decision.loc[0, "direction_gate_passed"] == 0
    assert (
        decision.loc[0, "direction_gate_reason"]
        == "GAP_AND_STRENGTH_TOO_LOW"
    )

    paths = pd.read_csv(
        live / "wnba_selection_path_board.csv"
    )

    assert paths.loc[0, "selection_path"] == "NO_BET"
    assert paths.loc[0, "path_direction"] == "NO_DIRECTION"

    probability = pd.read_csv(
        live / "wnba_probability_board.csv"
    )

    assert probability.loc[0, "selected_probability"] == pytest.approx(
        0.50
    )
    assert (
        probability.loc[0, "probability_status"]
        == "NO_DIRECTION_NEUTRAL_FALLBACK"
    )


def test_large_gap_but_low_strength_is_no_direction(
    tmp_path: Path,
) -> None:
    scored = tmp_path / "low_strength_board.csv"
    live = tmp_path / "low_strength_live"

    weak = sample_scored_board().iloc[[0]].copy()

    weak["over_score"] = 54.0
    weak["under_score"] = 30.0
    weak["model_score"] = 54.0
    weak["final_selection"] = ""
    weak["pick_level"] = ""

    weak.to_csv(scored, index=False)

    manifest = run_research_decision_pipeline(
        slate_date="2026-07-15",
        scored_board=scored,
        live_directory=live,
        root=tmp_path,
    )

    assert manifest["overall_status"] == "SUCCESS"

    decision = pd.read_csv(
        live / "wnba_decision_engine_board.csv"
    )

    assert decision.loc[0, "model_direction"] == "NO_DIRECTION"
    assert (
        decision.loc[0, "direction_gate_reason"]
        == "DECISION_STRENGTH_TOO_LOW"
    )


def test_rebs_plus_asts_over_is_hard_blocked(
    tmp_path: Path,
) -> None:
    scored = tmp_path / "rebs_asts_over.csv"
    live = tmp_path / "rebs_asts_over_live"

    row = sample_scored_board().iloc[[0]].copy()

    row["prop_type"] = "Rebs+Asts"
    row["over_score"] = 75.0
    row["under_score"] = 40.0
    row["model_score"] = 75.0
    row["opportunity_score"] = 85.0
    row["matchup_score"] = 70.0
    row["final_selection"] = ""
    row["pick_level"] = ""

    row.to_csv(scored, index=False)

    manifest = run_research_decision_pipeline(
        slate_date="2026-07-15",
        scored_board=scored,
        live_directory=live,
        root=tmp_path,
    )

    assert manifest["overall_status"] == "SUCCESS"

    paths = pd.read_csv(
        live / "wnba_selection_path_board.csv"
    )

    assert paths.loc[0, "path_direction"] == "OVER"
    assert paths.loc[0, "selection_path"] == "NO_BET"
    assert (
        paths.loc[0, "research_degrader_status"]
        == "HARD_BLOCK"
    )
    assert (
        paths.loc[0, "research_degrader_reason"]
        == "HISTORICAL_DEGRADER_REBS_PLUS_ASTS_OVER"
    )
    assert paths.loc[0, "research_eligible_path"] == 0
    assert paths.loc[0, "watchlist_eligible_path"] == 0


def test_points_under_cannot_be_research_qualified(
    tmp_path: Path,
) -> None:
    scored = tmp_path / "points_under.csv"
    live = tmp_path / "points_under_live"

    row = sample_scored_board().iloc[[0]].copy()

    row["prop_type"] = "Points"
    row["over_score"] = 35.0
    row["under_score"] = 78.0
    row["model_score"] = 78.0
    row["opportunity_score"] = 85.0
    row["matchup_score"] = 25.0
    row["line_value_score"] = 80.0
    row["evidence_agreement_score"] = 80.0
    row["ceiling_risk_score"] = 10.0
    row["final_selection"] = ""
    row["pick_level"] = ""

    row.to_csv(scored, index=False)

    manifest = run_research_decision_pipeline(
        slate_date="2026-07-15",
        scored_board=scored,
        live_directory=live,
        root=tmp_path,
    )

    assert manifest["overall_status"] == "SUCCESS"

    paths = pd.read_csv(
        live / "wnba_selection_path_board.csv"
    )

    assert paths.loc[0, "path_direction"] == "UNDER"
    assert (
        paths.loc[0, "selection_path"]
        != "RESEARCH_QUALIFIED"
    )
    assert (
        paths.loc[0, "research_degrader_status"]
        == "WATCHLIST_ONLY"
    )
    assert (
        paths.loc[0, "research_degrader_reason"]
        == "HISTORICAL_DEGRADER_POINTS_UNDER"
    )


def test_rebs_plus_asts_over_is_hard_blocked(
    tmp_path: Path,
) -> None:
    scored = tmp_path / "rebs_asts_over.csv"
    live = tmp_path / "rebs_asts_over_live"

    row = sample_scored_board().iloc[[0]].copy()

    row["prop_type"] = "Rebs+Asts"
    row["over_score"] = 75.0
    row["under_score"] = 40.0
    row["model_score"] = 75.0
    row["opportunity_score"] = 85.0
    row["matchup_score"] = 70.0
    row["final_selection"] = ""
    row["pick_level"] = ""

    row.to_csv(scored, index=False)

    manifest = run_research_decision_pipeline(
        slate_date="2026-07-15",
        scored_board=scored,
        live_directory=live,
        root=tmp_path,
    )

    assert manifest["overall_status"] == "SUCCESS"

    paths = pd.read_csv(
        live / "wnba_selection_path_board.csv"
    )

    assert paths.loc[0, "path_direction"] == "OVER"
    assert paths.loc[0, "selection_path"] == "NO_BET"
    assert (
        paths.loc[0, "research_degrader_status"]
        == "HARD_BLOCK"
    )
    assert (
        paths.loc[0, "research_degrader_reason"]
        == "HISTORICAL_DEGRADER_REBS_PLUS_ASTS_OVER"
    )
    assert paths.loc[0, "research_eligible_path"] == 0
    assert paths.loc[0, "watchlist_eligible_path"] == 0


def test_points_under_cannot_be_research_qualified(
    tmp_path: Path,
) -> None:
    scored = tmp_path / "points_under.csv"
    live = tmp_path / "points_under_live"

    row = sample_scored_board().iloc[[0]].copy()

    row["prop_type"] = "Points"
    row["over_score"] = 35.0
    row["under_score"] = 78.0
    row["model_score"] = 78.0
    row["opportunity_score"] = 85.0
    row["matchup_score"] = 25.0
    row["line_value_score"] = 80.0
    row["evidence_agreement_score"] = 80.0
    row["ceiling_risk_score"] = 10.0
    row["final_selection"] = ""
    row["pick_level"] = ""

    row.to_csv(scored, index=False)

    manifest = run_research_decision_pipeline(
        slate_date="2026-07-15",
        scored_board=scored,
        live_directory=live,
        root=tmp_path,
    )

    assert manifest["overall_status"] == "SUCCESS"

    paths = pd.read_csv(
        live / "wnba_selection_path_board.csv"
    )

    assert paths.loc[0, "path_direction"] == "UNDER"
    assert (
        paths.loc[0, "selection_path"]
        != "RESEARCH_QUALIFIED"
    )
    assert (
        paths.loc[0, "research_degrader_status"]
        == "WATCHLIST_ONLY"
    )
    assert (
        paths.loc[0, "research_degrader_reason"]
        == "HISTORICAL_DEGRADER_POINTS_UNDER"
    )
