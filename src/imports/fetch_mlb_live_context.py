from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd


BASE = "https://statsapi.mlb.com"


def get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "SportsHub/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _team_abbreviation(team: dict) -> str:
    return str(team.get("abbreviation") or team.get("teamCode") or team.get("name") or "").strip()


def _player_by_id(players: dict, player_id: object) -> dict:
    return players.get(f"ID{player_id}", {})


def build_context(
    slate_date: str,
    fetch: Callable[[str], dict] = get_json,
    captured_at: str | None = None,
) -> pd.DataFrame:
    schedule_url = (
        f"{BASE}/api/v1/schedule?sportId=1&date={slate_date}"
        "&hydrate=team,probablePitcher"
    )
    schedule = fetch(schedule_url)
    captured = captured_at or datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, object]] = []

    for date_block in schedule.get("dates", []):
        for game in date_block.get("games", []):
            game_id = game.get("gamePk")
            if not game_id:
                continue
            status = game.get("status", {})
            detailed = str(status.get("detailedState") or "UNKNOWN")
            venue = str(game.get("venue", {}).get("name") or "")
            weather = game.get("weather", {}) or {}
            teams = game.get("teams", {})
            feed = fetch(f"{BASE}/api/v1.1/game/{game_id}/feed/live")
            game_data = feed.get("gameData", {})
            detailed = str(game_data.get("status", {}).get("detailedState") or detailed)
            venue = str(game_data.get("venue", {}).get("name") or venue)
            weather = game_data.get("weather", {}) or weather
            box_teams = feed.get("liveData", {}).get("boxscore", {}).get("teams", {})

            for side in ("away", "home"):
                other = "home" if side == "away" else "away"
                team = teams.get(side, {}).get("team", {})
                opponent = teams.get(other, {}).get("team", {})
                team_code = _team_abbreviation(team)
                opponent_code = _team_abbreviation(opponent)
                team_box = box_teams.get(side, {})
                players = team_box.get("players", {})
                batting_order = team_box.get("battingOrder", []) or []
                lineup_confirmed = int(len(batting_order) >= 9)

                for order, player_id in enumerate(batting_order, start=1):
                    person = _player_by_id(players, player_id).get("person", {})
                    name = str(person.get("fullName") or "").strip()
                    if not name:
                        continue
                    rows.append({
                        "slate_date": slate_date,
                        "captured_at": captured,
                        "game_id": str(game_id),
                        "game_status": detailed,
                        "player": name,
                        "player_id": str(player_id),
                        "player_role": "HITTER",
                        "team": team_code,
                        "opponent": opponent_code,
                        "lineup_confirmed": lineup_confirmed,
                        "batting_order": order,
                        "starter_confirmed": None,
                        "venue": venue,
                        "weather_condition": weather.get("condition"),
                        "temperature": weather.get("temp"),
                        "wind": weather.get("wind"),
                        "source": "MLB_STATS_API",
                    })

                probable = teams.get(side, {}).get("probablePitcher", {}) or {}
                probable_name = str(probable.get("fullName") or "").strip()
                if probable_name:
                    rows.append({
                        "slate_date": slate_date,
                        "captured_at": captured,
                        "game_id": str(game_id),
                        "game_status": detailed,
                        "player": probable_name,
                        "player_id": str(probable.get("id") or ""),
                        "player_role": "PITCHER",
                        "team": team_code,
                        "opponent": opponent_code,
                        "lineup_confirmed": None,
                        "batting_order": None,
                        "starter_confirmed": 1,
                        "venue": venue,
                        "weather_condition": weather.get("condition"),
                        "temperature": weather.get("temp"),
                        "wind": weather.get("wind"),
                        "source": "MLB_STATS_API_PROBABLE_PITCHER",
                    })

    columns = [
        "slate_date", "captured_at", "game_id", "game_status", "player",
        "player_id", "player_role", "team", "opponent", "lineup_confirmed",
        "batting_order", "starter_confirmed", "venue", "weather_condition",
        "temperature", "wind", "source",
    ]
    return pd.DataFrame(rows, columns=columns)


def fetch_to_csv(slate_date: str, output: Path) -> int:
    frame = build_context(slate_date)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    return len(frame)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch official MLB live game context")
    parser.add_argument("--date", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = fetch_to_csv(args.date, args.output)
    print(f"MLB live context rows: {rows:,}")
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
