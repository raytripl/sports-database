from pathlib import Path


SPORT = "ncaaf"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / SPORT


def update() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"{SPORT.upper()} updater loaded.")
    print(f"Output folder: {DATA_DIR}")
    print("Data source connection will be added next.")


if __name__ == "__main__":
    update()
