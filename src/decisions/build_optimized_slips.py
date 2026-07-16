from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


SLIP_SIZES = (2, 4, 6)


def build_optimized_slips(
    source: Path,
    output: Path,
) -> int:
    if not source.exists():
        raise FileNotFoundError(
            f"Diversified candidates not found: {source}"
        )

    candidates = pd.read_csv(source).copy()

    selected = candidates[
        pd.to_numeric(
            candidates.get(
                "diversified_selected",
                pd.Series(0, index=candidates.index),
            ),
            errors="coerce",
        ).fillna(0).eq(1)
    ].copy()

    selected = selected.sort_values(
        "diversified_rank",
        na_position="last",
    )

    rows: list[dict[str, object]] = []

    for slip_size in SLIP_SIZES:
        available = selected.head(slip_size)

        if len(available) < slip_size:
            continue

        for leg_number, (_, row) in enumerate(
            available.iterrows(),
            start=1,
        ):
            record = row.to_dict()
            record["slip_size"] = slip_size
            record["slip_name"] = (
                f"WNBA_RESEARCH_{slip_size}_LEG"
            )
            record["leg_number"] = leg_number
            record["slip_mode"] = "RESEARCH_ONLY"
            record["production_approved"] = 0
            rows.append(record)

    slips = pd.DataFrame(rows)

    output.parent.mkdir(parents=True, exist_ok=True)
    slips.to_csv(output, index=False)

    return len(slips)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build optimized research-only slips."
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    rows = build_optimized_slips(
        source=args.source,
        output=args.output,
    )

    print("=" * 72)
    print("SPORTS HUB OPTIMIZED RESEARCH SLIPS")
    print("=" * 72)
    print(f"Slip rows: {rows}")
    print(f"Saved: {args.output}")
    print("Production approval: NO")
    print("v22-control fields were not modified.")


if __name__ == "__main__":
    main()
