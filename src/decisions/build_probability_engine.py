from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd


def numeric(
    frame: pd.DataFrame,
    column: str,
    default: float = 0.0,
) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype="float64")

    return pd.to_numeric(
        frame[column],
        errors="coerce",
    ).fillna(default)


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def probability_from_scores(
    over_score: float,
    under_score: float,
) -> tuple[float, float]:
    score_gap = over_score - under_score

    over_probability = sigmoid(score_gap / 18.0)
    under_probability = 1.0 - over_probability

    return over_probability, under_probability


def confidence_interval(
    probability: float,
    sample_size: float,
) -> tuple[float, float]:
    effective_sample = max(sample_size, 5.0)

    standard_error = math.sqrt(
        probability * (1.0 - probability) / effective_sample
    )

    lower = max(0.0, probability - 1.96 * standard_error)
    upper = min(1.0, probability + 1.96 * standard_error)

    return lower, upper


def build_probability_engine(
    source: Path,
    output: Path,
) -> int:
    if not source.exists():
        raise FileNotFoundError(
            f"Correlation board not found: {source}"
        )

    board = pd.read_csv(source).copy()

    over_scores = numeric(board, "over_score", 50.0)
    under_scores = numeric(board, "under_score", 50.0)
    sample_sizes = numeric(board, "sample_size", 10.0)

    over_probabilities: list[float] = []
    under_probabilities: list[float] = []
    selected_probabilities: list[float] = []
    lower_bounds: list[float] = []
    upper_bounds: list[float] = []
    variances: list[float] = []

    directions = (
        board.get(
            "path_direction",
            board.get(
                "model_direction",
                pd.Series("", index=board.index),
            ),
        )
        .fillna("")
        .astype(str)
        .str.upper()
    )

    for index in board.index:
        over_probability, under_probability = probability_from_scores(
            float(over_scores.loc[index]),
            float(under_scores.loc[index]),
        )

        direction = directions.loc[index]

        if direction == "UNDER":
            selected_probability = under_probability
        else:
            selected_probability = over_probability

        lower, upper = confidence_interval(
            selected_probability,
            float(sample_sizes.loc[index]),
        )

        over_probabilities.append(round(over_probability, 4))
        under_probabilities.append(round(under_probability, 4))
        selected_probabilities.append(round(selected_probability, 4))
        lower_bounds.append(round(lower, 4))
        upper_bounds.append(round(upper, 4))
        variances.append(
            round(
                selected_probability * (1.0 - selected_probability),
                4,
            )
        )

    board["over_probability"] = over_probabilities
    board["under_probability"] = under_probabilities
    board["selected_probability"] = selected_probabilities

    board["probability_edge"] = (
        board["selected_probability"] - 0.5
    ).round(4)

    board["probability_edge_percent"] = (
        board["probability_edge"] * 100.0
    ).round(2)

    board["confidence_interval_lower"] = lower_bounds
    board["confidence_interval_upper"] = upper_bounds
    board["projected_variance"] = variances

    board["probability_confidence"] = "LOW"

    board.loc[
        board["selected_probability"].ge(0.60),
        "probability_confidence",
    ] = "MEDIUM"

    board.loc[
        board["selected_probability"].ge(0.68),
        "probability_confidence",
    ] = "HIGH"

    board["probability_rank"] = (
        board["selected_probability"]
        .rank(
            method="first",
            ascending=False,
        )
        .astype("Int64")
    )

    board["probability_engine_mode"] = "RESEARCH_ONLY"
    board["production_fields_unchanged"] = 1

    preferred = [
        "probability_rank",
        "player",
        "team",
        "opponent",
        "prop_type",
        "line",
        "path_direction",
        "selection_path",
        "over_probability",
        "under_probability",
        "selected_probability",
        "probability_edge",
        "probability_edge_percent",
        "probability_confidence",
        "confidence_interval_lower",
        "confidence_interval_upper",
        "projected_variance",
        "sample_size",
        "player_comparison_score",
        "decision_strength",
        "direction_gap",
        "correlation_score",
        "correlation_warning",
        "final_selection",
        "exclusion_reason",
        "probability_engine_mode",
        "production_fields_unchanged",
    ]

    remaining = [
        column
        for column in board.columns
        if column not in preferred
    ]

    board = board[
        [column for column in preferred if column in board.columns]
        + remaining
    ]

    board = board.sort_values(
        [
            "selected_probability",
            "player_comparison_score",
        ],
        ascending=[False, False],
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    board.to_csv(output, index=False)

    return len(board)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a research-only probability board."
    )

    parser.add_argument(
        "--source",
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

    rows = build_probability_engine(
        source=args.source,
        output=args.output,
    )

    print("=" * 72)
    print("SPORTS HUB PROBABILITY ENGINE")
    print("=" * 72)
    print(f"Rows: {rows:,}")
    print(f"Saved: {args.output}")
    print("Mode: RESEARCH ONLY")
    print("Probabilities are provisional score-based estimates.")
    print("v22-control fields were not modified.")


if __name__ == "__main__":
    main()
