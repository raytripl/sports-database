import argparse
import traceback
from dotenv import load_dotenv

from src.updaters import tennis, nba, nfl, soccer, cs2

UPDATERS = {
    "tennis": tennis.update,
    "nba": nba.update,
    "nfl": nfl.update,
    "soccer": soccer.update,
    "cs2": cs2.update,
}

def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sport",
        choices=["all", *UPDATERS.keys()],
        default="all",
    )
    args = parser.parse_args()

    selected = UPDATERS if args.sport == "all" else {args.sport: UPDATERS[args.sport]}
    failures = []

    for sport, updater in selected.items():
        print(f"\n===== Updating {sport.upper()} =====")
        try:
            updater()
        except Exception as exc:
            failures.append(sport)
            print(f"[ERROR] {sport}: {exc}")
            traceback.print_exc()

    if failures:
        raise SystemExit(f"Failed updates: {', '.join(failures)}")

if __name__ == "__main__":
    main()
