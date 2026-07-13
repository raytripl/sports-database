from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.decisions.create_decision_board import create_board
from src.decisions.enrich_wnba_availability import enrich_snapshot
from src.decisions.import_decision_board import import_board
from src.decisions.save_snapshot import save_snapshot
from src.decisions.score_decision_board import score_board
from src.imports.capture_matchup_foundation import capture


def run_pipeline(
    pool_path: Path,
    slate_date: str,
    history_path: Path,
    output_dir: Path,
    snapshot_id: str | None = None,
    availability_path: Path | None = None,
) -> dict[str, object]:
    if not pool_path.exists():
        raise FileNotFoundError(f"Pool not found: {pool_path}")
    if not history_path.exists():
        raise FileNotFoundError(f"History not found: {history_path}")
    if availability_path is not None and not availability_path.exists():
        raise FileNotFoundError(f"Availability not found: {availability_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    board_path = output_dir / f"wnba_decision_board_{slate_date}.csv"
    scored_path = output_dir / f"wnba_scored_board_{slate_date}.csv"
    manifest_path = output_dir / f"wnba_pipeline_manifest_{slate_date}.json"

    resolved_snapshot, inserted = save_snapshot(
        pool_path=pool_path,
        slate_date=slate_date,
        sport="WNBA",
        snapshot_id=snapshot_id,
    )
    capture_counts = capture(resolved_snapshot, pool_path, "WNBA")
    board_rows = create_board(resolved_snapshot, board_path)
    scored_rows = score_board(board_path, history_path, scored_path)
    updated, skipped = import_board(scored_path)

    availability_counts = None
    if availability_path is not None:
        availability_counts = enrich_snapshot(
            resolved_snapshot,
            availability_path,
        )

    manifest: dict[str, object] = {
        "pipeline": "WNBA_DAILY_BASELINE",
        "model_version": "v17.3",
        "operating_revision": "Evidence-Enforced Revision B",
        "slate_date": slate_date,
        "snapshot_id": resolved_snapshot,
        "snapshot_rows_inserted": inserted,
        "capture": capture_counts,
        "decision_board_rows": board_rows,
        "scored_rows": scored_rows,
        "database_rows_updated": updated,
        "database_rows_skipped": skipped,
        "availability": availability_counts,
        "board_path": str(board_path),
        "scored_path": str(scored_path),
        "baseline_grade_cap": "B+",
        "recommendations_enabled": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the guarded Sports Hub WNBA daily baseline pipeline."
    )
    parser.add_argument("--pool", required=True, type=Path)
    parser.add_argument("--date", required=True)
    parser.add_argument("--history", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data/model_runs"))
    parser.add_argument("--snapshot-id")
    parser.add_argument("--availability", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_pipeline(
        pool_path=args.pool,
        slate_date=args.date,
        history_path=args.history,
        output_dir=args.output_dir,
        snapshot_id=args.snapshot_id,
        availability_path=args.availability,
    )
    print("=" * 70)
    print("SPORTS HUB — WNBA DAILY BASELINE")
    print("=" * 70)
    print(f"Slate: {result['slate_date']}")
    print(f"Snapshot: {result['snapshot_id']}")
    print(f"Decision board rows: {result['decision_board_rows']:,}")
    print(f"Database rows updated: {result['database_rows_updated']:,}")
    print(f"Manifest: {result['manifest_path']}")
    print("Baseline cap: B+; recommendations remain disabled.")


if __name__ == "__main__":
    main()
