from __future__ import annotations

import argparse
import importlib
import sys
import traceback
from datetime import datetime


SPORT_MODULES = {
    "mlb": "src.updaters.mlb",
    "wnba": "src.updaters.wnba",
    "nba": "src.updaters.nba",
    "nfl": "src.updaters.nfl",
    "nhl": "src.updaters.nhl",
    "ncaab": "src.updaters.ncaab",
    "ncaaf": "src.updaters.ncaaf",
    "tennis": "src.updaters.tennis",
    "soccer": "src.updaters.soccer",
    "golf": "src.updaters.golf",
    "mma": "src.updaters.mma",
    "nascar": "src.updaters.nascar",
}


def run_sport(sport: str) -> bool:
    module_name = SPORT_MODULES[sport]

    print()
    print("=" * 64)
    print(f"UPDATING {sport.upper()}")
    print(f"STARTED: {datetime.now():%Y-%m-%d %I:%M:%S %p}")
    print("=" * 64)

    try:
        module = importlib.import_module(module_name)
        update_function = getattr(module, "update", None)

        if update_function is None:
            raise AttributeError(
                f"{module_name} does not contain an update() function."
            )

        update_function()

        print(f"[SUCCESS] {sport.upper()}")
        return True

    except Exception as error:
        print(f"[FAILED] {sport.upper()}: {error}")
        traceback.print_exc()
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update one sport or all configured sports."
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

    results: dict[str, bool] = {}

    for sport in selected_sports:
        results[sport] = run_sport(sport)

    print()
    print("=" * 64)
    print("UPDATE SUMMARY")
    print("=" * 64)

    for sport, successful in results.items():
        status = "SUCCESS" if successful else "FAILED"
        print(f"{sport.upper():12} {status}")

    failures = [
        sport
        for sport, successful in results.items()
        if not successful
    ]

    if failures:
        print()
        print("Failed sports:", ", ".join(failures))
        return 1

    print()
    print("All requested sports completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
