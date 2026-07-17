from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


REPORT_FILES = (
    "ranking_report.csv",
    "score_bucket_report.csv",
    "opportunity_bucket_report.csv",
    "direction_gap_report.csv",
    "projection_error_report.csv",
    "component_lift_report.csv",
    "confidence_calibration_report.csv",
    "failure_summary.csv",
)


def discover_dates(
    replay_root: Path,
) -> list[str]:
    dates: list[str] = []

    for path in sorted(
        replay_root.iterdir()
    ):
        if not path.is_dir():
            continue

        calibration = path / "calibration"

        if calibration.exists():
            dates.append(path.name)

    return dates


def aggregate_report(
    replay_root: Path,
    dates: list[str],
    filename: str,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for slate_date in dates:
        path = (
            replay_root
            / slate_date
            / "calibration"
            / filename
        )

        if not path.exists():
            continue

        try:
            frame = pd.read_csv(
                path,
                low_memory=False,
            )
        except pd.errors.EmptyDataError:
            print(
                "Skipping empty report:",
                path,
            )
            continue

        if frame.empty:
            print(
                "Skipping report with no rows:",
                path,
            )
            continue

        frame.insert(
            0,
            "slate_date",
            slate_date,
        )

        frames.append(frame)

    if not frames:
        return pd.DataFrame()

    return pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    )


def ranking_stability_report(
    combined: pd.DataFrame,
) -> pd.DataFrame:
    required = {
        "cutoff",
        "wins",
        "losses",
        "decisions",
    }

    if (
        combined.empty
        or not required.issubset(
            combined.columns
        )
    ):
        return pd.DataFrame()

    grouped = (
        combined.groupby(
            "cutoff",
            dropna=False,
        )
        .agg(
            slates=("slate_date", "nunique"),
            total_wins=("wins", "sum"),
            total_losses=("losses", "sum"),
            total_decisions=("decisions", "sum"),
            average_slate_hit_rate=(
                "hit_rate",
                "mean",
            ),
            minimum_slate_hit_rate=(
                "hit_rate",
                "min",
            ),
            maximum_slate_hit_rate=(
                "hit_rate",
                "max",
            ),
            hit_rate_standard_deviation=(
                "hit_rate",
                "std",
            ),
            average_wilson_lower=(
                "wilson_lower",
                "mean",
            ),
        )
        .reset_index()
    )

    grouped["pooled_hit_rate"] = (
        grouped["total_wins"]
        / grouped[
            "total_decisions"
        ].replace(0, pd.NA)
    )

    return grouped.sort_values(
        [
            "average_wilson_lower",
            "pooled_hit_rate",
            "slates",
        ],
        ascending=[
            False,
            False,
            False,
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate research calibration reports "
            "across historical replay dates."
        )
    )

    parser.add_argument(
        "--replay-root",
        default=(
            "data/backtests/historical_replay"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=(
            "data/backtests/"
            "research_calibration_aggregate"
        ),
    )

    args = parser.parse_args()

    replay_root = Path(
        args.replay_root
    )
    output_dir = Path(
        args.output_dir
    )

    if not replay_root.exists():
        raise FileNotFoundError(
            f"Replay root not found: "
            f"{replay_root}"
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    dates = discover_dates(
        replay_root
    )

    print("=" * 88)
    print("RESEARCH CALIBRATION AGGREGATOR")
    print("=" * 88)
    print("Dates found:", len(dates))

    for slate_date in dates:
        print(" ", slate_date)

    combined_reports: dict[
        str,
        pd.DataFrame,
    ] = {}

    for filename in REPORT_FILES:
        combined = aggregate_report(
            replay_root,
            dates,
            filename,
        )

        output_name = (
            "combined_"
            + filename
        )

        combined.to_csv(
            output_dir / output_name,
            index=False,
        )

        combined_reports[
            filename
        ] = combined

    ranking_stability = (
        ranking_stability_report(
            combined_reports[
                "ranking_report.csv"
            ]
        )
    )

    ranking_stability.to_csv(
        output_dir
        / "ranking_stability_report.csv",
        index=False,
    )

    print()
    print("RANKING STABILITY")

    if ranking_stability.empty:
        print(
            "Not enough ranking data yet."
        )
    else:
        print(
            ranking_stability.to_string(
                index=False
            )
        )

    print()
    print("Outputs:")

    for path in sorted(
        output_dir.glob("*.csv")
    ):
        print(" ", path)


if __name__ == "__main__":
    main()
