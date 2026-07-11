from __future__ import annotations

from src.updaters.mlb_download import download_recent_statcast


def update() -> None:
    print("Starting MLB update...")

    download_recent_statcast(days_back=10)

    print("MLB download stage complete.")
    print("MLB history/model stage will run after integration.")


if __name__ == "__main__":
    update()
