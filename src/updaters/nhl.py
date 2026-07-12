from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import requests

from src.db import save_frame


BASE_URL = "https://api-web.nhle.com/v1"


def get_schedule(
    start_date: date,
    weeks: int = 18,
) -> pd.DataFrame:
    rows: list[dict] = []

    for week_offset in range(weeks):
        target = start_date + timedelta(days=week_offset * 7)
        url = f"{BASE_URL}/schedule/{target.isoformat()}"

        print(f"Downloading NHL schedule week near {target}...")

        response = requests.get(url, timeout=45)
        response.raise_for_status()
        payload = response.json()

        for week in payload.get("gameWeek", []):
            for game in week.get("games", []):
                home = game.get("homeTeam") or {}
                away = game.get("awayTeam") or {}

                rows.append(
                    {
                        "game_id": game.get("id"),
                        "season": game.get("season"),
                        "game_type": game.get("gameType"),
                        "game_date": game.get("gameDate"),
                        "start_time_utc": game.get("startTimeUTC"),
                        "game_state": game.get("gameState"),
                        "venue": (
                            game.get("venue") or {}
                        ).get("default"),
                        "home_team_abbrev": home.get("abbrev"),
                        "home_team_name": (
                            home.get("name") or {}
                        ).get("default"),
                        "home_score": home.get("score"),
                        "away_team_abbrev": away.get("abbrev"),
                        "away_team_name": (
                            away.get("name") or {}
                        ).get("default"),
                        "away_score": away.get("score"),
                    }
                )

    schedule = pd.DataFrame(rows)

    if not schedule.empty and "game_id" in schedule.columns:
        schedule = schedule.drop_duplicates(
            subset=["game_id"],
            keep="last",
        )

        schedule = schedule.sort_values(
            ["game_date", "start_time_utc"],
            na_position="last",
        )

    return schedule


def update() -> None:
    today = date.today()

    # Covers approximately the previous 13 weeks
    # and the next 5 weeks.
    start_date = today - timedelta(weeks=13)

    schedule = get_schedule(
        start_date=start_date,
        weeks=18,
    )

    if schedule.empty:
        print(
            "[SKIP] No NHL games were found in the selected "
            "date range."
        )
        return

    save_frame(schedule, "nhl_schedule")

    print(f"NHL games downloaded: {len(schedule):,}")
    print(
        f"Date range: {schedule['game_date'].min()} "
        f"through {schedule['game_date'].max()}"
    )


if __name__ == "__main__":
    update()
