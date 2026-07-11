from __future__ import annotations

from src.mlb.build_results import build_results_update
from src.mlb.history import history_update
from src.mlb.merge_model import merge_model_update
from src.updaters.mlb_download import download_recent_statcast


def update() -> None:
    print("Starting complete MLB update...")

    print("\n[1/4] Downloading recent Statcast data...")
    download_recent_statcast(days_back=10)

    print("\n[2/4] Building MLB batting and pitching results...")
    build_results_update()

    print("\n[3/4] Building MLB model database...")
    merge_model_update()

    print("\n[4/4] Updating MLB results history...")
    history_update()

    print("\nComplete MLB pipeline finished successfully.")


if __name__ == "__main__":
    update()
