"""One-command completed-slate WNBA research audit workflow."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from src.audits.audit_previous_slate import audit_slate
from src.audits.build_probability_history import build_probability_history
from src.audits.evaluate_probability_promotion import evaluate_promotion
from src.decisions.build_chronological_calibration import (
    chronological_calibration,
)
from src.workflows.research_decision_pipeline import (
    run_research_decision_pipeline,
)


ROOT = Path(__file__).resolve().parents[2]


def write_json_atomic(
    path: Path,
    payload: dict[str, object],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def parse_slate_date(value: str) -> date:
    try:
        parsed = datetime.strptime(
            value,
            "%Y-%m-%d",
        ).date()
    except ValueError as error:
        raise ValueError(
            "Date must use YYYY-MM-DD format"
        ) from error

    if parsed > date.today():
        raise ValueError(
            f"Future slate dates are not allowed: {value}"
        )

    return parsed


def resolve_scored_board(
    slate_date: str,
) -> Path:
    candidates = [
        ROOT
        / "data"
        / "live"
        / slate_date
        / "wnba_scored_board.csv",
        ROOT
        / "data"
        / "model_runs"
        / f"wnba_scored_board_{slate_date}.csv",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "No WNBA scored board found for "
        f"{slate_date}. Checked: "
        + ", ".join(str(path) for path in candidates)
    )


def validate_board_date(
    board_path: Path,
    slate_date: str,
) -> None:
    board = pd.read_csv(board_path)

    if "slate_date" not in board.columns:
        return

    available = {
        str(value)[:10]
        for value in board["slate_date"].dropna().unique()
    }

    if available and available != {slate_date}:
        raise ValueError(
            f"Scored board dates {sorted(available)} "
            f"do not match requested date {slate_date}"
        )


def run_completed_slate_audit(
    slate_date: str,
) -> dict[str, object]:
    live_directory = (
        ROOT / "data" / "live" / slate_date
    )
    model_runs = ROOT / "data" / "model_runs"
    audit_directory = ROOT / "data" / "audits"
    backtests = ROOT / "data" / "backtests"
    registry = ROOT / "data" / "model_registry"

    manifest_path = (
        audit_directory
        / f"wnba_audit_manifest_{slate_date}.json"
    )

    manifest: dict[str, object] = {
        "requested_date": slate_date,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "stage_statuses": {},
        "research_only": True,
        "production_unchanged": True,
        "automatic_promotion": False,
        "error_messages": [],
        "overall_status": "SUCCESS",
    }

    try:
        parse_slate_date(slate_date)
        scored_board = resolve_scored_board(slate_date)
        validate_board_date(scored_board, slate_date)

        results_path = (
            ROOT
            / "data"
            / "wnba"
            / f"WNBA_RESULTS_{slate_date}.csv"
        )

        if not results_path.exists():
            raise FileNotFoundError(
                f"Official results file not found: {results_path}"
            )

        live_directory.mkdir(parents=True, exist_ok=True)
        model_runs.mkdir(parents=True, exist_ok=True)
        audit_directory.mkdir(parents=True, exist_ok=True)
        backtests.mkdir(parents=True, exist_ok=True)
        registry.mkdir(parents=True, exist_ok=True)

        manifest["source_scored_board"] = str(scored_board)
        manifest["results_file"] = str(results_path)

        research = run_research_decision_pipeline(
            slate_date=slate_date,
            scored_board=scored_board,
            live_directory=live_directory,
            root=ROOT,
        )

        manifest["stage_statuses"]["research_pipeline"] = {
            "status": research.get("overall_status"),
            "manifest": str(
                live_directory
                / "wnba_research_pipeline_manifest.json"
            ),
        }

        if research.get("overall_status") not in {
            "SUCCESS",
            "PARTIAL",
        }:
            raise RuntimeError(
                "Historical research pipeline did not produce "
                "usable outputs"
            )

        live_probability = (
            live_directory
            / "wnba_probability_board.csv"
        )

        if not live_probability.exists():
            raise FileNotFoundError(
                f"Probability board not found: {live_probability}"
            )

        dated_probability = (
            model_runs
            / f"wnba_probability_board_{slate_date}.csv"
        )

        shutil.copy2(
            live_probability,
            dated_probability,
        )

        manifest["probability_board"] = str(
            dated_probability
        )

        audit_output = (
            audit_directory
            / f"wnba_full_audit_{slate_date}.csv"
        )

        audit_summary = audit_slate(
            board_path=scored_board,
            results_path=results_path,
            output_path=audit_output,
        )

        manifest["stage_statuses"]["audit"] = {
            "status": "SUCCESS",
            "output": str(audit_output),
            **audit_summary,
        }

        history_path = (
            backtests
            / "wnba_probability_history.csv"
        )

        history_rows, resolved_rows = (
            build_probability_history(
                probability_dir=model_runs,
                audit_dir=audit_directory,
                output=history_path,
            )
        )

        manifest["stage_statuses"]["probability_history"] = {
            "status": "SUCCESS",
            "output": str(history_path),
            "rows": history_rows,
            "resolved_rows": resolved_rows,
        }

        predictions_path = (
            backtests
            / "wnba_chronological_calibration_predictions.csv"
        )

        summary_path = (
            backtests
            / "wnba_chronological_calibration_summary.csv"
        )

        prediction_rows, evaluated_slates = (
            chronological_calibration(
                history_path=history_path,
                predictions_output=predictions_path,
                summary_output=summary_path,
            )
        )

        manifest["stage_statuses"]["calibration"] = {
            "status": "SUCCESS",
            "predictions_output": str(predictions_path),
            "summary_output": str(summary_path),
            "prediction_rows": prediction_rows,
            "evaluated_slates": evaluated_slates,
        }

        promotion_path = (
            registry
            / "wnba_probability_promotion_report.json"
        )

        promotion = evaluate_promotion(
            predictions_path=predictions_path,
            summary_path=summary_path,
            output_path=promotion_path,
        )

        if promotion.get("automatic_promotion") is not False:
            raise RuntimeError(
                "Automatic promotion safety assertion failed"
            )

        manifest["stage_statuses"]["promotion"] = {
            "status": "SUCCESS",
            "output": str(promotion_path),
            **promotion,
        }

        manifest["audit_output"] = str(audit_output)
        manifest["probability_history"] = str(history_path)
        manifest["calibration_predictions"] = str(
            predictions_path
        )
        manifest["calibration_summary"] = str(
            summary_path
        )
        manifest["promotion_report"] = str(
            promotion_path
        )

        manifest["resolved_rows"] = (
            audit_summary["hits"]
            + audit_summary["misses"]
        )
        manifest["graded_rows_including_pushes"] = (
            audit_summary["hits"]
            + audit_summary["misses"]
            + audit_summary["pushes"]
        )
        manifest["unresolved_rows"] = (
            audit_summary["unresolved"]
            + audit_summary["unsupported"]
        )
        manifest["hits"] = audit_summary["hits"]
        manifest["misses"] = audit_summary["misses"]
        manifest["pushes"] = audit_summary["pushes"]

    except Exception as error:
        manifest["overall_status"] = "FAILED"
        manifest["error_messages"].append(
            f"{type(error).__name__}: {error}"
        )

    manifest["completed_at"] = (
        datetime.now(timezone.utc).isoformat()
    )

    write_json_atomic(
        manifest_path,
        manifest,
    )

    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit one completed WNBA slate and refresh "
            "chronological probability evidence."
        )
    )
    parser.add_argument(
        "--date",
        required=True,
        dest="slate_date",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    manifest = run_completed_slate_audit(
        args.slate_date
    )

    print(
        json.dumps(
            manifest,
            indent=2,
            default=str,
        )
    )

    if manifest.get("overall_status") != "SUCCESS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
