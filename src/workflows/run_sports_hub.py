"""One-button guarded Sports Hub workflow."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
CENTRAL = ZoneInfo("America/Chicago")


def run_command(
    name: str,
    command: list[str],
    required: bool = True,
) -> dict[str, object]:
    print()
    print("=" * 72)
    print(name)
    print("=" * 72)
    print(" ".join(command))
    print()

    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        check=False,
    )

    status = (
        "SUCCESS"
        if completed.returncode == 0
        else "FAILED"
    )

    result = {
        "name": name,
        "status": status,
        "required": required,
        "exit_code": completed.returncode,
    }

    if required and completed.returncode != 0:
        raise RuntimeError(
            f"{name} failed with exit code "
            f"{completed.returncode}"
        )

    return result


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--date",
        default=datetime.now(CENTRAL).strftime(
            "%Y-%m-%d"
        ),
    )

    parser.add_argument(
        "--skip-update",
        action="store_true",
    )

    parser.add_argument(
        "--skip-tests",
        action="store_true",
    )

    args = parser.parse_args()

    python = str(PYTHON)
    day = args.date
    live = ROOT / "data" / "live" / day
    live.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, object]] = []

    try:
        if not args.skip_tests:
            results.append(
                run_command(
                    "TEST SUITE",
                    [
                        python,
                        "-m",
                        "pytest",
                        "-q",
                    ],
                    required=True,
                )
            )

        if not args.skip_update:
            results.append(
                run_command(
                    "UPDATE WNBA RESULTS",
                    [
                        python,
                        "update_all.py",
                        "--sport",
                        "wnba",
                    ],
                    required=False,
                )
            )

        results.append(
            run_command(
                "IMPORT DOWNLOAD EXPORTS",
                [
                    python,
                    "-m",
                    "src.imports.import_downloaded_pools",
                    "--maximum-age-hours",
                    "36",
                ],
                required=False,
            )
        )

        results.append(
            run_command(
                "BUILD CURRENT POOL",
                [
                    python,
                    "-m",
                    "src.workflows.daily_sports_hub",
                    "--date",
                    day,
                    "--stage",
                    "pool",
                    "--sport",
                    "all",
                ],
                required=True,
            )
        )

        results.append(
            run_command(
                "CAPTURE LIVE CONTEXT",
                [
                    python,
                    "-m",
                    "src.workflows.daily_sports_hub",
                    "--date",
                    day,
                    "--stage",
                    "context",
                    "--sport",
                    "all",
                ],
                required=True,
            )
        )

        results.append(
            run_command(
                "SCORE MLB AND WNBA",
                [
                    python,
                    "-m",
                    "src.workflows.daily_sports_hub",
                    "--date",
                    day,
                    "--stage",
                    "score",
                    "--sport",
                    "all",
                ],
                required=True,
            )
        )

        results.append(
            run_command(
                "BUILD RESEARCH SLIPS",
                [
                    python,
                    "-m",
                    "src.decisions.build_daily_research_slips",
                    "--date",
                    day,
                ],
                required=True,
            )
        )

        results.append(
            run_command(
                "BUILD DAILY REPORT",
                [
                    python,
                    "-m",
                    "src.workflows.daily_sports_hub",
                    "--date",
                    day,
                    "--stage",
                    "report",
                    "--sport",
                    "all",
                ],
                required=True,
            )
        )

        required_outputs = [
            live / "pool_manifest.json",
            live / "standardized_pool.csv",
            live / "scored_board.csv",
            live / "wnba_scored_board.csv",
            live / "mlb_scored_board.csv",
            live / "final_board.csv",
            live / "report.html",
            live / "research_power_2_leg.csv",
            live / "research_flex_4_leg.csv",
        ]

        missing = [
            str(path)
            for path in required_outputs
            if not path.exists()
        ]

        overall_status = (
            "SUCCESS"
            if not missing
            else "PARTIAL"
        )

    except Exception as error:
        overall_status = "FAILED"
        missing = []
        results.append(
            {
                "name": "WORKFLOW_EXCEPTION",
                "status": "FAILED",
                "error": (
                    f"{type(error).__name__}: {error}"
                ),
            }
        )

    manifest = {
        "slate_date": day,
        "completed_at": datetime.now(
            CENTRAL
        ).isoformat(),
        "overall_status": overall_status,
        "research_only": True,
        "production_model": "v22-control",
        "production_unchanged": True,
        "automatic_promotion": False,
        "results": results,
        "missing_outputs": missing,
    }

    manifest_path = (
        live
        / "one_button_manifest.json"
    )

    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 72)
    print("SPORTS HUB COMPLETE")
    print("=" * 72)
    print(json.dumps(manifest, indent=2))

    if overall_status == "FAILED":
        sys.exit(1)


if __name__ == "__main__":
    main()
