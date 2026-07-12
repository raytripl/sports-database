from __future__ import annotations

import argparse
import importlib
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from logger import log


PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


SPORT_MODULES = {
    "mlb": "src.updaters.mlb",
    "wnba": "src.updaters.wnba",
    "nba": "src.updaters.nba",
    "nfl": "src.updaters.nfl",
    "soccer": "src.updaters.soccer",
    "tennis": "src.updaters.tennis",
    "nhl": "src.updaters.nhl",
}


def run_sport(sport: str) -> tuple[bool, float, str]:
    module_name = SPORT_MODULES[sport]
    started = time.perf_counter()

    log("=" * 68)
    log(f"UPDATING {sport.upper()}")
    log(f"STARTED: {datetime.now():%Y-%m-%d %I:%M:%S %p}")
    log("=" * 68)

    try:
        module = importlib.import_module(module_name)
        update_function = getattr(module, "update", None)

        if update_function is None:
            raise AttributeError(
                f"{module_name} does not contain an update() function."
            )

        update_function()

        elapsed = time.perf_counter() - started
        log(f"[SUCCESS] {sport.upper()} ({elapsed:.1f} seconds)")
        return True, elapsed, ""

    except Exception as error:
        elapsed = time.perf_counter() - started

        log(f"[FAILED] {sport.upper()}: {error}")
        traceback.print_exc()

        return False, elapsed, str(error)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update one completed sport or every completed sport."
    )

    parser.add_argument(
        "--sport",
        default="all",
        choices=["all", *SPORT_MODULES.keys()],
        help="Sport to update. Default: all",
    )

    args = parser.parse_args()

    selected_sports = (
        list(SPORT_MODULES)
        if args.sport == "all"
        else [args.sport]
    )

    overall_started = time.perf_counter()
    results: dict[str, tuple[bool, float, str]] = {}

    for sport in selected_sports:
        results[sport] = run_sport(sport)

    total_elapsed = time.perf_counter() - overall_started

    log("=" * 68)
    log("FINAL UPDATE SUMMARY")
    log("=" * 68)

    for sport, (successful, elapsed, error) in results.items():
        status = "SUCCESS" if successful else "FAILED"
        log(f"{sport.upper():12} {status:8} {elapsed:8.1f} seconds")

        if error:
            log(f"{'':12} Error: {error}")

    log("-" * 68)
    log(f"Total elapsed time: {total_elapsed:.1f} seconds")

    failures = [
        sport
        for sport, (successful, _, _) in results.items()
        if not successful
    ]

    if failures:
        log(f"Failed sports: {', '.join(failures)}")
        return 1

    log("All requested sports completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
