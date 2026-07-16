"""Build immutable, cutoff-safe daily pregame records."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


CENTRAL = ZoneInfo("America/Chicago")


def git_sha(root: Path) -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def build_snapshot(pool: pd.DataFrame, mlb_context: pd.DataFrame | None,
                   model_version: str, root: Path, captured_at: str | None = None) -> list[dict[str, object]]:
    captured = captured_at or datetime.now(CENTRAL).isoformat()
    commit_sha = git_sha(root)
    context = mlb_context if mlb_context is not None else pd.DataFrame()
    pitcher_by_team: dict[str, dict[str, object]] = {}
    hitter_by_name: dict[str, dict[str, object]] = {}
    if not context.empty:
        for row in context.to_dict("records"):
            if str(row.get("player_role", "")).upper() == "PITCHER":
                pitcher_by_team[str(row.get("team", "")).upper()] = row
            else:
                hitter_by_name[str(row.get("player", "")).lower()] = row
    records=[]
    for row in pool.to_dict("records"):
        sport=str(row.get("league") or row.get("sport") or "").upper()
        player=str(row.get("player_name") or row.get("player") or "")
        team=str(row.get("team") or "").upper()
        hitter=hitter_by_name.get(player.lower(), {}) if sport == "MLB" else {}
        opponent=str(hitter.get("opponent") or row.get("opponent") or "").upper()
        opposing_pitcher=pitcher_by_team.get(opponent, {}) if opponent else {}
        expected_pitcher=opposing_pitcher.get("player")
        data_status="PARTIAL" if sport == "WNBA" else ("COMPLETE" if sport == "MLB" else "MISSING")
        if sport == "MLB" and not expected_pitcher:
            data_status="MISSING"
        elif sport == "MLB" and not hitter.get("lineup_confirmed"):
            data_status="PARTIAL"
        records.append({
            "slate_date": str(row.get("slate_date") or ""), "captured_at": captured,
            "sport": sport, "player": player,
            "player_id": hitter.get("player_id") or row.get("player_id"),
            "team": team, "opponent": opponent,
            "prop": row.get("stat_type") or row.get("prop_type"),
            "line": row.get("line_score") if row.get("line_score") is not None else row.get("line"),
            "game_start_time": str(row.get("start_time") or ""),
            "expected_pitcher": expected_pitcher,
            "expected_pitcher_id": opposing_pitcher.get("player_id"),
            "starter_status": "EXPECTED" if expected_pitcher else "UNAVAILABLE",
            "starter_source": opposing_pitcher.get("source"),
            "lineup_status": "CONFIRMED" if hitter.get("lineup_confirmed") else "EXPECTED_OR_UNAVAILABLE",
            "batting_order": hitter.get("batting_order"),
            "weather_condition": hitter.get("weather_condition"),
            "temperature": hitter.get("temperature"), "wind": hitter.get("wind"),
            "data_quality_status": data_status, "model_version": model_version,
            "git_commit_sha": commit_sha,
        })
    return records


def freeze_snapshot(path: Path, records: list[dict[str, object]]) -> Path:
    """Create once. Postgame or later runs cannot overwrite the frozen record."""
    if path.exists():
        raise FileExistsError(f"Pregame snapshot is immutable and already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")
    return path
