from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")


def extract_date(path: Path) -> str | None:
    match = DATE_PATTERN.search(path.name)

    if not match:
        return None

    return match.group(1)


def normalize_text(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )


def build_probability_history(
    probability_dir: Path,
    audit_dir: Path,
    output: Path,
) -> tuple[int, int]:
    probability_files = {
        date: path
        for path in probability_dir.glob(
            "wnba_probability_board_*.csv"
        )
        if (date := extract_date(path)) is not None
    }

    audit_files = {
        date: path
        for path in audit_dir.glob(
            "wnba_full_audit_*.csv"
        )
        if (date := extract_date(path)) is not None
    }

    completed_dates = sorted(
        set(probability_files) & set(audit_files)
    )

    collected: list[pd.DataFrame] = []

    for slate_date in completed_dates:
        probability = pd.read_csv(
            probability_files[slate_date]
        ).copy()

        audit = pd.read_csv(
            audit_files[slate_date]
        ).copy()

        required_probability = {
            "player",
            "prop_type",
            "line",
            "selected_probability",
        }

        required_audit = {
            "player",
            "prop_type",
            "line",
            "audit_status",
        }

        missing_probability = (
            required_probability - set(probability.columns)
        )

        missing_audit = (
            required_audit - set(audit.columns)
        )

        if missing_probability:
            raise ValueError(
                f"{probability_files[slate_date]} missing "
                f"{sorted(missing_probability)}"
            )

        if missing_audit:
            raise ValueError(
                f"{audit_files[slate_date]} missing "
                f"{sorted(missing_audit)}"
            )

        probability["_player_key"] = normalize_text(
            probability["player"]
        )

        probability["_prop_key"] = normalize_text(
            probability["prop_type"]
        )

        audit["_player_key"] = normalize_text(
            audit["player"]
        )

        audit["_prop_key"] = normalize_text(
            audit["prop_type"]
        )

        probability["_line_key"] = pd.to_numeric(
            probability["line"],
            errors="coerce",
        ).round(4)

        audit["_line_key"] = pd.to_numeric(
            audit["line"],
            errors="coerce",
        ).round(4)

        audit_columns = [
            "_player_key",
            "_prop_key",
            "_line_key",
            "audit_status",
        ]

        for optional in [
            "actual_value",
            "directional_margin",
            "process_classification",
        ]:
            if optional in audit.columns:
                audit_columns.append(optional)

        audit_subset = audit[
            audit_columns
        ].drop_duplicates(
            [
                "_player_key",
                "_prop_key",
                "_line_key",
            ],
            keep="last",
        )

        merged = probability.merge(
            audit_subset,
            on=[
                "_player_key",
                "_prop_key",
                "_line_key",
            ],
            how="left",
            validate="many_to_one",
        )

        merged["slate_date"] = slate_date

        merged["actual_hit"] = pd.NA

        resolved = merged["audit_status"].isin(
            ["HIT", "MISS"]
        )

        merged.loc[
            resolved,
            "actual_hit",
        ] = (
            merged.loc[
                resolved,
                "audit_status",
            ]
            .eq("HIT")
            .astype(int)
        )

        merged["actual_hit"] = pd.to_numeric(
            merged["actual_hit"],
            errors="coerce",
        ).astype("Int64")

        merged["raw_probability"] = pd.to_numeric(
            merged["selected_probability"],
            errors="coerce",
        )

        merged["history_status"] = "UNRESOLVED"

        merged.loc[
            resolved,
            "history_status",
        ] = "RESOLVED"

        preferred = [
            "slate_date",
            "player",
            "team",
            "opponent",
            "prop_type",
            "line",
            "path_direction",
            "selection_path",
            "raw_probability",
            "probability_edge_percent",
            "probability_confidence",
            "probability_rank",
            "player_comparison_score",
            "decision_strength",
            "direction_gap",
            "audit_status",
            "actual_hit",
            "actual_value",
            "directional_margin",
            "process_classification",
            "history_status",
        ]

        remaining = [
            column
            for column in merged.columns
            if column not in preferred
            and not column.startswith("_")
        ]

        merged = merged[
            [
                column
                for column in preferred
                if column in merged.columns
            ]
            + remaining
        ]

        collected.append(merged)

    if collected:
        history = pd.concat(
            collected,
            ignore_index=True,
        )
    else:
        history = pd.DataFrame()

    if not history.empty:
        history = history.sort_values(
            [
                "slate_date",
                "raw_probability",
            ],
            ascending=[True, False],
        )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    history.to_csv(
        output,
        index=False,
    )

    resolved_rows = (
        int(history["actual_hit"].notna().sum())
        if "actual_hit" in history.columns
        else 0
    )

    return len(history), resolved_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect completed WNBA probability boards "
            "and audit results into one historical dataset."
        )
    )

    parser.add_argument(
        "--probability-dir",
        type=Path,
        default=Path("data/model_runs"),
    )

    parser.add_argument(
        "--audit-dir",
        type=Path,
        default=Path("data/audits"),
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    rows, resolved = build_probability_history(
        probability_dir=args.probability_dir,
        audit_dir=args.audit_dir,
        output=args.output,
    )

    print("=" * 72)
    print("SPORTS HUB WNBA PROBABILITY HISTORY")
    print("=" * 72)
    print(f"Rows: {rows:,}")
    print(f"Resolved rows: {resolved:,}")
    print(f"Saved: {args.output}")
    print("Mode: RESEARCH ONLY")
    print("v22-control fields were not modified.")


if __name__ == "__main__":
    main()
