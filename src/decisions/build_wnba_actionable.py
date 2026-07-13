from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


MIN_SAMPLE = 10
MIN_SCORE = 74.0
MIN_EDGE_GAP = 8.0
MIN_OPPORTUNITY = 60.0
MIN_MATCHUP_SAMPLE = 5
ALLOWED_GRADES = {"B", "B+"}
ALLOWED_STATUSES = {"ACTIVE", "PROBABLE"}


def normalize_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "confirmed"}


def blank(value: object) -> bool:
    return pd.isna(value) or not str(value).strip()


def apply_availability(board: pd.DataFrame, path: Path | None) -> pd.DataFrame:
    result = board.copy()
    for column in ("injury_status", "lineup_confirmed", "minutes_restriction"):
        if column not in result.columns:
            result[column] = pd.NA
    if path is None:
        return result
    availability = pd.read_csv(path)
    required = {"player", "injury_status", "lineup_confirmed", "captured_at"}
    missing = sorted(required - set(availability.columns))
    if missing:
        raise ValueError("Availability missing columns: " + ", ".join(missing))
    availability["_player_key"] = availability["player"].map(normalize_name)
    availability["_captured"] = pd.to_datetime(
        availability["captured_at"], errors="coerce", utc=True
    )
    availability = availability.sort_values("_captured").drop_duplicates(
        "_player_key", keep="last"
    )
    lookup = availability.set_index("_player_key")
    for index, row in result.iterrows():
        key = normalize_name(row["player"])
        if key not in lookup.index:
            continue
        live = lookup.loc[key]
        for column in ("injury_status", "lineup_confirmed", "minutes_restriction"):
            if column in live.index:
                result.at[index, column] = live[column]
        result.at[index, "availability_captured_at"] = live["captured_at"]
    return result


def classify(row: pd.Series) -> tuple[str, str]:
    failures: list[str] = []
    if str(row.get("direction", "")).upper() not in {"OVER", "UNDER"}:
        failures.append("NO_DIRECTION")
    if str(row.get("grade", "")).upper() not in ALLOWED_GRADES:
        failures.append("GRADE_BELOW_B")
    if float(row.get("sample_size", 0) or 0) < MIN_SAMPLE:
        failures.append("HISTORY_LT_10")
    if float(row.get("model_score", 0) or 0) < MIN_SCORE:
        failures.append("SCORE_LT_74")
    gap = abs(float(row.get("over_score", 0) or 0) - float(row.get("under_score", 0) or 0))
    if gap < MIN_EDGE_GAP:
        failures.append("EDGE_GAP_LT_8")
    if float(row.get("opportunity_score", 0) or 0) < MIN_OPPORTUNITY:
        failures.append("OPPORTUNITY_LT_60")
    if blank(row.get("opponent")):
        failures.append("OPPONENT_MISSING")
    if float(row.get("team_matchup_sample_size", 0) or 0) < MIN_MATCHUP_SAMPLE:
        failures.append("MATCHUP_SAMPLE_LT_5")
    if failures:
        return "PASS", "|".join(failures)

    status = str(row.get("injury_status", "")).strip().upper()
    if status not in ALLOWED_STATUSES:
        return "LIVE_BLOCKED", "STATUS_NOT_ACTIVE_OR_PROBABLE"
    if not truthy(row.get("lineup_confirmed")):
        return "LIVE_BLOCKED", "LINEUP_UNCONFIRMED"
    if not blank(row.get("minutes_restriction")):
        return "LIVE_BLOCKED", "MINUTES_RESTRICTION"
    if blank(row.get("availability_captured_at")):
        return "LIVE_BLOCKED", "NO_TIMESTAMPED_AVAILABILITY"
    captured = pd.to_datetime(row["availability_captured_at"], errors="coerce", utc=True)
    slate = pd.to_datetime(row["slate_date"], errors="coerce", utc=True)
    if pd.isna(captured) or pd.isna(slate) or captured.date() != slate.date():
        return "LIVE_BLOCKED", "STALE_AVAILABILITY"
    return "ACTIONABLE_FLEX_REVIEW", "HISTORICAL_AND_LIVE_GATES_CLEARED"


def build_actionable(scored: Path, output: Path, availability: Path | None) -> int:
    board = pd.read_csv(scored)
    board = apply_availability(board, availability)
    classifications = board.apply(classify, axis=1, result_type="expand")
    board["actionable_status"] = classifications[0]
    board["actionable_reason"] = classifications[1]
    board["recommended"] = 0
    board["entry_type"] = ""
    actionable = board[board["actionable_status"] != "PASS"].copy()
    actionable = actionable.sort_values(
        ["actionable_status", "model_score", "opportunity_score"],
        ascending=[True, False, False],
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    actionable.to_csv(output, index=False)
    return len(actionable)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a guarded WNBA actionable-review shortlist."
    )
    parser.add_argument("--scored", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--availability", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = build_actionable(args.scored, args.output, args.availability)
    board = pd.read_csv(args.output) if args.output.exists() else pd.DataFrame()
    print("=" * 70)
    print("WNBA ACTIONABLE REVIEW")
    print("=" * 70)
    print(f"Shortlist rows: {rows:,}")
    if not board.empty:
        print(board["actionable_status"].value_counts().to_string())
    print(f"Saved: {args.output}")
    print("Cap: B+ Flex review. Power eligibility remains disabled.")
    print("Official model remains Raymond Prop Model v17.3 Revision B.")


if __name__ == "__main__":
    main()
