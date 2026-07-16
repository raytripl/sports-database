"""Single staged controller for the complete guarded Sports Hub daily run."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src.automation.prizepicks_hourly import acquire_pool, configure_runtime_directories
from src.imports import process_pool
from src.imports.capture_matchup_foundation import capture_all_prop_lines
from src.imports.fetch_mlb_live_context import fetch_to_csv
from src.imports.wnba_official_injuries import capture_latest as capture_wnba_injuries
from src.imports.wnba_lineups import capture_rotowire_lineups, merge_availability
from src.context.build_wnba_opportunity import build_projections as build_wnba_opportunity_projections
from src.context.opportunity_store import (
    create_run as create_opportunity_run,
    insert_frame as insert_opportunity_frame,
    update_run_row_count as update_opportunity_run_row_count,
)
from src.pipelines.mlb_daily import run_pipeline as run_mlb
from src.pipelines.wnba_daily import run_pipeline as run_wnba
from src.decisions.build_research_rankings import build_rankings
from src.decisions.build_research_board import build_research_board
from src.decisions.build_research_slip import build_slip
from src.workflows.pregame_snapshot import build_snapshot, freeze_snapshot
from src.workflows.research_decision_pipeline import run_research_decision_pipeline


ROOT=Path(__file__).resolve().parents[2]
CENTRAL=ZoneInfo("America/Chicago")
MODEL_RUNS=ROOT/"data"/"model_runs"
REGISTRY=ROOT/"data"/"model_registry"/"models.json"
POOL_MAX_AGE_HOURS=float(os.environ.get("SPORTS_HUB_POOL_MAX_AGE_HOURS", "12"))


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def validate_environment() -> dict[str, object]:
    required=[ROOT/"data"/"mlb"/"MLB_RESULTS_HISTORY.csv", ROOT/"data"/"wnba"/"WNBA_RESULTS_HISTORY.csv", REGISTRY]
    missing=[str(path) for path in required if not path.exists()]
    if missing: raise FileNotFoundError("Missing Sports Hub prerequisites: " + ", ".join(missing))
    registry=json.loads(REGISTRY.read_text(encoding="utf-8"))
    control=registry.get("production_control", {})
    if control.get("status") != "CONTROL" or not control.get("enabled"):
        raise RuntimeError("Model registry has no enabled CONTROL model")
    return {"status":"OK","production_control":control.get("name"),"missing":[]}


def update_data(sport: str) -> dict[str, object]:
    selected = "all" if sport == "all" else sport
    command = [
        str(ROOT / ".venv" / "Scripts" / "python.exe"),
        str(ROOT / "update_all.py"),
        "--sport",
        selected,
    ]

    print(
        f"[SPORTS HUB] Starting data update for: {selected}",
        flush=True,
    )

    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            check=False,
            timeout=5400,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "FAILED",
            "exit_code": None,
            "reason": "UPDATE_TIMEOUT_AFTER_90_MINUTES",
            "sport": selected,
        }

    return {
        "status": (
            "COMPLETE"
            if completed.returncode == 0
            else "FAILED"
        ),
        "exit_code": completed.returncode,
        "sport": selected,
    }


def import_pool(day: str, live: Path) -> dict[str, object]:
    configure_runtime_directories()
    raw, downloaded, rows, mode, error=acquire_pool()
    outputs=process_pool.process_pool(downloaded)
    normalized=outputs[1]
    live.mkdir(parents=True,exist_ok=True)

    raw_target=live/"raw_pool.csv"
    normalized_target=live/"standardized_pool.csv"

    shutil.copy2(raw,raw_target)
    shutil.copy2(normalized,normalized_target)

    now=datetime.now(CENTRAL)
    modified=datetime.fromtimestamp(
        raw_target.stat().st_mtime,
        tz=CENTRAL,
    )
    age_hours=max(
        0.0,
        (now-modified).total_seconds()/3600.0,
    )

    mode_text=str(mode or "").strip().upper()

    if not raw_target.exists() or rows <= 0:
        pool_status="NO_POOL"
        eligible=False
        reason="NO_USABLE_POOL_ROWS"
    elif age_hours > POOL_MAX_AGE_HOURS:
        pool_status="STALE_FALLBACK"
        eligible=False
        reason=(
            f"POOL_AGE_{age_hours:.2f}_HOURS_EXCEEDS_"
            f"{POOL_MAX_AGE_HOURS:.2f}"
        )
    elif "MANUAL" in mode_text or error:
        pool_status="MANUAL_FALLBACK"
        eligible=True
        reason=(
            "MANUAL_EXPORT_FALLBACK"
            if not error
            else f"API_FALLBACK: {error}"
        )
    else:
        pool_status="LIVE"
        eligible=True
        reason="CURRENT_LIVE_POOL"

    pool_manifest={
        "workflow_date":day,
        "status":pool_status,
        "eligible_for_scoring":eligible,
        "reason":reason,
        "source_filename":raw_target.name,
        "source_path":str(raw_target),
        "normalized_path":str(normalized_target),
        "capture_timestamp":now.isoformat(),
        "file_modified_timestamp":modified.isoformat(),
        "pool_age_hours":round(age_hours,4),
        "maximum_age_hours":POOL_MAX_AGE_HOURS,
        "row_count":int(rows),
        "source_type":mode_text or "UNKNOWN",
        "acquisition_error":error,
        "research_only":False,
    }
    _write_json(live/"pool_manifest.json",pool_manifest)

    if not eligible:
        return {
            "status":"BLOCKED",
            "acquisition_mode":mode,
            "acquisition_error":error,
            "source_rows":rows,
            "normalized_path":str(normalized_target),
            "pool_manifest":str(live/"pool_manifest.json"),
            "pool_status":pool_status,
            "eligible_for_scoring":False,
            "reason":reason,
        }

    tracked=capture_all_prop_lines(
        normalized,
        f"daily-{day}-{now.strftime('%H%M%S')}",
    )

    return {
        "status":"COMPLETE",
        "acquisition_mode":mode,
        "acquisition_error":error,
        "source_rows":rows,
        "normalized_path":str(normalized_target),
        "line_tracker":tracked,
        "pool_manifest":str(live/"pool_manifest.json"),
        "pool_status":pool_status,
        "eligible_for_scoring":True,
    }


def capture_context(day: str, live: Path, sport: str) -> dict[str, object]:
    result={
        "status": "COMPLETE",
        "mlb_context_rows": 0,
        "wnba_availability_rows": 0,
        "wnba_opportunity_rows": 0,
        "wnba_opportunity_status": "NOT_RUN",
        "errors": [],
    }
    if sport in {"all","mlb"}:
        context=live/"mlb_context.csv"
        try: result["mlb_context_rows"]=fetch_to_csv(day,context)
        except Exception as error: result["errors"].append(f"MLB: {type(error).__name__}: {error}")
        if context.exists():
            frame=pd.read_csv(context)
            pitchers=frame[frame.player_role.eq("PITCHER")].to_dict("records")
            _write_json(live/"expected_starters.json",pitchers)
            _write_json(live/"weather.json",frame[[c for c in ["game_id","venue","weather_condition","temperature","wind"] if c in frame]].drop_duplicates().to_dict("records"))
    if sport in {"all","wnba"}:
        try:
            injuries=capture_wnba_injuries()
            injury_path=Path(str(injuries["csv_path"])); injury_rows=pd.read_csv(injury_path)
            lineups=capture_rotowire_lineups(day)
            lineup_path=Path(str(lineups["csv_path"])); lineup_rows=pd.read_csv(lineup_path)
            availability_path = live / "wnba_availability.csv"

            merge_availability(
                injury_path,
                lineup_path,
            ).to_csv(
                availability_path,
                index=False,
            )

            _write_json(
                live / "lineups.json",
                lineup_rows.to_dict("records"),
            )

            _write_json(
                live / "injuries.json",
                injury_rows.to_dict("records"),
            )

            result["wnba_availability_rows"] = len(
                pd.read_csv(
                    availability_path,
                    low_memory=False,
                )
            )

            try:
                opportunity_output = (
                    live
                    / "wnba_opportunity_projection.csv"
                )

                opportunity_database = (
                    ROOT
                    / "data"
                    / "sports_hub.db"
                )

                opportunity_history = (
                    ROOT
                    / "data"
                    / "wnba"
                    / "WNBA_RESULTS_HISTORY.csv"
                )

                opportunity_frame = (
                    build_wnba_opportunity_projections(
                        slate_date=day,
                        history_path=opportunity_history,
                        availability_path=availability_path,
                    )
                )

                opportunity_frame.to_csv(
                    opportunity_output,
                    index=False,
                )

                opportunity_run_id = (
                    f"wnba-opportunity-{day}-"
                    f"{datetime.now(CENTRAL).strftime('%H%M%S')}"
                )

                create_opportunity_run(
                    run_id=opportunity_run_id,
                    slate_date=day,
                    sport="WNBA",
                    source_summary={
                        "history": str(
                            opportunity_history
                        ),
                        "availability": str(
                            availability_path
                        ),
                        "output": str(
                            opportunity_output
                        ),
                        "workflow": (
                            "daily_sports_hub_context"
                        ),
                        "version": (
                            "WNBA_OPPORTUNITY_V2"
                        ),
                    },
                    database=opportunity_database,
                )

                database_frame = (
                    opportunity_frame.copy()
                )

                database_frame.insert(
                    0,
                    "run_id",
                    opportunity_run_id,
                )

                inserted_rows = (
                    insert_opportunity_frame(
                        "basketball_opportunity",
                        database_frame,
                        opportunity_database,
                    )
                )

                update_opportunity_run_row_count(
                    opportunity_run_id,
                    inserted_rows,
                    opportunity_database,
                )

                result[
                    "wnba_opportunity_rows"
                ] = int(
                    len(opportunity_frame)
                )

                result[
                    "wnba_opportunity_stored_rows"
                ] = int(inserted_rows)

                result[
                    "wnba_opportunity_status"
                ] = "COMPLETE"

                result[
                    "wnba_opportunity_path"
                ] = str(opportunity_output)

                result[
                    "wnba_opportunity_run_id"
                ] = opportunity_run_id

            except Exception as opportunity_error:
                result[
                    "wnba_opportunity_status"
                ] = "FAILED_RESEARCH_ONLY"

                result["errors"].append(
                    "WNBA_OPPORTUNITY: "
                    f"{type(opportunity_error).__name__}: "
                    f"{opportunity_error}"
                )
        except Exception as error:
            result["errors"].append(f"WNBA: {type(error).__name__}: {error}")
    if result["errors"]: result["status"]="PARTIAL"
    return result


def score(day: str, live: Path, sport: str) -> dict[str, object]:
    pool=live/"standardized_pool.csv"
    if not pool.exists():
        raise FileNotFoundError(f"Run pool stage first: {pool}")

    pool_manifest_path=live/"pool_manifest.json"

    if pool_manifest_path.exists():
        pool_manifest=json.loads(
            pool_manifest_path.read_text(encoding="utf-8")
        )

        if not pool_manifest.get("eligible_for_scoring",False):
            raise RuntimeError(
                "Pool is not eligible for scoring: "
                f"{pool_manifest.get('status')} - "
                f"{pool_manifest.get('reason')}"
            )
    frame=pd.read_csv(pool); runs=[]
    for selected, history, runner in (
        ("WNBA",ROOT/"data"/"wnba"/"WNBA_RESULTS_HISTORY.csv",run_wnba),
        ("MLB",ROOT/"data"/"mlb"/"MLB_RESULTS_HISTORY.csv",run_mlb),
    ):
        if sport not in {"all",selected.lower()} or not ((frame.league.astype(str).str.upper()==selected)&(frame.slate_date.astype(str)==day)).any(): continue
        kwargs={}
        if selected == "MLB" and (live/"mlb_context.csv").exists(): kwargs["live_context_path"]=live/"mlb_context.csv"
        if selected == "WNBA" and (live/"wnba_availability.csv").exists(): kwargs["availability_path"]=live/"wnba_availability.csv"
        runs.append(runner(pool,day,history,MODEL_RUNS,**kwargs))
    scored=[]
    for run in runs:
        source=Path(run["scored_path"])
        if source.exists():
            target=live/f"{run['pipeline'].split('_')[0].lower()}_scored_board.csv"; shutil.copy2(source,target); scored.append(target)
    research_outputs = []

    if scored:
        pd.concat(
            [pd.read_csv(path) for path in scored],
            ignore_index=True,
            sort=False,
        ).to_csv(live/"scored_board.csv", index=False)

    wnba_scored = live/"wnba_scored_board.csv"

    if wnba_scored.exists():
        rankings = live/"wnba_research_rankings.csv"
        research_board = live/"wnba_research_board.csv"
        research_slip = live/"wnba_research_slip.csv"

        build_rankings(wnba_scored, rankings)
        build_research_board(rankings, research_board)
        candidate_rows, selected_rows = build_slip(
            research_board,
            research_slip,
        )

        research_outputs.append({
            "sport": "WNBA",
            "rankings_path": str(rankings),
            "research_board_path": str(research_board),
            "research_slip_path": str(research_slip),
            "candidate_rows": candidate_rows,
            "selected_rows": selected_rows,
            "label": "RESEARCH_ONLY",
            "production_approved": False,
        })

        try:
            decision_pipeline = run_research_decision_pipeline(
                slate_date=day,
                scored_board=wnba_scored,
                live_directory=live,
                root=ROOT,
            )
        except Exception as error:
            decision_pipeline = {
                "overall_status": "FAILED",
                "research_only": True,
                "production_unchanged": True,
                "error_messages": [
                    f"{type(error).__name__}: {error}"
                ],
            }

        research_outputs.append({
            "sport": "WNBA",
            "pipeline": "WNBA_RESEARCH_DECISION_PIPELINE",
            "manifest_path": str(
                live / "wnba_research_pipeline_manifest.json"
            ),
            "overall_status": decision_pipeline.get(
                "overall_status"
            ),
            "research_only": True,
            "production_approved": False,
        })

    return {
        "status": "COMPLETE",
        "runs": runs,
        "scored_boards": [str(path) for path in scored],
        "research_outputs": research_outputs,
    }


def _public_board(frame: pd.DataFrame) -> pd.DataFrame:
    output=frame.copy()
    selection=output.get("final_selection",pd.Series("NO PICK",index=output.index)).fillna("NO PICK").astype(str).str.upper()
    output["public_selection"]=selection.where(selection.isin({"OVER","UNDER"}),"NO PICK")
    output["data_quality_status"]=output.get("eligibility_status",pd.Series("MISSING",index=output.index)).fillna("MISSING")
    columns=["sport","player","team","opponent","prop_type","line","direction","public_selection","pick_level","final_rank",
             "hierarchy_probability","hierarchy_prop_wilson","candidate_action","decision_flow","eligibility_status","exclusion_reason",
             "data_quality_status","correlation_cluster","final_model_version"]
    return output[[column for column in columns if column in output]]


def report(day: str, live: Path) -> dict[str, object]:
    scored=live/"scored_board.csv"
    if not scored.exists(): raise FileNotFoundError(f"Run score stage first: {scored}")
    raw=pd.read_csv(scored); final=_public_board(raw)
    final.to_csv(live/"final_board.csv",index=False)
    primary=final[final.get("pick_level",pd.Series(index=final.index,dtype=str)).eq("PRIMARY")]
    secondary=final[final.get("pick_level",pd.Series(index=final.index,dtype=str)).eq("SECONDARY")]
    primary.to_csv(live/"primary_picks.csv",index=False); secondary.to_csv(live/"secondary_picks.csv",index=False)
    pool=pd.read_csv(live/"standardized_pool.csv")
    context=pd.read_csv(live/"mlb_context.csv") if (live/"mlb_context.csv").exists() else None
    records=build_snapshot(pool,context,"v22-control",ROOT)
    if (live/"wnba_availability.csv").exists():
        availability=pd.read_csv(live/"wnba_availability.csv")
        lookup={str(row.get("player","")).lower():row for row in availability.to_dict("records")}
        for record in records:
            if record["sport"] != "WNBA": continue
            available=lookup.get(str(record["player"]).lower())
            if not available: record["data_quality_status"]="MISSING"; continue
            record["injury_status"]=available.get("injury_status")
            record["projected_minutes"]=available.get("expected_minutes")
            record["projection_source"]=available.get("source")
            confirmed=available.get("lineup_confirmed") in (1,True,"1","1.0")
            record["lineup_status"]="CONFIRMED" if confirmed else "EXPECTED"
            record["data_quality_status"]="COMPLETE" if confirmed else "PARTIAL"
    snapshot=live/"pregame_snapshot.json"
    snapshot_state="EXISTING_IMMUTABLE"
    if not snapshot.exists(): freeze_snapshot(snapshot,records); snapshot_state="FROZEN"
    quality=pd.DataFrame(records)
    quality.to_csv(live/"data_quality.csv",index=False)
    html="<h1>Sports Hub Daily Report</h1>"+final.to_html(index=False)
    (live/"report.html").write_text(html,encoding="utf-8")
    latest=ROOT/"reports"/"latest"; latest.mkdir(parents=True,exist_ok=True)
    for name in ("final_board.csv","primary_picks.csv","secondary_picks.csv","data_quality.csv","report.html"):
        shutil.copy2(live/name,latest/name)
    status={"slate_date":day,"completed_at":datetime.now(CENTRAL).isoformat(),"final_rows":len(final),
            "primary_rows":len(primary),"secondary_rows":len(secondary),"snapshot_state":snapshot_state,
            "production_model":"v22-control","recommendations_enabled":False}
    _write_json(latest/"status.json",status)
    (latest/"model_report.md").write_text("# Sports Hub latest\n\nProduction control: v22. Shadow models are not promoted automatically.\n",encoding="utf-8")
    return status


def run(day: str, stage: str, sport: str) -> dict[str, object]:
    live=ROOT/"data"/"live"/day; live.mkdir(parents=True,exist_ok=True)
    manifest={"slate_date":day,"stage":stage,"sport":sport,"started_at":datetime.now(CENTRAL).isoformat(),"stages":{}}
    manifest["stages"]["validate"]=validate_environment()
    requested=[stage] if stage != "all" else ["update","pool","context","score","report"]
    for item in requested:
        if item == "update": manifest["stages"][item]=update_data(sport)
        elif item == "pool": manifest["stages"][item]=import_pool(day,live)
        elif item == "context": manifest["stages"][item]=capture_context(day,live,sport)
        elif item == "score": manifest["stages"][item]=score(day,live,sport)
        elif item == "report": manifest["stages"][item]=report(day,live)
    manifest["completed_at"]=datetime.now(CENTRAL).isoformat(); _write_json(live/"daily_manifest.json",manifest)
    return manifest


def main() -> None:
    parser=argparse.ArgumentParser(description="Run the unified Sports Hub daily workflow")
    parser.add_argument("--date",default=datetime.now(CENTRAL).strftime("%Y-%m-%d"))
    parser.add_argument("--stage",choices=["all","update","pool","context","score","report"],default="all")
    parser.add_argument("--sport",choices=["all","mlb","wnba"],default="all")
    args=parser.parse_args(); print(json.dumps(run(args.date,args.stage,args.sport),indent=2,default=str))


if __name__ == "__main__": main()
