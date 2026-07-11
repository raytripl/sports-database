import os
import requests
import pandas as pd
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

def update() -> None:
    token = os.getenv("FOOTBALL_DATA_TOKEN")
    if not token:
        raise RuntimeError("FOOTBALL_DATA_TOKEN is missing")

    headers = {"X-Auth-Token": token}
    rows = []

    for code in COMPETITIONS:
        url = f"{BASE_URL}/competitions/{code}/matches"
        response = requests.get(url, headers=headers, timeout=45)
        response.raise_for_status()
        payload = response.json()

        for match in payload.get("matches", []):
            rows.append(_flatten_match(match, code))

    save_frame(pd.DataFrame(rows).drop_duplicates("match_id"), "soccer_matches")
