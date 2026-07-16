"""One-command full-board postgame grading and daily audit export."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pandas as pd

from src.audits.run_daily_audits import run_daily_audits


ROOT=Path(__file__).resolve().parents[2]


def grade(day: str) -> dict[str, object]:
    destination=ROOT/"data"/"results"/day
    manifest=run_daily_audits(day,ROOT/"data"/"wnba"/"WNBA_RESULTS_HISTORY.csv",
                              ROOT/"data"/"mlb"/"MLB_RESULTS_HISTORY.csv",destination/"snapshots")
    reports=[]
    for run in manifest["runs"]:
        if run["slate_date"] == day and run.get("report") and Path(run["report"]).exists():
            reports.append(pd.read_csv(run["report"]))
    full=pd.concat(reports,ignore_index=True,sort=False) if reports else pd.DataFrame()
    full.to_csv(destination/"full_audit.csv",index=False)
    if not full.empty:
        selected=full[full.get("final_selection",pd.Series(index=full.index,dtype=str)).isin(["OVER","UNDER"])]
        same_player=full.sort_values([c for c in ["player","prop_type"] if c in full]).copy()
        misses=full[full.get("status",pd.Series(index=full.index,dtype=str)).eq("MISS")]
    else: selected=same_player=misses=full
    selected.to_csv(destination/"selection_audit.csv",index=False)
    same_player.to_csv(destination/"same_player_comparison.csv",index=False)
    misses.to_csv(destination/"miss_reasons.csv",index=False)
    summary={"slate_date":day,"rows":len(full),"status_counts":full.get("status",pd.Series(dtype=str)).value_counts().to_dict(),
             "recommendations_enabled":False,"model_weights_changed":False}
    (destination/"daily_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    latest=ROOT/"reports"/"latest"; latest.mkdir(parents=True,exist_ok=True)
    shutil.copy2(destination/"full_audit.csv",latest/"full_audit.csv")
    (latest/"audit_report.md").write_text(f"# Latest audit\n\nSlate: {day}\n\nRows graded: {len(full)}\n",encoding="utf-8")
    return summary


def main() -> None:
    parser=argparse.ArgumentParser(description="Grade every candidate on a completed Sports Hub slate")
    parser.add_argument("--date",required=True); args=parser.parse_args()
    print(json.dumps(grade(args.date),indent=2))


if __name__ == "__main__": main()
