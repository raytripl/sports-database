"""Historical WNBA opportunity context for baseline prop scoring.

This module deliberately does not claim to know the current game-day role.
It summarizes stable, observable box-score opportunity and leaves lineup,
injury, on/off, and matchup confirmation to later enrichment stages.
"""

from __future__ import annotations

import math

import pandas as pd


VOLUME_COLUMNS = {
    "Points": ("FGA", "FTA"),
    "Pts+Rebs": ("FGA", "FTA"),
    "Pts+Asts": ("FGA", "FTA"),
    "Pts+Rebs+Asts": ("FGA", "FTA"),
    "Fantasy Score": ("FGA", "FTA"),
    "3-PT Made": ("FG3A",),
}


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").dropna()


def _bounded(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return round(max(minimum, min(maximum, value)), 1)


def _weighted_expected_minutes(minutes: pd.Series) -> float | None:
    if minutes.empty:
        return None
    season = float(minutes.mean())
    recent = float(minutes.tail(5).mean())
    return round((0.35 * season) + (0.65 * recent), 1)


def volume_series(history: pd.DataFrame, prop_type: str) -> pd.Series:
    columns = VOLUME_COLUMNS.get(prop_type, ())
    if not columns:
        return pd.Series(dtype=float)

    available = [column for column in columns if column in history.columns]
    if not available:
        return pd.Series(dtype=float)

    numeric = history[available].apply(pd.to_numeric, errors="coerce")
    if prop_type in {
        "Points",
        "Pts+Rebs",
        "Pts+Asts",
        "Pts+Rebs+Asts",
        "Fantasy Score",
    }:
        fga = numeric.get("FGA", pd.Series(0.0, index=numeric.index)).fillna(0.0)
        fta = numeric.get("FTA", pd.Series(0.0, index=numeric.index)).fillna(0.0)
        return fga + (0.44 * fta)

    return numeric.sum(axis=1, min_count=1).dropna()


def calculate_opportunity_context(
    player_history: pd.DataFrame,
    prop_type: str,
) -> dict[str, object]:
    """Return conservative historical opportunity metrics on a 0-100 scale."""

    minutes = _numeric(player_history, "MIN")
    sample_size = len(minutes)
    expected_minutes = _weighted_expected_minutes(minutes)

    if sample_size == 0 or expected_minutes is None:
        return {
            "expected_minutes": None,
            "minutes_season_avg": None,
            "minutes_l5_avg": None,
            "minutes_stability": None,
            "volume_season_avg": None,
            "volume_l5_avg": None,
            "opportunity_score": 0.0,
            "opportunity_note": "No historical minutes available",
        }

    minutes_season = float(minutes.mean())
    minutes_l5 = float(minutes.tail(5).mean())
    minutes_std = float(minutes.std(ddof=0)) if sample_size > 1 else 0.0
    coefficient_of_variation = minutes_std / max(minutes_season, 1.0)
    minutes_stability = _bounded(100.0 * (1.0 - coefficient_of_variation / 0.40))

    sample_score = min(sample_size / 10.0, 1.0) * 100.0
    minutes_level_score = min(expected_minutes / 34.0, 1.0) * 100.0
    trend_ratio = (minutes_l5 - minutes_season) / max(minutes_season, 1.0)
    trend_score = _bounded(50.0 + (trend_ratio * 200.0))

    volume = volume_series(player_history, prop_type)
    if volume.empty:
        volume_season = None
        volume_l5 = None
        volume_trend_score = 50.0
        volume_weight = 0.0
    else:
        volume_season = float(volume.mean())
        volume_l5 = float(volume.tail(5).mean())
        volume_ratio = (volume_l5 - volume_season) / max(abs(volume_season), 1.0)
        volume_trend_score = _bounded(50.0 + (volume_ratio * 200.0))
        volume_weight = 15.0

    base_weights = {
        "sample": 30.0,
        "minutes_level": 25.0,
        "minutes_stability": 20.0,
        "minutes_trend": 10.0,
    }
    total_weight = sum(base_weights.values()) + volume_weight
    weighted = (
        sample_score * base_weights["sample"]
        + minutes_level_score * base_weights["minutes_level"]
        + minutes_stability * base_weights["minutes_stability"]
        + trend_score * base_weights["minutes_trend"]
        + volume_trend_score * volume_weight
    ) / total_weight

    note = (
        f"Historical opportunity only: {sample_size} games, "
        f"{expected_minutes:.1f} expected minutes"
    )
    if math.isfinite(minutes_stability):
        note += f", {minutes_stability:.0f}/100 minutes stability"

    return {
        "expected_minutes": expected_minutes,
        "minutes_season_avg": round(minutes_season, 2),
        "minutes_l5_avg": round(minutes_l5, 2),
        "minutes_stability": minutes_stability,
        "volume_season_avg": None if volume_season is None else round(volume_season, 2),
        "volume_l5_avg": None if volume_l5 is None else round(volume_l5, 2),
        "opportunity_score": _bounded(weighted),
        "opportunity_note": note,
    }
