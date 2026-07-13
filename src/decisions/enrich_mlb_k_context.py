from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

import pandas as pd

from src.db import connect
from src.decisions.score_mlb_decision_board import PITCHER_COLUMNS, result_column


BASE = "https://statsapi.mlb.com/api/v1"
K_PATTERN = re.compile(r"(?:^|; )MLB_K\[[^]]*\]")


def get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "SportsHub/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def extract_stat(payload: dict) -> dict:
    for block in payload.get("stats", []):
        for split in block.get("splits", []):
            stat = split.get("stat", {})
            if stat:
                return stat
    return {}


def k_rate(stat: dict) -> tuple[float | None, int]:
    pa = int(stat.get("plateAppearances") or 0)
    strikeouts = int(stat.get("strikeOuts") or 0)
    return (None, pa) if pa <= 0 else (round(strikeouts / pa * 100, 2), pa)


def confirmed_lineup_k_rate(
    live_context: pd.DataFrame,
    history: pd.DataFrame,
    opponent: str,
) -> tuple[float | None, int, int]:
    hitters = live_context[
        (live_context["player_role"].astype(str).str.upper() == "HITTER")
        & (live_context["team"].map(normalize) == normalize(opponent))
        & (pd.to_numeric(live_context["lineup_confirmed"], errors="coerce") == 1)
    ]
    names = set(hitters["player"].map(normalize))
    player_history = history[
        (history["PLAYER_TYPE"].astype(str).str.upper() == "HITTER")
        & history["PLAYER_NAME"].map(normalize).isin(names)
    ]
    pa = int(pd.to_numeric(player_history.get("PA"), errors="coerce").fillna(0).sum())
    so = int(pd.to_numeric(player_history.get("SO"), errors="coerce").fillna(0).sum())
    rate = None if pa <= 0 else round(so / pa * 100, 2)
    return rate, pa, len(names)


def replace_k_flags(existing: object, flags: list[str], clear_legacy: bool) -> str:
    text = "" if pd.isna(existing) else str(existing).strip()
    text = K_PATTERN.sub("", text).strip("; ")
    if clear_legacy:
        text = text.replace("|HARD_VETO_K_RATE_NOT_VERIFIED", "")
        text = text.replace("HARD_VETO_K_RATE_NOT_VERIFIED|", "")
        text = text.replace("HARD_VETO_K_RATE_NOT_VERIFIED", "")
        text = text.replace("MLB_LIVE[]", "").strip("; ")
    live = "MLB_K[" + "|".join(flags or ["VERIFIED"]) + "]"
    return f"{text}; {live}" if text else live


def enrich_snapshot(
    snapshot_id: str,
    live_context_path: Path,
    history_path: Path,
    season: int,
    fetch=get_json,
) -> dict[str, int]:
    live = pd.read_csv(live_context_path)
    history = pd.read_csv(history_path)
    with connect() as connection:
        decisions = pd.read_sql_query(
            "SELECT decision_id, player, prop_type, opponent, red_flags FROM model_decisions WHERE snapshot_id = ? AND sport = 'MLB'",
            connection, params=(snapshot_id,),
        )
    pitchers = decisions[decisions["prop_type"].map(lambda p: result_column(p) in PITCHER_COLUMNS)]
    teams_payload = fetch(f"{BASE}/teams?sportId=1&season={season}")
    team_ids = {
        normalize(team.get("abbreviation") or team.get("teamCode") or team.get("name")): team.get("id")
        for team in teams_payload.get("teams", [])
    }
    live_lookup = {
        normalize(row["player"]): row
        for _, row in live[live["player_role"].astype(str).str.upper() == "PITCHER"].iterrows()
    }
    cache: dict[tuple[int, str], tuple[float | None, int]] = {}
    counts = {"pitcher_props": len(pitchers), "props_updated": 0, "fully_verified": 0}

    with connect() as connection:
        for _, decision in pitchers.iterrows():
            pitcher = live_lookup.get(normalize(decision["player"]))
            flags: list[str] = []
            overall_rate = split_rate = lineup_rate = None
            if pitcher is None:
                flags.append("HARD_VETO_MISSING_PITCHER_CONTEXT")
                hand = None
                overall_pa = split_pa = lineup_pa = lineup_count = 0
            else:
                person_id = str(pitcher.get("player_id") or "").replace(".0", "")
                person = fetch(f"{BASE}/people/{person_id}") if person_id else {}
                hand = None
                if person.get("people"):
                    hand = person["people"][0].get("pitchHand", {}).get("code")
                opponent = str(pitcher.get("opponent") or decision["opponent"])
                team_id = team_ids.get(normalize(opponent))
                if not hand:
                    flags.append("HARD_VETO_UNKNOWN_PITCHER_HAND")
                if not team_id:
                    flags.append("HARD_VETO_UNKNOWN_OPPONENT_TEAM")
                    overall_pa = split_pa = 0
                else:
                    for code in ("overall", "vl" if hand == "L" else "vr"):
                        key = (int(team_id), code)
                        if key not in cache:
                            if code == "overall":
                                url = f"{BASE}/teams/{team_id}/stats?stats=season&group=hitting&season={season}"
                            else:
                                url = f"{BASE}/teams/{team_id}/stats?stats=statSplits&group=hitting&season={season}&sitCodes={code}"
                            cache[key] = k_rate(extract_stat(fetch(url)))
                    overall_rate, overall_pa = cache[(int(team_id), "overall")]
                    split_rate, split_pa = cache[(int(team_id), "vl" if hand == "L" else "vr")]
                lineup_rate, lineup_pa, lineup_count = confirmed_lineup_k_rate(live, history, opponent)

            if overall_rate is None or overall_pa < 100:
                flags.append("HARD_VETO_LOW_TEAM_K_SAMPLE")
            if split_rate is None or split_pa < 75:
                flags.append("HARD_VETO_LOW_HANDED_K_SAMPLE")
            if lineup_rate is None or lineup_pa < 50 or lineup_count < 9:
                flags.append("HARD_VETO_LOW_CONFIRMED_LINEUP_K_SAMPLE")
            clear_legacy = not flags
            red_flags = replace_k_flags(decision["red_flags"], flags, clear_legacy)
            cursor = connection.execute("""
                UPDATE model_decisions SET opponent_k_percent = ?,
                    opponent_k_percent_vs_hand = ?, confirmed_lineup_k_percent = ?,
                    red_flags = ?, recommended = 0 WHERE decision_id = ?
            """, (overall_rate, split_rate, lineup_rate, red_flags, int(decision["decision_id"])))
            counts["props_updated"] += cursor.rowcount
            if not flags:
                counts["fully_verified"] += cursor.rowcount
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich MLB pitcher props with opponent K rates")
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--live-context", required=True, type=Path)
    parser.add_argument("--history", required=True, type=Path)
    parser.add_argument("--season", required=True, type=int)
    args = parser.parse_args()
    counts = enrich_snapshot(args.snapshot_id, args.live_context, args.history, args.season)
    print(counts)
    print("Recommendations remain disabled.")


if __name__ == "__main__":
    main()
