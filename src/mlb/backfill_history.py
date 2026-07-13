from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd


BASE = "https://statsapi.mlb.com"


def get_json(url: str, retries: int = 3) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "SportsHub/1.0"}
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as error:  # network errors vary by platform
            last_error = error
            if attempt < retries:
                time.sleep(attempt * 1.5)
    raise RuntimeError(f"MLB request failed after {retries} attempts: {url}") from last_error


def completed_game_ids(
    start_date: str,
    end_date: str,
    fetch: Callable[[str], dict] = get_json,
) -> list[tuple[str, int]]:
    query = urllib.parse.urlencode(
        {"sportId": 1, "startDate": start_date, "endDate": end_date}
    )
    schedule = fetch(f"{BASE}/api/v1/schedule?{query}")
    games: list[tuple[str, int]] = []
    for date_block in schedule.get("dates", []):
        game_date = str(date_block.get("date") or "")
        for game in date_block.get("games", []):
            status = game.get("status", {})
            abstract = str(status.get("abstractGameState") or "")
            detailed = str(status.get("detailedState") or "")
            if abstract == "Final" or detailed in {
                "Final", "Game Over", "Completed Early"
            }:
                games.append((game_date, int(game["gamePk"])))
    return games


def number(value: object, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def ip_to_outs(value: object) -> int:
    text = str(value or "0.0")
    try:
        whole, fraction = (text.split(".", 1) + ["0"])[:2]
        digit = int((fraction or "0")[0])
        if digit in (0, 1, 2):
            return int(whole) * 3 + digit
        return round(float(text) * 3)
    except (TypeError, ValueError):
        return 0


def boxscore_rows(game_date: str, game_id: int, boxscore: dict) -> list[dict]:
    rows: list[dict] = []
    teams = boxscore.get("teams", {})
    for side in ("away", "home"):
        other = "home" if side == "away" else "away"
        team_data = teams.get(side, {})
        team = str(team_data.get("team", {}).get("abbreviation") or "")
        opponent = str(teams.get(other, {}).get("team", {}).get("abbreviation") or "")
        for player in team_data.get("players", {}).values():
            person = player.get("person", {})
            name = str(person.get("fullName") or "").strip().upper()
            player_id = person.get("id")
            stats = player.get("stats", {})
            batting = stats.get("batting", {}) or {}
            pa = number(batting.get("plateAppearances"))
            if name and pa > 0:
                hits = number(batting.get("hits"))
                doubles = number(batting.get("doubles"))
                triples = number(batting.get("triples"))
                homers = number(batting.get("homeRuns"))
                singles = max(0.0, hits - doubles - triples - homers)
                runs = number(batting.get("runs"))
                rbi = number(batting.get("rbi"))
                walks = number(batting.get("baseOnBalls"))
                hbp = number(batting.get("hitByPitch"))
                steals = number(batting.get("stolenBases"))
                total_bases = singles + 2 * doubles + 3 * triples + 4 * homers
                rows.append({
                    "RESULT_DATE": game_date, "GAME_ID": str(game_id),
                    "PLAYER_ID": str(player_id or ""), "PLAYER_NAME": name,
                    "PLAYER_TYPE": "HITTER", "TEAM": team, "OPPONENT": opponent,
                    "PA": pa, "AB": number(batting.get("atBats")), "H": hits,
                    "R": runs, "RBI": rbi, "HR": homers, "BB": walks,
                    "HBP": hbp, "SO": number(batting.get("strikeOuts")), "SB": steals,
                    "DOUBLES": doubles, "TRIPLES": triples, "SINGLES": singles,
                    "TOTAL_BASES": total_bases,
                    "H_PLUS_R_PLUS_RBI": hits + runs + rbi,
                    "HITTER_FANTASY_PP": (
                        3 * singles + 5 * doubles + 8 * triples + 10 * homers
                        + 2 * runs + 2 * rbi + 2 * walks + 2 * hbp + 5 * steals
                    ),
                    "SOURCE_FILE": "MLB_STATS_API_BACKFILL",
                })

            pitching = stats.get("pitching", {}) or {}
            ip = pitching.get("inningsPitched", "0.0")
            outs = ip_to_outs(ip)
            if name and outs > 0:
                strikeouts = number(pitching.get("strikeOuts"))
                earned = number(pitching.get("earnedRuns"))
                win = min(1.0, number(pitching.get("wins")))
                started = number(pitching.get("gamesStarted")) >= 1
                quality = int(started and outs >= 18 and earned <= 3)
                rows.append({
                    "RESULT_DATE": game_date, "GAME_ID": str(game_id),
                    "PLAYER_ID": str(player_id or ""), "PLAYER_NAME": name,
                    "PLAYER_TYPE": "PITCHER", "TEAM": team, "OPPONENT": opponent,
                    "IP": ip, "OUTS": outs, "K": strikeouts, "ER": earned,
                    "BB": number(pitching.get("baseOnBalls")),
                    "HITS_ALLOWED": number(pitching.get("hits")),
                    "HR_ALLOWED": number(pitching.get("homeRuns")),
                    "PITCHES": number(pitching.get("numberOfPitches")),
                    "WIN": win, "QUALITY_START": quality,
                    "PITCHER_FANTASY_PP": 6 * win + 4 * quality - 3 * earned + 3 * strikeouts + outs,
                    "SOURCE_FILE": "MLB_STATS_API_BACKFILL",
                })
    return rows


def fetch_boxscore(
    game_date: str,
    game_id: int,
    cache_dir: Path,
    fetch: Callable[[str], dict] = get_json,
) -> dict:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{game_date}_{game_id}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    data = fetch(f"{BASE}/api/v1/game/{game_id}/boxscore")
    cache_path.write_text(json.dumps(data), encoding="utf-8")
    return data


def merge_history(existing: pd.DataFrame, new_rows: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if existing.empty:
        combined = new_rows.copy()
    else:
        dates = pd.to_datetime(existing.get("RESULT_DATE"), errors="coerce")
        keep = ~dates.between(pd.Timestamp(start), pd.Timestamp(end), inclusive="both")
        combined = pd.concat([existing.loc[keep], new_rows], ignore_index=True, sort=False)
    keys = ["RESULT_DATE", "GAME_ID", "PLAYER_NAME", "PLAYER_TYPE"]
    for column in keys:
        if column not in combined:
            combined[column] = ""
    combined = combined.drop_duplicates(keys, keep="last")
    return combined.sort_values(keys, kind="stable").reset_index(drop=True)


def run_backfill(
    start_date: str,
    end_date: str,
    history_path: Path,
    cache_dir: Path,
    fetch: Callable[[str], dict] = get_json,
) -> dict[str, int]:
    games = completed_game_ids(start_date, end_date, fetch)
    if not games:
        raise RuntimeError(f"No completed MLB games found from {start_date} through {end_date}")
    rows: list[dict] = []
    for index, (game_date, game_id) in enumerate(games, start=1):
        boxscore = fetch_boxscore(game_date, game_id, cache_dir, fetch)
        rows.extend(boxscore_rows(game_date, game_id, boxscore))
        if index % 25 == 0 or index == len(games):
            print(f"Processed {index:,}/{len(games):,} games; player-games {len(rows):,}")
    frame = pd.DataFrame(rows)
    existing = pd.read_csv(history_path, low_memory=False) if history_path.exists() else pd.DataFrame()
    merged = merge_history(existing, frame, start_date, end_date)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    if history_path.exists():
        backup = history_path.with_suffix(".pre_backfill.csv")
        history_path.replace(backup)
    temp = history_path.with_suffix(".tmp.csv")
    merged.to_csv(temp, index=False)
    temp.replace(history_path)
    return {"games": len(games), "new_player_games": len(frame), "history_rows": len(merged)}


def main() -> None:
    yesterday = date.today() - timedelta(days=1)
    parser = argparse.ArgumentParser(description="Resumable official MLB season history backfill")
    parser.add_argument("--start", default=f"{date.today().year}-03-25")
    parser.add_argument("--end", default=yesterday.isoformat())
    parser.add_argument("--history", type=Path, default=Path("data/mlb/MLB_RESULTS_HISTORY.csv"))
    parser.add_argument("--cache", type=Path, default=Path("data/mlb/backfill_cache"))
    args = parser.parse_args()
    if pd.Timestamp(args.end) < pd.Timestamp(args.start):
        raise ValueError("--end must be on or after --start")
    counts = run_backfill(args.start, args.end, args.history, args.cache)
    print("=" * 70)
    print("MLB OFFICIAL HISTORY BACKFILL")
    print("=" * 70)
    for key, value in counts.items():
        print(f"{key}: {value:,}")
    print("Model weights unchanged. Recommendations remain disabled; grade cap remains B+.")


if __name__ == "__main__":
    main()
