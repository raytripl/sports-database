from __future__ import annotations

from datetime import date, timedelta, datetime
from pathlib import Path
import json
import urllib.request

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "mlb"
DATA_DIR.mkdir(parents=True, exist_ok=True)


BATTING_OUTPUT = DATA_DIR / "MLB_BATTING_RESULTS.csv"
PITCHING_OUTPUT = DATA_DIR / "MLB_PITCHING_RESULTS.csv"


def get_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
        },
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def get_final_game_ids(game_date: str) -> list[int]:
    url = (
        "https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&date={game_date}"
    )

    data = get_json(url)
    game_ids: list[int] = []

    for date_block in data.get("dates", []):
        for game in date_block.get("games", []):
            status = game.get("status", {})
            abstract_state = status.get("abstractGameState", "")
            detailed_state = status.get("detailedState", "")

            if (
                abstract_state == "Final"
                or detailed_state in {
                    "Final",
                    "Game Over",
                    "Completed Early",
                }
            ):
                game_ids.append(game["gamePk"])

    return game_ids


def format_date(game_date: str) -> str:
    parsed = datetime.strptime(game_date, "%Y-%m-%d")
    return parsed.strftime("%b %#d, %Y")


def safe_number(value, default=0):
    if value is None or value == "":
        return default

    return value


def build_results(game_date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    game_ids = get_final_game_ids(game_date)

    if not game_ids:
        raise RuntimeError(
            f"No completed MLB games were found for {game_date}."
        )

    batting_rows: list[dict] = []
    pitching_rows: list[dict] = []

    display_date = format_date(game_date)

    for game_id in game_ids:
        url = (
            f"https://statsapi.mlb.com/api/v1/game/{game_id}/boxscore"
        )

        boxscore = get_json(url)

        teams = boxscore.get("teams", {})

        for side in ["away", "home"]:
            team_data = teams.get(side, {})
            opponent_side = "home" if side == "away" else "away"

            team_name = (
                team_data
                .get("team", {})
                .get("abbreviation", "")
            )

            opponent_name = (
                teams
                .get(opponent_side, {})
                .get("team", {})
                .get("abbreviation", "")
            )

            players = team_data.get("players", {})

            for player_data in players.values():
                person = player_data.get("person", {})
                player_name = person.get("fullName", "")
                player_id = person.get("id", "")

                stats = player_data.get("stats", {})

                batting = stats.get("batting", {})

                if batting and safe_number(
                    batting.get("plateAppearances"), 0
                ) > 0:
                    batting_rows.append(
                        {
                            "Name": player_name,
                            "Date": display_date,
                            "Tm": team_name,
                            "Opp": opponent_name,
                            "G": 1,
                            "PA": safe_number(
                                batting.get("plateAppearances")
                            ),
                            "AB": safe_number(
                                batting.get("atBats")
                            ),
                            "R": safe_number(
                                batting.get("runs")
                            ),
                            "H": safe_number(
                                batting.get("hits")
                            ),
                            "2B": safe_number(
                                batting.get("doubles")
                            ),
                            "3B": safe_number(
                                batting.get("triples")
                            ),
                            "HR": safe_number(
                                batting.get("homeRuns")
                            ),
                            "RBI": safe_number(
                                batting.get("rbi")
                            ),
                            "BB": safe_number(
                                batting.get("baseOnBalls")
                            ),
                            "IBB": safe_number(
                                batting.get("intentionalWalks")
                            ),
                            "SO": safe_number(
                                batting.get("strikeOuts")
                            ),
                            "HBP": safe_number(
                                batting.get("hitByPitch")
                            ),
                            "SH": safe_number(
                                batting.get("sacBunts")
                            ),
                            "SF": safe_number(
                                batting.get("sacFlies")
                            ),
                            "GDP": safe_number(
                                batting.get("groundOuts")
                            ),
                            "SB": safe_number(
                                batting.get("stolenBases")
                            ),
                            "CS": safe_number(
                                batting.get("caughtStealing")
                            ),
                            "BA": batting.get("avg", ""),
                            "OBP": batting.get("obp", ""),
                            "SLG": batting.get("slg", ""),
                            "OPS": batting.get("ops", ""),
                            "mlbID": player_id,
                        }
                    )

                pitching = stats.get("pitching", {})

                innings_pitched = pitching.get(
                    "inningsPitched",
                    "0.0",
                )

                if pitching and str(innings_pitched) != "0.0":
                    pitching_rows.append(
                        {
                            "Name": player_name,
                            "Date": display_date,
                            "Tm": team_name,
                            "Opp": opponent_name,
                            "G": 1,
                            "GS": safe_number(
                                pitching.get("gamesStarted")
                            ),
                            "W": safe_number(
                                pitching.get("wins")
                            ),
                            "L": safe_number(
                                pitching.get("losses")
                            ),
                            "SV": safe_number(
                                pitching.get("saves")
                            ),
                            "IP": innings_pitched,
                            "H": safe_number(
                                pitching.get("hits")
                            ),
                            "R": safe_number(
                                pitching.get("runs")
                            ),
                            "ER": safe_number(
                                pitching.get("earnedRuns")
                            ),
                            "BB": safe_number(
                                pitching.get("baseOnBalls")
                            ),
                            "SO": safe_number(
                                pitching.get("strikeOuts")
                            ),
                            "HR": safe_number(
                                pitching.get("homeRuns")
                            ),
                            "HBP": safe_number(
                                pitching.get("hitBatsmen")
                            ),
                            "ERA": pitching.get("era", ""),
                            "BF": safe_number(
                                pitching.get("battersFaced")
                            ),
                            "Pit": safe_number(
                                pitching.get("numberOfPitches")
                            ),
                            "Str": safe_number(
                                pitching.get("strikes")
                            ),
                            "WHIP": pitching.get("whip", ""),
                            "mlbID": player_id,
                        }
                    )

    batting_df = pd.DataFrame(batting_rows)
    pitching_df = pd.DataFrame(pitching_rows)

    if batting_df.empty:
        raise RuntimeError("No batting results were created.")

    if pitching_df.empty:
        raise RuntimeError("No pitching results were created.")

    return batting_df, pitching_df


def build_results_update() -> None:
    target_date = (
        date.today() - timedelta(days=1)
    ).isoformat()

    print(f"Downloading MLB box scores for {target_date}...")

    batting_df, pitching_df = build_results(target_date)

    batting_df.to_csv(
        BATTING_OUTPUT,
        index=False,
    )

    pitching_df.to_csv(
        PITCHING_OUTPUT,
        index=False,
    )

    print("DONE")
    print(
        f"Created {BATTING_OUTPUT.name}: "
        f"{len(batting_df)} hitter rows"
    )
    print(
        f"Created {PITCHING_OUTPUT.name}: "
        f"{len(pitching_df)} pitcher rows"
    )
    print(f"Result date: {target_date}")


if __name__ == "__main__":
    build_results_update()