from __future__ import annotations

import pandas as pd


def calculate_standard_movement(lines: pd.DataFrame) -> pd.DataFrame:
    required = {"captured_at", "slate_date", "sport", "player", "prop_type", "line", "is_standard_line"}
    missing = sorted(required - set(lines.columns))
    if missing:
        raise ValueError("Line history is missing columns: " + ", ".join(missing))
    frame = lines[lines["is_standard_line"].fillna(0).astype(bool)].copy()
    if frame.empty:
        return pd.DataFrame()
    frame["captured_at"] = pd.to_datetime(frame["captured_at"], errors="coerce", utc=True)
    frame["line"] = pd.to_numeric(frame["line"], errors="coerce")
    frame = frame.dropna(subset=["captured_at", "line"])
    keys = ["slate_date", "sport", "player", "prop_type"]
    output = []
    for values, group in frame.sort_values("captured_at").groupby(keys, dropna=False):
        group = group.drop_duplicates("captured_at", keep="last")
        current = group.iloc[-1]
        opening = group.iloc[0]
        previous = group.iloc[-2] if len(group) > 1 else current
        changes = group["line"].diff().dropna()
        signs = changes[changes.ne(0)].map(lambda value: 1 if value > 0 else -1)
        reversals = int((signs.diff().abs() == 2).sum())
        elapsed_hours = max((current["captured_at"] - opening["captured_at"]).total_seconds() / 3600, 0)
        movement = float(current["line"] - opening["line"])
        output.append(dict(zip(keys, values)) | {
            "opening_standard_line": float(opening["line"]),
            "previous_standard_line": float(previous["line"]),
            "current_standard_line": float(current["line"]),
            "closing_standard_line": float(current["line"]) if bool(current.get("is_closing_line", False)) else None,
            "absolute_movement": abs(movement),
            "direction": "UP" if movement > 0 else "DOWN" if movement < 0 else "FLAT",
            "time_since_movement_minutes": float((current["captured_at"] - previous["captured_at"]).total_seconds() / 60),
            "movement_velocity_per_hour": movement / elapsed_hours if elapsed_hours else 0.0,
            "number_of_reversals": reversals,
            "over_odds_movement": None,
            "under_odds_movement": None,
            "model_agreement": None,
            "value_disappeared": None,
            "recommendation_eligible": False,
        })
    return pd.DataFrame(output)
