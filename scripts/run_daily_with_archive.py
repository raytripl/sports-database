from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path


def run(command: list[str]) -> None:
    print()
    print("$", " ".join(command))

    subprocess.run(
        command,
        check=True,
    )


def find_actual_slate_date(
    requested_date: str,
) -> str:
    requested_live = (
        Path("data/live")
        / requested_date
    )

    required_files = [
        requested_live
        / "wnba_scored_board.csv",
        requested_live
        / "wnba_research_board.csv",
    ]

    if all(
        path.exists()
        for path in required_files
    ):
        return requested_date

    live_root = Path("data/live")

    if not live_root.exists():
        raise RuntimeError(
            "data/live does not exist."
        )

    candidates: list[
        tuple[str, float]
    ] = []

    for directory in live_root.iterdir():
        if not directory.is_dir():
            continue

        try:
            date.fromisoformat(
                directory.name
            )
        except ValueError:
            continue

        scored = (
            directory
            / "wnba_scored_board.csv"
        )

        research = (
            directory
            / "wnba_research_board.csv"
        )

        if not (
            scored.exists()
            and research.exists()
        ):
            continue

        latest_mtime = max(
            scored.stat().st_mtime,
            research.stat().st_mtime,
        )

        candidates.append(
            (
                directory.name,
                latest_mtime,
            )
        )

    if not candidates:
        raise RuntimeError(
            "No complete WNBA live slate "
            "directory was found."
        )

    candidates.sort(
        key=lambda item: item[1],
        reverse=True,
    )

    actual_date = candidates[0][0]

    print()
    print(
        "Requested archive date:",
        requested_date,
    )
    print(
        "Detected pipeline slate date:",
        actual_date,
    )

    return actual_date


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Sports Hub daily research "
            "pipeline and archive its actual "
            "pregame slate."
        )
    )

    parser.add_argument(
        "--date",
        required=True,
        help=(
            "Requested run date. The wrapper "
            "will detect the actual generated "
            "slate date before archiving."
        ),
    )

    parser.add_argument(
        "--stage",
        default=None,
    )

    parser.add_argument(
        "--allow-partial-archive",
        action="store_true",
    )

    parser.add_argument(
        "--archive-only",
        action="store_true",
        help=(
            "Skip the daily pipeline and archive "
            "existing outputs."
        ),
    )

    args = parser.parse_args()
    python = sys.executable

    sports_hub_args = [
        "./sports_hub.sh",
        "daily",
    ]

    if args.stage:
        sports_hub_args.extend(
            [
                "--stage",
                args.stage,
            ]
        )

    daily_command = [
        "bash",
        *sports_hub_args,
    ]

    if not args.archive_only:
        run(daily_command)
    else:
        print()
        print(
            "Skipping daily pipeline; "
            "archive-only mode enabled."
        )

    actual_date = find_actual_slate_date(
        args.date
    )

    archive_command = [
        python,
        "scripts/archive_research_slate.py",
        "--date",
        actual_date,
    ]

    if args.allow_partial_archive:
        archive_command.append(
            "--allow-partial"
        )

    run(archive_command)

    run(
        [
            python,
            "scripts/build_archive_inventory.py",
        ]
    )

    print()
    print(
        "Daily pipeline completed."
    )
    print(
        "Requested date:",
        args.date,
    )
    print(
        "Archived slate date:",
        actual_date,
    )


if __name__ == "__main__":
    main()
