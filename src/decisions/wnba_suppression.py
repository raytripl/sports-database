"""Historical WNBA suppression context for baseline under research.

The output is descriptive evidence, not a live under recommendation. Current
injuries, starters, rotations, matchup scheme, pace, and coaching decisions
must still be confirmed before an under can clear the Raymond v17.3 gate.
"""

from __future__ import annotations

import pandas as pd

from src.decisions.wnba_opportunity import volume_series


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


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").dropna()


def _decline_score(values: pd.Series) -> float:
    if values.empty:
        return 50.0
    season = float(values.mean())
    recent = float(values.tail(5).mean())
    decline_ratio = (season - recent) / max(abs(season), 1.0)
    return _bounded(50.0 + decline_ratio * 200.0)


def calculate_suppression_context(
    player_history: pd.DataFrame,
    prop_type: str,
    line: float,
) -> dict[str, object]:
    """Calculate conservative historical under signals and ceiling risk."""

    result_column = PROP_TO_RESULT.get(prop_type)
    results = (
        _numeric(player_history, result_column)
        if result_column is not None
        else pd.Series(dtype=float)
    )
    minutes = _numeric(player_history, "MIN")
    volume = volume_series(player_history, prop_type)
    sample_size = len(results)

    if sample_size == 0:
        return {
            "suppression_score": 0.0,
            "ceiling_risk_score": 100.0,
            "minutes_decline_score": 50.0,
            "volume_decline_score": 50.0,
            "line_inflation_score": 50.0,
            "historical_under_reasons": "",
            "suppression_note": "No historical result sample",
        }

    minutes_decline = _decline_score(minutes)
    volume_decline = _decline_score(volume)

    denominator = max(abs(line), 1.0)
    upper_quartile = float(results.quantile(0.75))
    high_outcome = float(results.quantile(0.90))
    over_rate = float((results > line).mean())

    inflation_ratio = (line - upper_quartile) / denominator
    line_inflation = _bounded(50.0 + inflation_ratio * 150.0)

    ceiling_gap = (high_outcome - line) / denominator
    ceiling_risk = _bounded(
        0.60 * _bounded(50.0 + ceiling_gap * 150.0)
        + 0.40 * over_rate * 100.0
    )
    ceiling_containment = 100.0 - ceiling_risk

    volume_available = not volume.empty
    components = [
        (minutes_decline, 35.0),
        (line_inflation, 30.0),
        (ceiling_containment, 20.0),
    ]
    if volume_available:
        components.append((volume_decline, 15.0))

    raw_score = sum(value * weight for value, weight in components) / sum(
        weight for _, weight in components
    )
    sample_reliability = min(sample_size / 10.0, 1.0)
    suppression_score = _bounded(
        50.0 + (raw_score - 50.0) * sample_reliability
    )

    reasons: list[str] = []
    if minutes_decline >= 65.0:
        reasons.append("HIST_MINUTES_DECLINE")
    if volume_available and volume_decline >= 65.0:
        reasons.append("HIST_VOLUME_DECLINE")
    if line_inflation >= 65.0:
        reasons.append("HIST_LINE_INFLATION")
    if ceiling_risk <= 35.0:
        reasons.append("HIST_CEILING_CONTAINED")

    note = (
        f"Historical suppression only: {sample_size} games; "
        f"minutes decline {minutes_decline:.0f}, "
        f"line inflation {line_inflation:.0f}, ceiling risk {ceiling_risk:.0f}"
    )

    return {
        "suppression_score": suppression_score,
        "ceiling_risk_score": ceiling_risk,
        "minutes_decline_score": minutes_decline,
        "volume_decline_score": volume_decline,
        "line_inflation_score": line_inflation,
        "historical_under_reasons": ";".join(reasons),
        "suppression_note": note,
    }
