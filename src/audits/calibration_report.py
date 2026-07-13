from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.db import connect
from src.decisions.schema import initialize_schema


GRADE_ORDER = ["A+", "A", "A-", "B+", "B", "B-", "C", "PASS", "UNSET"]
RESOLVED_STATUSES = {"HIT", "MISS", "PUSH"}
OPPORTUNITY_TOKENS = {
    "WNBA": {
        "assists", "rebounds", "offensiverebounds", "defensiverebounds",
        "fgattempts", "fieldgoalattempts", "3ptattempted", "3pointattempts",
        "2ptattempts", "twopointattempts",
    },
    "MLB": {"totalpitches", "pitchingouts"},
}


def normalize_token(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def opportunity_class(sport: object, prop_type: object) -> str:
    sport_key = str(sport).upper()
    return "OPPORTUNITY" if normalize_token(prop_type) in OPPORTUNITY_TOKENS.get(sport_key, set()) else "RESULT"


def load_decisions() -> pd.DataFrame:
    initialize_schema()
    with connect() as connection:
        return pd.read_sql_query(
            """
            SELECT d.decision_id, d.snapshot_id, d.slate_date, UPPER(d.sport) AS sport,
                   d.created_at, d.game_id, d.player, d.team, d.opponent,
                   d.prop_type, d.line, UPPER(d.direction) AS direction,
                   COALESCE(d.grade, 'UNSET') AS grade, d.model_score,
                   d.opportunity_score, d.suppression_score, d.matchup_score,
                   d.recommended, COALESCE(r.status, 'PENDING') AS status,
                   r.actual_value, r.margin, r.minutes, r.plate_appearances,
                   r.innings, r.pitch_count, r.opportunity_received,
                   r.process_quality, r.error_classification
            FROM model_decisions d
            LEFT JOIN prop_results r ON r.decision_id=d.decision_id
            WHERE UPPER(d.sport) IN ('WNBA', 'MLB')
            """,
            connection,
        )


def closing_decisions(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    result = frame.copy()
    result["created_at"] = pd.to_datetime(result["created_at"], errors="coerce", utc=True)
    result = result.sort_values(["created_at", "decision_id"], na_position="first")
    # One closing decision per player/game/market. Line is intentionally omitted:
    # repeated hourly captures and line moves must not inflate calibration samples.
    keys = ["slate_date", "sport", "game_id", "player", "opponent", "prop_type"]
    for column in keys:
        result[column] = result[column].fillna("").astype(str)
    result = result.drop_duplicates(keys, keep="last").copy()
    result["opportunity_class"] = [
        opportunity_class(sport, prop)
        for sport, prop in zip(result["sport"], result["prop_type"])
    ]
    result["score_band"] = pd.cut(
        pd.to_numeric(result["model_score"], errors="coerce"),
        bins=[-0.001, 59.999, 69.999, 79.999, 89.999, 100.0],
        labels=["0-59", "60-69", "70-79", "80-89", "90-100"],
        include_lowest=True,
    ).astype("object").fillna("UNSCORED")
    return result


def grouped_performance(frame: pd.DataFrame, groups: list[str]) -> pd.DataFrame:
    columns = groups + [
        "total_decisions", "directional_decisions", "resolved_directional",
        "hits", "misses", "pushes", "pending", "unsupported", "passes",
        "hit_rate", "average_margin",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, object]] = []
    grouper: object = groups[0] if len(groups) == 1 else groups
    for key, sample in frame.groupby(grouper, dropna=False, sort=False):
        values = (key,) if len(groups) == 1 else tuple(key)
        directional = sample[sample["direction"].isin(["OVER", "UNDER"])]
        resolved = directional[directional["status"].isin(RESOLVED_STATUSES)]
        wins = int((resolved["status"] == "HIT").sum())
        losses = int((resolved["status"] == "MISS").sum())
        denominator = wins + losses
        margins = pd.to_numeric(resolved["margin"], errors="coerce").dropna()
        row = dict(zip(groups, values))
        row.update({
            "total_decisions": len(sample),
            "directional_decisions": len(directional),
            "resolved_directional": len(resolved),
            "hits": wins,
            "misses": losses,
            "pushes": int((resolved["status"] == "PUSH").sum()),
            "pending": int((sample["status"] == "PENDING").sum()),
            "unsupported": int((sample["status"] == "UNSUPPORTED").sum()),
            "passes": int((sample["direction"] == "PASS").sum()),
            "hit_rate": round(wins / denominator, 4) if denominator else None,
            "average_margin": round(float(margins.mean()), 3) if not margins.empty else None,
        })
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def grade_ordering_status(by_grade: pd.DataFrame, minimum_per_grade: int = 20) -> dict[str, object]:
    if by_grade.empty:
        return {"status": "INSUFFICIENT_DATA", "eligible_grades": [], "violations": []}
    sample = by_grade.copy()
    sample = sample[(sample["resolved_directional"] >= minimum_per_grade) & sample["hit_rate"].notna()]
    sample["grade_rank"] = sample["grade"].map({grade: index for index, grade in enumerate(GRADE_ORDER)})
    sample = sample.dropna(subset=["grade_rank"]).sort_values("grade_rank")
    if len(sample) < 2:
        return {"status": "INSUFFICIENT_DATA", "eligible_grades": sample["grade"].tolist(), "violations": []}
    violations: list[str] = []
    records = sample[["grade", "hit_rate"]].to_dict("records")
    for stronger, weaker in zip(records, records[1:]):
        if float(stronger["hit_rate"]) < float(weaker["hit_rate"]):
            violations.append(
                f"{stronger['grade']} ({stronger['hit_rate']:.3f}) below {weaker['grade']} ({weaker['hit_rate']:.3f})"
            )
    return {
        "status": "ORDERED" if not violations else "NOT_ORDERED",
        "eligible_grades": sample["grade"].tolist(),
        "violations": violations,
    }


def calibration_gates(frame: pd.DataFrame, by_grade: pd.DataFrame) -> dict[str, object]:
    directional = frame[frame["direction"].isin(["OVER", "UNDER"])]
    resolved = directional[directional["status"].isin(RESOLVED_STATUSES)]
    slate_count = int(resolved[["slate_date", "sport"]].drop_duplicates().shape[0])
    pending_rate = round(float((directional["status"] == "PENDING").mean()), 4) if len(directional) else 1.0
    ordering = grade_ordering_status(by_grade)
    checks = {
        "at_least_3_completed_sport_slates": slate_count >= 3,
        "at_least_100_resolved_directional_props": len(resolved) >= 100,
        "pending_rate_at_most_5_percent": pending_rate <= 0.05,
        "at_least_2_supported_grade_tiers": len(ordering["eligible_grades"]) >= 2,
        "grade_ordering_validated": ordering["status"] == "ORDERED",
    }
    return {
        "status": "READY_FOR_HUMAN_REVIEW" if all(checks.values()) else "INSUFFICIENT_EVIDENCE",
        "checks": checks,
        "completed_sport_slates": slate_count,
        "resolved_directional_props": len(resolved),
        "pending_rate": pending_rate,
        "grade_ordering": ordering,
        "recommendations_enabled": False,
        "weights_changed": False,
    }


def generate_report(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_frame = load_decisions()
    frame = closing_decisions(raw_frame)
    reports = {
        "by_grade": grouped_performance(frame, ["grade"]),
        "by_sport": grouped_performance(frame, ["sport"]),
        "by_prop_type": grouped_performance(frame, ["sport", "prop_type"]),
        "by_direction": grouped_performance(frame, ["sport", "direction"]),
        "by_opportunity_class": grouped_performance(frame, ["sport", "opportunity_class"]),
        "by_score_band": grouped_performance(frame, ["sport", "score_band"]),
        "by_slate": grouped_performance(frame, ["slate_date", "sport"]),
    }
    paths: dict[str, str] = {}
    for name, report in reports.items():
        path = output_dir / f"{name}.csv"
        report.to_csv(path, index=False)
        paths[name] = str(path)
    closing_path = output_dir / "closing_decisions.csv"
    frame.to_csv(closing_path, index=False)
    paths["closing_decisions"] = str(closing_path)
    gates = calibration_gates(frame, reports["by_grade"])
    manifest = {
        "pipeline": "SPORTS_HUB_MULTI_SLATE_CALIBRATION",
        "model_version": "v17.3",
        "operating_revision": "Evidence-Enforced Revision B",
        "generated_at": datetime.now().astimezone().isoformat(),
        "raw_decisions": int(len(raw_frame)),
        "deduplicated_closing_decisions": int(len(frame)),
        "gates": gates,
        "reports": paths,
        "recommendations_enabled": False,
        "model_weights_changed": False,
    }
    manifest_path = output_dir / "latest_calibration_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate guarded multi-slate calibration reports")
    parser.add_argument("--output-dir", type=Path, default=Path("data/calibration"))
    args = parser.parse_args()
    manifest = generate_report(args.output_dir)
    gates = manifest["gates"]
    print("=" * 70)
    print("SPORTS HUB MULTI-SLATE CALIBRATION")
    print("=" * 70)
    print(f"Closing decisions: {manifest['deduplicated_closing_decisions']:,}")
    print(f"Resolved directional props: {gates['resolved_directional_props']:,}")
    print(f"Completed sport-slates: {gates['completed_sport_slates']:,}")
    print(f"Status: {gates['status']}")
    print(f"Manifest: {manifest['manifest_path']}")
    print("Recommendations remain disabled; v17.3 weights are unchanged.")


if __name__ == "__main__":
    main()
