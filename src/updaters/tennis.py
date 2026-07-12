from datetime import datetime, timedelta
import os
import time

import pandas as pd
import requests

from src.db import save_frame


BASE_URL = "https://api.api-tennis.com/tennis/"


def api_request(method: str, **params) -> dict:
    api_key = os.getenv("TENNIS_API_KEY")

    if not api_key:
        raise RuntimeError("TENNIS_API_KEY is missing")

    request_params = {
        "method": method,
        "APIkey": api_key,
        **params,
    }

    response = requests.get(
        BASE_URL,
        params=request_params,
        timeout=90,
    )

    if response.status_code >= 500:
        raise RuntimeError(
            f"API-Tennis server error {response.status_code}: "
            f"{response.text[:300]}"
        )

    response.raise_for_status()

    payload = response.json()

    if payload.get("success") != 1:
        raise RuntimeError(
            payload.get("error")
            or f"Tennis API request failed: {method}"
        )

    return payload


def flatten_fixture(match: dict) -> dict:
    scores = match.get("scores") or []

    row = {
        "event_key": match.get("event_key"),
        "event_date": match.get("event_date"),
        "event_time": match.get("event_time"),
        "event_status": match.get("event_status"),
        "event_type": match.get("event_type_type"),
        "tournament_key": match.get("tournament_key"),
        "tournament_name": match.get("tournament_name"),
        "tournament_round": match.get("tournament_round"),
        "tournament_season": match.get("tournament_season"),
        "player1_key": match.get("first_player_key"),
        "player1_name": match.get("event_first_player"),
        "player2_key": match.get("second_player_key"),
        "player2_name": match.get("event_second_player"),
        "winner": match.get("event_winner"),
        "final_result": match.get("event_final_result"),
        "game_result": match.get("event_game_result"),
        "serve": match.get("event_serve"),
    }

    for index in range(5):
        set_data = scores[index] if index < len(scores) else {}

        row[f"player1_set{index + 1}"] = set_data.get("score_first")
        row[f"player2_set{index + 1}"] = set_data.get("score_second")

    return row


def update() -> None:
    today = datetime.utcnow().date()

    date_start = today
    date_stop = today

    rows = []
    failed_dates = []

    current_date = date_start

    while current_date <= date_stop:
        date_text = current_date.isoformat()

        print(f"Downloading tennis fixtures for {date_text}...")

        try:
            payload = api_request(
                "get_fixtures",
                date_start=date_text,
                date_stop=date_text,
                timezone="America/Chicago",
            )

            matches = payload.get("result", [])

            print(f"Received {len(matches)} matches")

            rows.extend(
                flatten_fixture(match)
                for match in matches
            )

        except Exception as exc:
            print(f"[WARN] {date_text}: {exc}")
            failed_dates.append(date_text)

        current_date += timedelta(days=1)

        # Reduce the chance of API rate limiting.
        time.sleep(1)

    if not rows:
        raise RuntimeError(
            "No tennis fixtures were downloaded. "
            "Check the API key, subscription, and API status."
        )

    fixtures = pd.DataFrame(rows)

    if "event_key" in fixtures.columns:
        fixtures = fixtures.drop_duplicates(
            subset=["event_key"],
            keep="last",
        )
    else:
        fixtures = fixtures.drop_duplicates()

    save_frame(
        fixtures,
        "tennis_matches",
    )

    if failed_dates:
        print(
            f"[WARN] Failed dates: {', '.join(failed_dates)}"
        )


if __name__ == "__main__":
    update()