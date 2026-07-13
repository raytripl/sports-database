from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


PROP_ALIASES = {
    "hits": "H",
    "singles": "SINGLES",
    "totalbases": "TOTAL_BASES",
    "hitsrunsrbis": "H_PLUS_R_PLUS_RBI",
    "hitterfantasyscore": "HITTER_FANTASY_PP",
    "runs": "R",
    "rbis": "RBI",
    "batterwalks": "BB",
    "walks": "BB",
    "stolenbases": "SB",
    "homeruns": "HR",
    "pitcherstrikeouts": "K",
    "strikeouts": "K",
    "pitchingouts": "OUTS",
    "totalpitches": "PITCHES",
    "pitcherfantasyscore": "PITCHER_FANTASY_PP",
    "earnedrunsallowed": "ER",
    "hitsallowed": "HITS_ALLOWED",
}

PITCHER_COLUMNS = {
    "K",
    "OUTS",
    "PITCHES",
    "PITCHER_FANTASY_PP",
    "ER",
    "HITS_ALLOWED",
}

TEXT_COLUMNS = [
    "direction",
    "grade",
    "entry_type",
    "over_reason",
    "under_reason",
    "red_flags",
    "decision_reason",
]

BASELINE_FLAG = (
    "MLB baseline only: confirmed lineup, batting order, starting pitcher, "
    "weather, platoon role, opponent K%, and live workload are not verified"
)


def normalize_token(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def normalize_name(value: object) -> str:
    return normalize_token(value)


def result_column(prop_type: object) -> str | None:
    token = normalize_token(prop_type)
    token = token.replace("pp", "").replace("ud", "")
    return PROP_ALIASES.get(token)


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").dropna()


def clip(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


def historical_scores(values: pd.Series, line: float) -> dict[str, object]:
    values = numeric(values)
    size = len(values)
    if not size:
        return {
            "sample_size": 0,
            "season_avg": None,
            "l5_avg": None,
            "l10_avg": None,
            "season_over_rate": None,
            "l5_over_rate": None,
            "l10_over_rate": None,
            "season_under_rate": None,
            "l5_under_rate": None,
            "l10_under_rate": None,
            "over_score": 0.0,
            "under_score": 0.0,
        }

    l5, l10 = values.tail(5), values.tail(10)
    avg = float(values.mean())
    l5_avg, l10_avg = float(l5.mean()), float(l10.mean())
    over = float((values > line).mean())
    l5_over, l10_over = float((l5 > line).mean()), float((l10 > line).mean())
    under = float((values < line).mean())
    l5_under, l10_under = float((l5 < line).mean()), float((l10 < line).mean())
    denom = max(abs(line), 1.0)
    sample = min(size / 10.0, 1.0)
    over_edge = (l10_avg - line) / denom * 100
    under_edge = (line - l10_avg) / denom * 100
    over_score = (
        .30 * over * 100 + .25 * l10_over * 100 + .15 * l5_over * 100
        + .20 * (50 + over_edge) + .10 * sample * 100
    )
    under_score = (
        .30 * under * 100 + .25 * l10_under * 100 + .15 * l5_under * 100
        + .20 * (50 + under_edge) + .10 * sample * 100
    )
    return {
        "sample_size": size,
        "season_avg": avg,
        "l5_avg": l5_avg,
        "l10_avg": l10_avg,
        "season_over_rate": over,
        "l5_over_rate": l5_over,
        "l10_over_rate": l10_over,
        "season_under_rate": under,
        "l5_under_rate": l5_under,
        "l10_under_rate": l10_under,
        "over_score": clip(over_score),
        "under_score": clip(under_score),
    }


def opportunity_context(history: pd.DataFrame, is_pitcher: bool) -> dict[str, object]:
    if history.empty:
        return {
            "opportunity_score": 0.0,
            "expected_plate_appearances": None,
            "expected_innings": None,
            "expected_pitch_count": None,
            "workload_score": 0.0,
            "opportunity_note": "NO_PLAYER_HISTORY",
        }

    if is_pitcher:
        pitches = numeric(history.get("PITCHES", pd.Series(dtype=float))).tail(10)
        outs = numeric(history.get("OUTS", pd.Series(dtype=float))).tail(10)
        expected_pitches = None if pitches.empty else float(pitches.mean())
        expected_outs = None if outs.empty else float(outs.mean())
        expected_innings = None if expected_outs is None else expected_outs / 3.0
        pitch_component = min((expected_pitches or 0) / 95.0, 1.0) * 55
        outs_component = min((expected_outs or 0) / 18.0, 1.0) * 35
        sample_component = min(len(history) / 10.0, 1.0) * 10
        score = clip(pitch_component + outs_component + sample_component)
        return {
            "opportunity_score": score,
            "expected_plate_appearances": None,
            "expected_innings": expected_innings,
            "expected_pitch_count": expected_pitches,
            "workload_score": score,
            "opportunity_note": (
                f"HISTORICAL_WORKLOAD pitches={expected_pitches!s} "
                f"innings={expected_innings!s}"
            ),
        }

    pa = numeric(history.get("PA", pd.Series(dtype=float))).tail(10)
    expected_pa = None if pa.empty else float(pa.mean())
    stability = 0.0 if pa.empty else max(0.0, 1.0 - float(pa.std(ddof=0)) / 2.0)
    score = clip(min((expected_pa or 0) / 4.5, 1.0) * 75 + stability * 15 + min(len(history) / 10, 1) * 10)
    return {
        "opportunity_score": score,
        "expected_plate_appearances": expected_pa,
        "expected_innings": None,
        "expected_pitch_count": None,
        "workload_score": score,
        "opportunity_note": f"HISTORICAL_PA expected={expected_pa!s}",
    }


def suppression_context(history: pd.DataFrame, is_pitcher: bool) -> dict[str, object]:
    workload_col = "PITCHES" if is_pitcher else "PA"
    workload = numeric(history.get(workload_col, pd.Series(dtype=float)))
    if len(workload) < 3:
        return {"suppression_score": 50.0, "suppression_note": "LOW_WORKLOAD_SAMPLE"}
    recent = float(workload.tail(3).mean())
    prior = float(workload.tail(10).mean())
    decline = max(0.0, (prior - recent) / max(prior, 1.0))
    return {
        "suppression_score": clip(35 + decline * 65),
        "suppression_note": f"HISTORICAL_WORKLOAD_DECLINE={decline:.3f}",
    }


def matchup_context(history: pd.DataFrame, opponent: object, column: str) -> dict[str, object]:
    opponent_key = normalize_token(opponent)
    if not opponent_key or "OPPONENT" not in history or column not in history:
        return {"matchup_score": 50.0, "matchup_sample": 0, "matchup_note": "NO_MATCHUP_SAMPLE"}
    sample = history[history["OPPONENT"].map(normalize_token) == opponent_key]
    values = numeric(sample[column])
    overall = numeric(history[column])
    if values.empty or overall.empty:
        return {"matchup_score": 50.0, "matchup_sample": 0, "matchup_note": "NO_MATCHUP_SAMPLE"}
    delta = (float(values.mean()) - float(overall.mean())) / max(abs(float(overall.mean())), 1.0)
    shrink = min(len(values) / 10.0, 1.0)
    score = clip(50 + 30 * delta * shrink)
    return {"matchup_score": score, "matchup_sample": len(values), "matchup_note": f"HISTORICAL_OPPONENT_SAMPLE={len(values)}"}


def choose_direction(metrics: dict[str, object]) -> tuple[str, float, str]:
    over, under = float(metrics["over_score"]), float(metrics["under_score"])
    best, gap = max(over, under), abs(over - under)
    if int(metrics["sample_size"]) < 3:
        return "PASS", best, "Insufficient history"
    if best < 58 or gap < 5:
        return "PASS", best, "No clear statistical edge"
    return ("OVER", over, "Baseline history favors over") if over > under else ("UNDER", under, "Baseline history favors under")


def grade(direction: str, score: float, sample: int) -> str:
    if direction == "PASS":
        return "PASS"
    if sample < 5:
        return "B-"
    if score >= 82:
        return "B+"
    if score >= 74:
        return "B"
    if score >= 66:
        return "B-"
    return "C"


def filter_pregame(board: pd.DataFrame, history: pd.DataFrame) -> tuple[pd.DataFrame, pd.Timestamp]:
    dates = pd.to_datetime(board["slate_date"], errors="coerce").dropna().unique()
    if len(dates) != 1:
        raise ValueError("Decision board must contain exactly one valid slate_date")
    slate = pd.Timestamp(dates[0]).normalize()
    result_dates = pd.to_datetime(history["RESULT_DATE"], errors="coerce").dt.normalize()
    frame = history.loc[result_dates < slate].copy()
    frame["RESULT_DATE"] = result_dates.loc[frame.index]
    return frame, slate


def score_board(board_path: Path, history_path: Path, output_path: Path) -> int:
    board = pd.read_csv(board_path)
    history = pd.read_csv(history_path)
    required_board = {"decision_id", "slate_date", "player", "opponent", "prop_type", "line"}
    required_history = {"RESULT_DATE", "PLAYER_NAME", "PLAYER_TYPE"}
    if missing := sorted(required_board - set(board.columns)):
        raise ValueError(f"Decision board missing columns: {', '.join(missing)}")
    if missing := sorted(required_history - set(history.columns)):
        raise ValueError(f"MLB history missing columns: {', '.join(missing)}")

    history, slate = filter_pregame(board, history)
    dedup_columns = ["RESULT_DATE", "PLAYER_NAME", "PLAYER_TYPE"]
    if "GAME_ID" in history.columns and history["GAME_ID"].notna().any():
        dedup_columns.insert(1, "GAME_ID")
    history = history.drop_duplicates(dedup_columns, keep="last")
    history = history.sort_values("RESULT_DATE")
    history["_key"] = history["PLAYER_NAME"].map(normalize_name)
    board["_key"] = board["player"].map(normalize_name)
    for column in TEXT_COLUMNS:
        board[column] = board[column].astype("object")

    metric_rows: list[dict[str, object]] = []
    for index, row in board.iterrows():
        column = result_column(row["prop_type"])
        player_history = history[history["_key"] == row["_key"]]
        is_pitcher = column in PITCHER_COLUMNS if column else False
        expected_type = "PITCHER" if is_pitcher else "HITTER"
        player_history = player_history[player_history["PLAYER_TYPE"].astype(str).str.upper() == expected_type]
        opportunity = opportunity_context(player_history, is_pitcher)
        suppression = suppression_context(player_history, is_pitcher)
        matchup = matchup_context(player_history, row["opponent"], column or "")

        if column is None or column not in history.columns:
            metrics = historical_scores(pd.Series(dtype=float), float(row["line"]))
            extra_flag = "Unsupported MLB prop type; "
        else:
            metrics = historical_scores(player_history[column], float(row["line"]))
            extra_flag = ""
        direction, model_score, reason = choose_direction(metrics)
        assigned = grade(direction, model_score, int(metrics["sample_size"]))

        board.at[index, "direction"] = direction
        board.at[index, "grade"] = assigned
        board.at[index, "model_score"] = model_score
        board.at[index, "recommended"] = 0
        board.at[index, "entry_type"] = ""
        board.at[index, "opportunity_score"] = opportunity["opportunity_score"]
        board.at[index, "workload_score"] = opportunity["workload_score"]
        board.at[index, "expected_plate_appearances"] = opportunity["expected_plate_appearances"]
        board.at[index, "expected_innings"] = opportunity["expected_innings"]
        board.at[index, "expected_pitch_count"] = opportunity["expected_pitch_count"]
        board.at[index, "suppression_score"] = suppression["suppression_score"]
        board.at[index, "matchup_score"] = matchup["matchup_score"]
        board.at[index, "red_flags"] = extra_flag + BASELINE_FLAG
        board.at[index, "decision_reason"] = (
            f"BASELINE STATISTICAL ONLY - {reason}; {opportunity['opportunity_note']}; "
            f"{suppression['suppression_note']}; {matchup['matchup_note']}; cutoff {slate.date()}"
        )
        metric_rows.append({**metrics, **matchup})

    metrics_frame = pd.DataFrame(metric_rows)
    for column in metrics_frame.columns:
        if column != "matchup_score":
            board[column] = metrics_frame[column].values
    board["statistical_score"] = board["model_score"]
    board["same_player_rank"] = board.groupby("player")["model_score"].rank(method="first", ascending=False).astype("Int64")
    playable = board["direction"].isin(["OVER", "UNDER"])
    board.loc[playable, "overall_rank"] = board.loc[playable, "model_score"].rank(method="first", ascending=False).astype("Int64")
    board = board.drop(columns=["_key"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    board.to_csv(output_path, index=False)
    return len(board)


def main() -> None:
    parser = argparse.ArgumentParser(description="Score an MLB baseline decision board")
    parser.add_argument("--board", required=True, type=Path)
    parser.add_argument("--history", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = score_board(args.board, args.history, args.output)
    print("=" * 70)
    print("MLB BASELINE SCORER")
    print("=" * 70)
    print(f"Rows scored: {rows:,}")
    print(f"Saved: {args.output}")
    print("Baseline cap: B+; recommendations remain disabled.")


if __name__ == "__main__":
    main()

