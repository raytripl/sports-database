from __future__ import annotations

from src.wnba.results import results_update


def update() -> None:
    print("Starting complete WNBA update...")
    results_update()
    print("Complete WNBA pipeline finished successfully.")


if __name__ == "__main__":
    update()
