from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd


BUCKET_EDGES = [
    0.00,
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

BUCKET_LABELS = [
    "00-55",
    "55-60",
    "60-65",
    "65-70",
    "70-75",
    "75-80",
    "80-85",
    "85-90",
    "90-95",
    "95-100",
]

MIN_BUCKET_ROWS = 10
PRIOR_STRENGTH = 10.0
EPSILON = 1e-6


def assign_bucket(
    probabilities: pd.Series,
) -> pd.Series:
    return pd.cut(
        probabilities,
        bins=BUCKET_EDGES,
        labels=BUCKET_LABELS,
        include_lowest=True,
        right=False,
    ).astype("object")


def clipped_probability(
    values: pd.Series,
) -> pd.Series:
    return pd.to_numeric(
        values,
        errors="coerce",
    ).clip(EPSILON, 1.0 - EPSILON)


def brier_score(
    probability: pd.Series,
    actual: pd.Series,
) -> float:
    return float(
        ((probability - actual) ** 2).mean()
    )


def log_loss(
    probability: pd.Series,
    actual: pd.Series,
) -> float:
    probability = clipped_probability(probability)

    loss = -(
        actual * probability.map(math.log)
        + (1 - actual)
        * (1 - probability).map(math.log)
    )

    return float(loss.mean())


def build_bucket_calibration(
    training: pd.DataFrame,
) -> pd.DataFrame:
    if training.empty:
        return pd.DataFrame(
            columns=[
                "calibration_bucket",
                "training_rows",
                "training_hits",
                "training_hit_rate",
                "shrunk_hit_rate",
            ]
        )

    training = training.copy()

    training["calibration_bucket"] = assign_bucket(
        training["raw_probability"]
    )

    overall_rate = float(
        training["actual_hit"].mean()
    )

    grouped = (
        training.groupby(
            "calibration_bucket",
            observed=False,
        )
        .agg(
            training_rows=("actual_hit", "size"),
            training_hits=("actual_hit", "sum"),
            training_hit_rate=("actual_hit", "mean"),
        )
        .reset_index()
    )

    grouped["shrunk_hit_rate"] = (
        grouped["training_hits"]
        + PRIOR_STRENGTH * overall_rate
    ) / (
        grouped["training_rows"]
        + PRIOR_STRENGTH
    )

    return grouped


def chronological_calibration(
    history_path: Path,
    predictions_output: Path,
    summary_output: Path,
) -> tuple[int, int]:
    if not history_path.exists():
        raise FileNotFoundError(
            f"Probability history not found: {history_path}"
        )

    history = pd.read_csv(history_path).copy()

    history["slate_date"] = pd.to_datetime(
        history["slate_date"],
        errors="coerce",
    )

    history["raw_probability"] = pd.to_numeric(
        history["raw_probability"],
        errors="coerce",
    )

    history["actual_hit"] = pd.to_numeric(
        history["actual_hit"],
        errors="coerce",
    )

    resolved = history[
        history["slate_date"].notna()
        & history["raw_probability"].notna()
        & history["actual_hit"].isin([0, 1])
    ].copy()

    resolved = resolved.sort_values(
        [
            "slate_date",
            "raw_probability",
        ]
    )

    dates = sorted(
        resolved["slate_date"].dropna().unique()
    )

    prediction_frames: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []

    for test_date in dates:
        training = resolved[
            resolved["slate_date"] < test_date
        ].copy()

        test = resolved[
            resolved["slate_date"] == test_date
        ].copy()

        if test.empty:
            continue

        test["calibration_bucket"] = assign_bucket(
            test["raw_probability"]
        )

        training_slates = int(
            training["slate_date"].nunique()
        )

        training_rows = len(training)

        if training.empty:
            test["bucket_training_rows"] = 0
            test["bucket_training_hit_rate"] = pd.NA
            test["calibrated_probability"] = 0.50
            test["calibration_status"] = (
                "NO_PRIOR_TRAINING_DATA"
            )
        else:
            calibration = build_bucket_calibration(
                training
            )

            calibration = calibration.rename(
                columns={
                    "training_rows": (
                        "bucket_training_rows"
                    ),
                    "training_hit_rate": (
                        "bucket_training_hit_rate"
                    ),
                }
            )

            test = test.merge(
                calibration[
                    [
                        "calibration_bucket",
                        "bucket_training_rows",
                        "bucket_training_hit_rate",
                        "shrunk_hit_rate",
                    ]
                ],
                on="calibration_bucket",
                how="left",
            )

            overall_training_rate = float(
                training["actual_hit"].mean()
            )

            test["calibrated_probability"] = (
                test["shrunk_hit_rate"]
            )

            missing_bucket = (
                test["bucket_training_rows"]
                .fillna(0)
                .lt(MIN_BUCKET_ROWS)
            )

            test.loc[
                missing_bucket,
                "calibrated_probability",
            ] = overall_training_rate

            test["calibration_status"] = (
                "CHRONOLOGICAL_BUCKET"
            )

            test.loc[
                missing_bucket,
                "calibration_status",
            ] = "PRIOR_OVERALL_FALLBACK"

        test["calibrated_probability"] = (
            clipped_probability(
                test["calibrated_probability"]
            )
        )

        test["training_rows_before_slate"] = (
            training_rows
        )

        test["training_slates_before_slate"] = (
            training_slates
        )

        raw_brier = brier_score(
            test["raw_probability"],
            test["actual_hit"],
        )

        calibrated_brier = brier_score(
            test["calibrated_probability"],
            test["actual_hit"],
        )

        raw_log_loss = log_loss(
            test["raw_probability"],
            test["actual_hit"],
        )

        calibrated_log_loss = log_loss(
            test["calibrated_probability"],
            test["actual_hit"],
        )

        summary_rows.append(
            {
                "test_slate_date": (
                    pd.Timestamp(test_date)
                    .strftime("%Y-%m-%d")
                ),
                "training_rows": training_rows,
                "training_slates": training_slates,
                "test_rows": len(test),
                "test_hits": int(
                    test["actual_hit"].sum()
                ),
                "test_hit_rate": float(
                    test["actual_hit"].mean()
                ),
                "raw_brier": raw_brier,
                "calibrated_brier": calibrated_brier,
                "brier_improvement": (
                    raw_brier - calibrated_brier
                ),
                "raw_log_loss": raw_log_loss,
                "calibrated_log_loss": (
                    calibrated_log_loss
                ),
                "log_loss_improvement": (
                    raw_log_loss
                    - calibrated_log_loss
                ),
            }
        )

        prediction_frames.append(test)

    if prediction_frames:
        predictions = pd.concat(
            prediction_frames,
            ignore_index=True,
        )
    else:
        predictions = pd.DataFrame()

    summary = pd.DataFrame(summary_rows)

    if not predictions.empty:
        predictions["slate_date"] = (
            pd.to_datetime(
                predictions["slate_date"]
            )
            .dt.strftime("%Y-%m-%d")
        )

    predictions_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    predictions.to_csv(
        predictions_output,
        index=False,
    )

    summary.to_csv(
        summary_output,
        index=False,
    )

    return len(predictions), len(summary)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run leakage-safe chronological "
            "probability calibration."
        )
    )

    parser.add_argument(
        "--history",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--predictions-output",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--summary-output",
        required=True,
        type=Path,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    predictions, slates = chronological_calibration(
        history_path=args.history,
        predictions_output=(
            args.predictions_output
        ),
        summary_output=args.summary_output,
    )

    print("=" * 72)
    print("SPORTS HUB CHRONOLOGICAL CALIBRATION")
    print("=" * 72)
    print(f"Prediction rows: {predictions:,}")
    print(f"Evaluated slates: {slates:,}")
    print(
        f"Saved predictions: "
        f"{args.predictions_output}"
    )
    print(
        f"Saved summary: "
        f"{args.summary_output}"
    )
    print("Mode: RESEARCH ONLY")
    print("Future slate data was not used for training.")
    print("v22-control fields were not modified.")


if __name__ == "__main__":
    main()
