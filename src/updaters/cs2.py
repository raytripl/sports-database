import os
import requests
import pandas as pd
from src.db import save_frame

BASE_URL = "https://api.pandascore.co/csgo"

def update() -> None:
    token = os.getenv("PANDASCORE_TOKEN")
    if not token:
        raise RuntimeError("PANDASCORE_TOKEN is missing")

    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "page[size]": 100,
        "sort": "-begin_at",
    }

    response = requests.get(
        f"{BASE_URL}/matches",
        headers=headers,
        params=params,
        timeout=45,
    )
    response.raise_for_status()

    rows = []
    for match in response.json():
        opponents = match.get("opponents") or []
        team1 = opponents[0].get("opponent", {}) if len(opponents) > 0 else {}
        team2 = opponents[1].get("opponent", {}) if len(opponents) > 1 else {}
        league = match.get("league") or {}
        serie = match.get("serie") or {}
        tournament = match.get("tournament") or {}
        winner = match.get("winner") or {}

        rows.append({
            "match_id": match.get("id"),
            "name": match.get("name"),
            "status": match.get("status"),
            "begin_at": match.get("begin_at"),
            "end_at": match.get("end_at"),
            "number_of_games": match.get("number_of_games"),
            "match_type": match.get("match_type"),
            "league_id": league.get("id"),
            "league": league.get("name"),
            "serie_id": serie.get("id"),
            "serie": serie.get("full_name") or serie.get("name"),
            "tournament_id": tournament.get("id"),
            "tournament": tournament.get("name"),
            "team1_id": team1.get("id"),
            "team1": team1.get("name"),
            "team2_id": team2.get("id"),
            "team2": team2.get("name"),
            "winner_id": winner.get("id"),
            "winner": winner.get("name"),
        })

    save_frame(pd.DataFrame(rows), "cs2_matches")
