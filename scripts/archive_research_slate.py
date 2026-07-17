from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


RESEARCH_ONLY = True
PRODUCTION_MODEL = "v22-control"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def git_value(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
    ):
        return None

    value = result.stdout.strip()
    return value or None


def copy_artifact(
    source: Path,
    destination: Path,
    *,
    required: bool,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source": str(source),
        "destination": str(destination),
        "required": required,
        "exists": source.exists(),
        "copied": False,
    }

    if not source.exists():
        return record

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        source,
        destination,
    )

    record.update(
        {
            "copied": True,
            "bytes": destination.stat().st_size,
            "sha256": file_sha256(destination),
        }
    )

    if destination.suffix.lower() == ".csv":
        try:
            frame = pd.read_csv(
                destination,
                low_memory=False,
            )

            record["rows"] = len(frame)
            record["columns"] = len(
                frame.columns
            )
        except pd.errors.EmptyDataError:
            record["rows"] = 0
            record["columns"] = 0
            record["empty_csv"] = True
        except Exception as exc:
            record["csv_read_error"] = str(exc)

    return record


def first_existing(
    candidates: list[Path],
) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


def newest_matching(
    directory: Path,
    pattern: str,
) -> Path | None:
    matches = [
        path
        for path in directory.glob(pattern)
        if path.is_file()
    ]

    if not matches:
        return None

    return max(
        matches,
        key=lambda path: path.stat().st_mtime,
    )


def build_artifacts(
    slate_date: str,
) -> dict[str, tuple[Path, bool]]:
    live = Path("data/live") / slate_date

    dated_processed_pool = newest_matching(
        Path("data/pools/processed"),
        f"raymond_pool_{slate_date}*.csv",
    )

    live = Path("data/live") / slate_date

    pool_candidates = [
        Path(
            "data/backtests/historical_text"
        )
        / slate_date
        / "wnba"
        / "pool.csv",
        live / "standardized_pool.csv",
        live / "raw_pool.csv",
        Path(
            "data/pools/processed"
        )
        / f"raymond_pool_{slate_date}.csv",
    ]

    if dated_processed_pool is not None:
        pool_candidates.append(
            dated_processed_pool
        )

    historical_pool = first_existing(
        pool_candidates
    )

    availability = first_existing(
        [
            Path(
                "data/runtime/prizepicks/"
                "wnba_live"
            )
            / f"availability_{slate_date}.csv",
            live / "wnba_availability.csv",
            live / "availability.csv",
        ]
    )

    return {
        "historical_pool.csv": (
            historical_pool,
            True,
        ),
        "wnba_availability.csv": (
            availability,
            True,
        ),
        "wnba_scored_board.csv": (
            live / "wnba_scored_board.csv",
            True,
        ),
        "wnba_research_rankings.csv": (
            live / "wnba_research_rankings.csv",
            False,
        ),
        "wnba_research_board.csv": (
            live / "wnba_research_board.csv",
            True,
        ),
        "wnba_research_slip.csv": (
            live / "wnba_research_slip.csv",
            False,
        ),
        "wnba_decision_engine_board.csv": (
            live
            / "wnba_decision_engine_board.csv",
            False,
        ),
        "wnba_player_comparison_board.csv": (
            live
            / "wnba_player_comparison_board.csv",
            False,
        ),
        "wnba_selection_path_board.csv": (
            live
            / "wnba_selection_path_board.csv",
            False,
        ),
        "wnba_correlation_board.csv": (
            live
            / "wnba_correlation_board.csv",
            False,
        ),
        "wnba_probability_board.csv": (
            live
            / "wnba_probability_board.csv",
            False,
        ),
        "wnba_optimized_research_slips.csv": (
            live
            / "wnba_optimized_research_slips.csv",
            False,
        ),
        "wnba_research_pipeline_manifest.json": (
            live
            / "wnba_research_pipeline_manifest.json",
            False,
        ),
        "pool_manifest.json": (
            live / "pool_manifest.json",
            False,
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create a leakage-safe, research-only "
            "pregame WNBA slate archive."
        )
    )

    parser.add_argument(
        "--date",
        required=True,
        help="Slate date in YYYY-MM-DD format.",
    )

    parser.add_argument(
        "--archive-root",
        default="data/archive",
    )

    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help=(
            "Write an incomplete archive while "
            "clearly marking missing required files."
        ),
    )

    args = parser.parse_args()

    slate_date = args.date
    archive_dir = (
        Path(args.archive_root)
        / slate_date
        / "wnba"
        / "pregame"
    )

    archive_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    artifact_definitions = build_artifacts(
        slate_date
    )

    records: dict[str, dict[str, Any]] = {}

    for destination_name, (
        source,
        required,
    ) in artifact_definitions.items():
        destination = (
            archive_dir / destination_name
        )

        records[destination_name] = (
            copy_artifact(
                source,
                destination,
                required=required,
            )
        )

    missing_required = [
        filename
        for filename, record in records.items()
        if (
            record["required"]
            and not record["copied"]
        )
    ]

    manifest = {
        "pipeline": (
            "SPORTS_HUB_PREGAME_ARCHIVE"
        ),
        "slate_date": slate_date,
        "sport": "wnba",
        "snapshot_phase": "pregame",
        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "research_only": RESEARCH_ONLY,
        "production_model": PRODUCTION_MODEL,
        "production_unchanged": True,
        "automatic_promotion": False,
        "git_commit": git_value(
            "rev-parse",
            "HEAD",
        ),
        "git_branch": git_value(
            "branch",
            "--show-current",
        ),
        "git_dirty": bool(
            git_value(
                "status",
                "--porcelain",
            )
        ),
        "archive_complete": (
            len(missing_required) == 0
        ),
        "missing_required": (
            missing_required
        ),
        "artifacts": records,
    }

    manifest_path = (
        archive_dir / "manifest.json"
    )

    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    print("=" * 88)
    print("WNBA RESEARCH PREGAME ARCHIVE")
    print("=" * 88)
    print("Date:", slate_date)
    print("Archive:", archive_dir)
    print(
        "Complete:",
        manifest["archive_complete"],
    )

    print()
    print("ARTIFACTS")

    for filename, record in records.items():
        status = (
            "COPIED"
            if record["copied"]
            else "MISSING"
        )

        requirement = (
            "REQUIRED"
            if record["required"]
            else "OPTIONAL"
        )

        print(
            f"{status:8} "
            f"{requirement:8} "
            f"{filename}"
        )

    if missing_required:
        print()
        print("MISSING REQUIRED")

        for filename in missing_required:
            print(" ", filename)

        if not args.allow_partial:
            raise SystemExit(
                "Archive incomplete. No production "
                "behavior was changed."
            )

    print()
    print("Manifest:", manifest_path)


if __name__ == "__main__":
    main()
