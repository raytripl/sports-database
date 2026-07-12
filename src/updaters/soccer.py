from __future__ import annotations

import os
import time

import pandas as pd
import requests

from src.db import save_frame


BASE_URL = "https://api.football-data.org/v4"
COMPETITIONS = ["PL", "PD", "SA", "BL1", "FL1", "CL"]


def _flatten_match(match: dict, competition_code: str) -> dict:
    score = match.get("score") or {}
    full_time = score.get("fullTime") or {}
    home = match.get("homeTeam") or {}
    away = match.get("awayTeam") or {}

    return {
        "competition_code": competition_code,
        "match_id": match.get("id"),
        "utc_date": match.get("utcDate"),
        "status": match.get("status"),
        "matchday": match.get("matchday"),
        "stage": match.get("stage"),
        "home_team_id": home.get("id"),
        "home_team": home.get("name"),
        "away_team_id": away.get("id"),
        "away_team": away.get("name"),
        "home_score": full_time.get("home"),
        "away_score": full_time.get("away"),
    }


def fetch_competition(
    code: str,
    headers: dict[str, str],
    max_attempts: int = 4,
) -> list[dict]:
    url = f"{BASE_URL}/competitions/{code}/matches"

    for attempt in range(1, max_attempts + 1):
        response = requests.get(
            url,
            headers=headers,
            timeout=45,
        )

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")

            try:
                wait_seconds = int(retry_after)
            except (TypeError, ValueError):
                wait_seconds = 15 * attempt

            print(
                f"[RATE LIMIT] {code}: waiting "
                f"{wait_seconds} seconds "
                f"(attempt {attempt}/{max_attempts})"
            )

            time.sleep(wait_seconds)
            continue

        response.raise_for_status()
        payload = response.json()

        return [
            _flatten_match(match, code)
            for match in payload.get("matches", [])
        ]

    print(
        f"[WARN] Skipping {code} after "
        f"{max_attempts} rate-limit responses."
    )
    return []


def update() -> None:
    token = os.getenv("FOOTBALL_DATA_TOKEN")

    if not token:
        raise RuntimeError("FOOTBALL_DATA_TOKEN is missing")

    headers = {"X-Auth-Token": token}
    rows: list[dict] = []
    successful_competitions = 0

    for index, code in enumerate(COMPETITIONS):
        print(f"Downloading soccer competition: {code}")

        competition_rows = fetch_competition(
            code=code,
            headers=headers,
        )

        if competition_rows:
            rows.extend(competition_rows)
            successful_competitions += 1

        # Free API plans commonly require spacing between requests.
        if index < len(COMPETITIONS) - 1:
            time.sleep(7)

    if not rows:
        raise RuntimeError(
            "No soccer matches were downloaded. "
            "The API may be rate-limited or the token may be invalid."
        )

    matches = pd.DataFrame(rows)

    if "match_id" in matches.columns:
        matches = matches.drop_duplicates(
            subset=["match_id"],
            keep="last",
        )

    save_frame(matches, "soccer_matches")

    print(
        f"Soccer competitions downloaded: "
        f"{successful_competitions}/{len(COMPETITIONS)}"
    )
    print(f"Soccer matches saved: {len(matches):,}")


if __name__ == "__main__":
    update()
