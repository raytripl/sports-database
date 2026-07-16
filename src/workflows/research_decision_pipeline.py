"""Fail-closed research-only WNBA post-score pipeline."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from src.decisions.build_decision_engine import build_decision_engine
from src.decisions.build_player_comparison import build_player_comparison
from src.decisions.build_selection_paths import build_selection_paths
from src.decisions.build_correlation_engine import build_correlation_engine
from src.decisions.build_relationship_engine import build_relationship_engine
from src.decisions.build_diversified_candidates import build_diversified_candidates
from src.decisions.build_optimized_slips import build_optimized_slips
from src.decisions.build_probability_engine import build_probability_engine


PROTECTED_COLUMNS = (
    "final_selection",
    "pick_level",
    "eligibility_status",
    "candidate_action",
    "decision_flow",
    "final_model_version",
    "snapshot_id",
)

PIPELINE_VERSION = "WNBA_RESEARCH_DECISION_PIPELINE_V1"


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _git_commit(root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None

    if completed.returncode != 0:
        return None

    return completed.stdout.strip() or None


def _protected_snapshot(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)

    key_columns = [
        column
        for column in (
            "player",
            "team",
            "opponent",
            "prop_type",
            "line",
        )
        if column in frame.columns
    ]

    protected = [
        column
        for column in PROTECTED_COLUMNS
        if column in frame.columns
    ]

    if not protected:
        return pd.DataFrame()

    selected = frame[key_columns + protected].copy()

    sort_columns = key_columns + protected

    if sort_columns:
        selected = selected.sort_values(
            sort_columns,
            kind="stable",
            na_position="last",
        )

    return selected.reset_index(drop=True)


def _assert_production_unchanged(
    original_snapshot: pd.DataFrame,
    output_path: Path,
) -> None:
    if original_snapshot.empty:
        return

    output = pd.read_csv(output_path)

    columns = list(original_snapshot.columns)

    missing = [
        column
        for column in columns
        if column not in output.columns
    ]

    if missing:
        raise RuntimeError(
            "Research output dropped protected production columns: "
            + ", ".join(missing)
        )

    current = output[columns].copy()

    current = current.sort_values(
        columns,
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)

    pd.testing.assert_frame_equal(
        original_snapshot,
        current,
        check_dtype=False,
        check_like=False,
    )


def run_research_decision_pipeline(
    slate_date: str,
    scored_board: Path,
    live_directory: Path,
    root: Path,
) -> dict[str, object]:
    live_directory.mkdir(parents=True, exist_ok=True)

    outputs = {
        "decision_board": live_directory / "wnba_decision_engine_board.csv",
        "player_comparison_board": live_directory / "wnba_player_comparison_board.csv",
        "selection_path_board": live_directory / "wnba_selection_path_board.csv",
        "correlation_board": live_directory / "wnba_correlation_board.csv",
        "relationships": live_directory / "wnba_relationships.csv",
        "diversified_candidates": live_directory / "wnba_diversified_candidates.csv",
        "optimized_slips": live_directory / "wnba_optimized_research_slips.csv",
        "probability_board": live_directory / "wnba_probability_board.csv",
    }

    manifest_path = (
        live_directory
        / "wnba_research_pipeline_manifest.json"
    )

    manifest: dict[str, object] = {
        "slate_date": slate_date,
        "source_scored_board": str(scored_board),
        **{
            name: str(path)
            for name, path in outputs.items()
        },
        "stage_statuses": {},
        "research_only": True,
        "production_unchanged": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": PIPELINE_VERSION,
        "git_commit": _git_commit(root),
        "overall_status": "SUCCESS",
        "error_messages": [],
    }

    if not scored_board.exists():
        manifest["overall_status"] = "BLOCKED_NO_SCORED_BOARD"
        manifest["production_unchanged"] = True
        manifest["error_messages"] = [
            f"Scored board not found: {scored_board}"
        ]
        _write_json_atomic(manifest_path, manifest)
        return manifest

    protected_snapshot = _protected_snapshot(scored_board)

    stages: list[
        tuple[
            str,
            Path,
            Callable[[], object],
            str | None,
        ]
    ] = [
        (
            "decision_engine",
            outputs["decision_board"],
            lambda: build_decision_engine(
                scored_board,
                outputs["decision_board"],
            ),
            None,
        ),
        (
            "player_comparison",
            outputs["player_comparison_board"],
            lambda: build_player_comparison(
                outputs["decision_board"],
                outputs["player_comparison_board"],
            ),
            "decision_engine",
        ),
        (
            "selection_paths",
            outputs["selection_path_board"],
            lambda: build_selection_paths(
                outputs["player_comparison_board"],
                outputs["selection_path_board"],
            ),
            "player_comparison",
        ),
        (
            "correlation_engine",
            outputs["correlation_board"],
            lambda: build_correlation_engine(
                outputs["selection_path_board"],
                outputs["correlation_board"],
            ),
            "selection_paths",
        ),
        (
            "relationship_engine",
            outputs["relationships"],
            lambda: build_relationship_engine(
                outputs["selection_path_board"],
                outputs["relationships"],
            ),
            "selection_paths",
        ),
        (
            "diversification_engine",
            outputs["diversified_candidates"],
            lambda: build_diversified_candidates(
                outputs["selection_path_board"],
                outputs["relationships"],
                outputs["diversified_candidates"],
            ),
            "relationship_engine",
        ),
        (
            "optimized_slips",
            outputs["optimized_slips"],
            lambda: build_optimized_slips(
                outputs["diversified_candidates"],
                outputs["optimized_slips"],
            ),
            "diversification_engine",
        ),
        (
            "probability_engine",
            outputs["probability_board"],
            lambda: build_probability_engine(
                outputs["correlation_board"],
                outputs["probability_board"],
            ),
            "correlation_engine",
        ),
    ]

    failed_stages: set[str] = set()

    for stage_name, output_path, runner, dependency in stages:
        if dependency and dependency in failed_stages:
            manifest["stage_statuses"][stage_name] = {
                "status": "BLOCKED",
                "dependency": dependency,
                "output": str(output_path),
            }
            failed_stages.add(stage_name)
            continue

        try:
            result = runner()

            row_preserving_stages = {
                "decision_engine",
                "player_comparison",
                "selection_paths",
                "correlation_engine",
                "probability_engine",
            }

            if stage_name in row_preserving_stages:
                _assert_production_unchanged(
                    protected_snapshot,
                    output_path,
                )

            manifest["stage_statuses"][stage_name] = {
                "status": "SUCCESS",
                "output": str(output_path),
                "result": result,
            }
        except Exception as error:
            failed_stages.add(stage_name)
            manifest["stage_statuses"][stage_name] = {
                "status": "FAILED",
                "output": str(output_path),
                "error": f"{type(error).__name__}: {error}",
            }
            manifest["error_messages"].append(
                f"{stage_name}: {type(error).__name__}: {error}"
            )

    if failed_stages:
        successful = any(
            value.get("status") == "SUCCESS"
            for value in manifest["stage_statuses"].values()
        )
        manifest["overall_status"] = (
            "PARTIAL" if successful else "FAILED"
        )

    manifest["production_unchanged"] = True
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()

    _write_json_atomic(manifest_path, manifest)

    return manifest
