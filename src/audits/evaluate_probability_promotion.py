from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


REQUIRED_ROWS = 75
REQUIRED_SLATES = 10
REQUIRED_BRIER_IMPROVEMENT = 0.0
REQUIRED_LOG_LOSS_IMPROVEMENT = 0.0


def evaluate_promotion(
    predictions_path: Path,
    summary_path: Path,
    output_path: Path,
) -> dict[str, object]:
    if not predictions_path.exists():
        raise FileNotFoundError(
            f"Predictions not found: {predictions_path}"
        )

    if not summary_path.exists():
        raise FileNotFoundError(
            f"Summary not found: {summary_path}"
        )

    predictions = pd.read_csv(
        predictions_path
    )

    summary = pd.read_csv(
        summary_path
    )

    chronological = predictions[
        predictions["training_rows_before_slate"]
        .fillna(0)
        .gt(0)
    ].copy()

    evaluated_rows = len(chronological)

    evaluated_slates = (
        int(chronological["slate_date"].nunique())
        if not chronological.empty
        else 0
    )

    eligible_summary = summary[
        summary["training_rows"].fillna(0).gt(0)
    ].copy()

    if eligible_summary.empty:
        total_brier_improvement = 0.0
        total_log_loss_improvement = 0.0
    else:
        weights = eligible_summary[
            "test_rows"
        ].clip(lower=1)

        total_brier_improvement = float(
            (
                eligible_summary[
                    "brier_improvement"
                ]
                * weights
            ).sum()
            / weights.sum()
        )

        total_log_loss_improvement = float(
            (
                eligible_summary[
                    "log_loss_improvement"
                ]
                * weights
            ).sum()
            / weights.sum()
        )

    rows_gate = evaluated_rows >= REQUIRED_ROWS
    slates_gate = (
        evaluated_slates >= REQUIRED_SLATES
    )

    brier_gate = (
        total_brier_improvement
        > REQUIRED_BRIER_IMPROVEMENT
    )

    log_loss_gate = (
        total_log_loss_improvement
        > REQUIRED_LOG_LOSS_IMPROVEMENT
    )

    production_enabled = all(
        [
            rows_gate,
            slates_gate,
            brier_gate,
            log_loss_gate,
        ]
    )

    report = {
        "evaluated_rows": evaluated_rows,
        "required_rows": REQUIRED_ROWS,
        "rows_gate_passed": rows_gate,
        "evaluated_slates": evaluated_slates,
        "required_slates": REQUIRED_SLATES,
        "slates_gate_passed": slates_gate,
        "weighted_brier_improvement": round(
            total_brier_improvement,
            6,
        ),
        "brier_gate_passed": brier_gate,
        "weighted_log_loss_improvement": round(
            total_log_loss_improvement,
            6,
        ),
        "log_loss_gate_passed": log_loss_gate,
        "production_enabled": production_enabled,
        "status": (
            "ELIGIBLE_FOR_MANUAL_REVIEW"
            if production_enabled
            else "INSUFFICIENT_EVIDENCE"
        ),
        "automatic_promotion": False,
        "model_mode": "RESEARCH_ONLY",
    }

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate whether chronological "
            "probability calibration has enough "
            "evidence for manual review."
        )
    )

    parser.add_argument(
        "--predictions",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--summary",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    report = evaluate_promotion(
        predictions_path=args.predictions,
        summary_path=args.summary,
        output_path=args.output,
    )

    print("=" * 72)
    print("SPORTS HUB PROBABILITY PROMOTION REPORT")
    print("=" * 72)

    for key, value in report.items():
        print(f"{key}: {value}")

    print(f"Saved: {args.output}")
    print("Automatic promotion: DISABLED")
    print("v22-control was not modified.")


if __name__ == "__main__":
    main()
