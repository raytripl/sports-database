"""Team-level WNBA matchup context from completed pre-slate box scores.

This is intentionally a broad team environment signal. It is not the future
position/archetype matchup engine and cannot independently create a bet.
"""

from __future__ import annotations

import re

import pandas as pd


PROP_TO_RESULT = {
    "Points": "PTS",
    "Rebounds": "REB",
    "Assists": "AST",
    "Pts+Rebs+Asts": "PRA",
    "Pts+Rebs": "PTS_REB",
    "Pts+Asts": "PTS_AST",
    "Rebs+Asts": "REB_AST",
    "Fantasy Score": "FANTASY_SCORE_PP",
    "3-PT Made": "FG3M",
    "3-PT Attempted": "FG3A",
    "FG Attempted": "FGA",
    "FG Made": "FGM",
    "Def Rebounds": "DREB",
    "Defensive Rebounds": "DREB",
    "Off Rebounds": "OREB",
    "Offensive Rebounds": "OREB",
    "Blks+Stls": "STOCKS",
    "Blocked Shots": "BLK",
    "Steals": "STL",
    "Turnovers": "TOV",
    "2-PT Attempted": "FG2A",
    "Two Pointers Attempted": "FG2A",
    "2-PT Made": "FG2M",
    "Two Pointers Made": "FG2M",
    "Free Throws Attempted": "FTA",
    "Free Throws Made": "FTM",
}


def _bounded(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


def matchup_opponent(matchup: object, team: object) -> str | None:
    """Extract the opposing team abbreviation from NBA-style matchup text."""

    matchup_text = str(matchup).upper().strip()
    team_text = str(team).upper().strip()
    abbreviations = re.findall(r"\b[A-Z]{3}\b", matchup_text)
    opponents = [abbreviation for abbreviation in abbreviations if abbreviation != team_text]
    return opponents[0] if opponents else None


def calculate_team_matchup_context(
    history: pd.DataFrame,
    opponent: str,
    prop_type: str,
) -> dict[str, object]:
    """Return an over-friendly matchup score, shrunk toward neutral at low N."""

    result_column = PROP_TO_RESULT.get(prop_type)
    required = {"GAME_ID", "GAME_DATE", "TEAM_ABBREVIATION", "MATCHUP"}
    if result_column is None or result_column not in history.columns:
        return _empty_context("Unsupported prop type")
    if not required.issubset(history.columns):
        return _empty_context("History lacks team matchup fields")

    frame = history.copy()
    if "PLAYER_ID" in frame.columns:
        frame = frame.drop_duplicates(
            subset=["GAME_ID", "PLAYER_ID"],
            keep="last",
        )
    frame[result_column] = pd.to_numeric(frame[result_column], errors="coerce")
    frame["_opponent"] = [
        matchup_opponent(matchup, team)
        for matchup, team in zip(frame["MATCHUP"], frame["TEAM_ABBREVIATION"])
    ]
    frame = frame.dropna(subset=[result_column, "_opponent"])
    if frame.empty:
        return _empty_context("No valid team matchup history")

    game_totals = (
        frame.groupby(
            ["GAME_ID", "GAME_DATE", "TEAM_ABBREVIATION", "_opponent"],
            as_index=False,
        )[result_column]
        .sum()
        .sort_values("GAME_DATE")
    )
    league_average = float(game_totals[result_column].mean())
    opponent_games = game_totals[
        game_totals["_opponent"] == str(opponent).upper().strip()
    ]
    sample_size = len(opponent_games)
    if sample_size == 0:
        return _empty_context(f"No completed games found against {opponent}")

    allowed_average = float(opponent_games[result_column].mean())
    allowed_recent = float(opponent_games[result_column].tail(5).mean())
    blended_allowed = 0.60 * allowed_recent + 0.40 * allowed_average
    relative_difference = (
        (blended_allowed - league_average) / max(abs(league_average), 1.0)
    )
    raw_score = _bounded(50.0 + relative_difference * 100.0)
    reliability = min(sample_size / 10.0, 1.0)
    matchup_score = _bounded(50.0 + (raw_score - 50.0) * reliability)

    return {
        "matchup_score": matchup_score,
        "matchup_suppression_score": _bounded(100.0 - matchup_score),
        "team_matchup_sample_size": sample_size,
        "opponent_allowed_avg": round(allowed_average, 2),
        "opponent_allowed_l5_avg": round(allowed_recent, 2),
        "league_team_avg": round(league_average, 2),
        "matchup_note": (
            f"Team-level matchup only: {opponent} sample {sample_size}, "
            f"allows {allowed_average:.2f} vs league {league_average:.2f}"
        ),
    }


def _empty_context(note: str) -> dict[str, object]:
    return {
        "matchup_score": 50.0,
        "matchup_suppression_score": 50.0,
        "team_matchup_sample_size": 0,
        "opponent_allowed_avg": None,
        "opponent_allowed_l5_avg": None,
        "league_team_avg": None,
        "matchup_note": note,
    }
