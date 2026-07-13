from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.decisions.create_decision_board import create_board
from src.decisions.enrich_mlb_live_context import enrich_snapshot
from src.decisions.import_decision_board import import_board
from src.decisions.save_snapshot import save_snapshot
from src.decisions.score_mlb_decision_board import score_board
from src.imports.capture_matchup_foundation import capture


def run_pipeline(
    pool_path: Path,
    slate_date: str,
    history_path: Path,
    output_dir: Path,
    snapshot_id: str | None = None,
    live_context_path: Path | None = None,
    live_context_error: str | None = None,
) -> dict[str, object]:
    if not pool_path.exists():
        raise FileNotFoundError(f"Pool not found: {pool_path}")
    if not history_path.exists():
        raise FileNotFoundError(f"History not found: {history_path}")
    if live_context_path is not None and not live_context_path.exists():
        raise FileNotFoundError(f"Live context not found: {live_context_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    board_path = output_dir / f"mlb_decision_board_{slate_date}.csv"
    scored_path = output_dir / f"mlb_scored_board_{slate_date}.csv"
    manifest_path = output_dir / f"mlb_pipeline_manifest_{slate_date}.json"

    resolved, inserted = save_snapshot(pool_path, slate_date, "MLB", snapshot_id)
    capture_counts = capture(resolved, pool_path, "MLB")
    board_rows = create_board(resolved, board_path)
    scored_rows = score_board(board_path, history_path, scored_path)
    updated, skipped = import_board(scored_path)
    live_counts = None
    if live_context_path is not None:
        live_counts = enrich_snapshot(resolved, live_context_path)

    manifest: dict[str, object] = {
        "pipeline": "MLB_DAILY_BASELINE",
        "model_version": "v17.3",
        "operating_revision": "Evidence-Enforced Revision B",
        "slate_date": slate_date,
        "snapshot_id": resolved,
        "snapshot_rows_inserted": inserted,
        "capture": capture_counts,
        "decision_board_rows": board_rows,
        "scored_rows": scored_rows,
        "database_rows_updated": updated,
        "database_rows_skipped": skipped,
        "live_context": live_counts,
        "live_context_path": str(live_context_path) if live_context_path else None,
        "live_context_error": live_context_error,
        "board_path": str(board_path),
        "scored_path": str(scored_path),
        "baseline_grade_cap": "B+",
        "recommendations_enabled": False,
        "power_play_eligible": False,
        "live_gates_required": [
            "confirmed_lineup", "batting_order", "starting_pitcher",
            "opponent_k_percent_vs_hand", "expected_pitch_count",
            "expected_innings", "platoon_risk", "weather",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run guarded MLB daily baseline")
    parser.add_argument("--pool", required=True, type=Path)
    parser.add_argument("--date", required=True)
    parser.add_argument("--history", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data/model_runs"))
    parser.add_argument("--snapshot-id")
    parser.add_argument("--live-context", type=Path)
    args = parser.parse_args()
    result = run_pipeline(
        args.pool, args.date, args.history, args.output_dir,
        args.snapshot_id, args.live_context,
    )
    print("=" * 70)
    print("SPORTS HUB - MLB DAILY BASELINE")
    print("=" * 70)
    print(f"Slate: {result['slate_date']}")
    print(f"Snapshot: {result['snapshot_id']}")
    print(f"Decision board rows: {result['decision_board_rows']:,}")
    print(f"Live context: {result['live_context']}")
    print(f"Manifest: {result['manifest_path']}")
    print("Baseline cap: B+; recommendations remain disabled.")


if __name__ == "__main__":
    main()
