from datetime import datetime

import nflreadpy as nfl

from src.db import save_frame


def update() -> None:
    current_year = datetime.utcnow().year

    # Historical completed NFL seasons.
    # In 2026, this downloads 2018 through 2025.
    completed_seasons = list(range(2018, current_year))

    print(f"Downloading NFL seasons: {completed_seasons}")

    player_stats = nfl.load_player_stats(
        completed_seasons
    ).to_pandas()

    schedules = nfl.load_schedules(
        completed_seasons
    ).to_pandas()

    rosters = nfl.load_rosters(
        completed_seasons
    ).to_pandas()

    save_frame(
        player_stats,
        "nfl_weekly_player_stats"
    )

    save_frame(
        schedules,
        "nfl_schedules"
    )

    save_frame(
        rosters,
        "nfl_rosters"
    )