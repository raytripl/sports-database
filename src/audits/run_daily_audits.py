from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from src.audits.resolve_full_board import export_audit, resolve_snapshot
from src.db import connect
from src.decisions.schema import initialize_schema


def eligible_snapshots(through_date: str) -> pd.DataFrame:
    initialize_schema()
    with connect() as connection:
        return pd.read_sql_query(
            """
            SELECT snapshot_id, slate_date, UPPER(sport) AS sport,
                   COUNT(*) AS decision_rows, MAX(created_at) AS created_at
            FROM model_decisions
            WHERE snapshot_id IS NOT NULL
              AND slate_date <= ?
              AND UPPER(sport) IN ('WNBA', 'MLB')
            GROUP BY snapshot_id, slate_date, UPPER(sport)
            ORDER BY slate_date, sport, created_at
            """,
            connection,
            params=(through_date,),
        )


def run_daily_audits(
    through_date: str,
    wnba_results: Path,
    mlb_results: Path,
    output_dir: Path,
) -> dict[str, object]:
    snapshots = eligible_snapshots(through_date)
    output_dir.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, object]] = []
    for _, snapshot in snapshots.iterrows():
        sport = str(snapshot["sport"])
        results = wnba_results if sport == "WNBA" else mlb_results
        snapshot_id = str(snapshot["snapshot_id"])
        slate_date = str(snapshot["slate_date"])
        report = output_dir / slate_date / f"{sport.lower()}_{snapshot_id}.csv"
        try:
            counts = resolve_snapshot(snapshot_id, results)
            rows = export_audit(snapshot_id, report)
            state = "RESOLVED" if counts["PENDING"] == 0 else "PARTIAL"
            error = None
        except Exception as exc:
            counts, rows, state = {}, 0, "FAILED_SAFE"
            error = f"{type(exc).__name__}: {exc}"
        runs.append({
            "snapshot_id": snapshot_id,
            "slate_date": slate_date,
            "sport": sport,
            "decision_rows": int(snapshot["decision_rows"]),
            "state": state,
            "counts": counts,
            "report": str(report) if rows else None,
            "error": error,
        })
    manifest = {
        "pipeline": "SPORTS_HUB_FULL_BOARD_AUDIT",
        "model_version": "v17.3",
        "operating_revision": "Evidence-Enforced Revision B",
        "generated_at": datetime.now().astimezone().isoformat(),
        "through_date": through_date,
        "snapshots_found": len(snapshots),
        "runs": runs,
        "model_weights_changed": False,
        "recommendations_enabled": False,
    }
    manifest_path = output_dir / "latest_audit_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit every saved full-game WNBA/MLB snapshot")
    parser.add_argument(
        "--through-date",
        default=(date.today() - timedelta(days=1)).isoformat(),
        help="Latest completed slate to audit (defaults to yesterday).",
    )
    parser.add_argument("--wnba-results", type=Path, default=Path("data/wnba/WNBA_RESULTS_HISTORY.csv"))
    parser.add_argument("--mlb-results", type=Path, default=Path("data/mlb/MLB_RESULTS_HISTORY.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/audits"))
    args = parser.parse_args()
    manifest = run_daily_audits(args.through_date, args.wnba_results, args.mlb_results, args.output_dir)
    print("=" * 70)
    print("SPORTS HUB FULL-BOARD AUDIT")
    print("=" * 70)
    print(f"Snapshots found: {manifest['snapshots_found']:,}")
    for run in manifest["runs"]:
        print(f"{run['slate_date']} {run['sport']} {run['snapshot_id']} {run['state']}")
    print(f"Manifest: {manifest['manifest_path']}")
    print("Model weights unchanged; recommendations remain disabled.")


if __name__ == "__main__":
    main()
