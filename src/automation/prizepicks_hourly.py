from __future__ import annotations

import argparse
import json
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src.imports import prizepicks, process_pool
from src.imports.fetch_mlb_live_context import fetch_to_csv
from src.pipelines.mlb_daily import run_pipeline as run_mlb_pipeline
from src.pipelines.wnba_daily import run_pipeline as run_wnba_pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = PROJECT_ROOT / "data" / "runtime" / "prizepicks"
MODEL_RUNS = PROJECT_ROOT / "data" / "model_runs"
WNBA_HISTORY = PROJECT_ROOT / "data" / "wnba" / "WNBA_RESULTS_HISTORY.csv"
MLB_HISTORY = PROJECT_ROOT / "data" / "mlb" / "MLB_RESULTS_HISTORY.csv"
LOCK_PATH = RUNTIME_ROOT / "hourly_capture.lock"
CENTRAL = ZoneInfo("America/Chicago")
REQUIRED_EXPORT_COLUMNS = {
    "projection_id", "league", "player_name", "stat_type", "line_score",
}


@contextmanager
def single_run_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        try:
            existing_pid = int(path.read_text(encoding="ascii").strip())
            os.kill(existing_pid, 0)
        except (OSError, ValueError):
            path.unlink(missing_ok=True)
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        else:
            raise RuntimeError(
                f"Another PrizePicks capture is already running (PID {existing_pid})"
            ) from error
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.close(descriptor)
        yield
    finally:
        path.unlink(missing_ok=True)


def eligible_sport_dates(frame: pd.DataFrame, sport: str, now: datetime) -> list[str]:
    if "league" not in frame.columns or "slate_date" not in frame.columns:
        return []
    rows = frame[frame["league"].astype(str).str.upper() == sport.upper()]
    today = now.astimezone(CENTRAL).date()
    tomorrow = today + timedelta(days=1)
    available = set(rows["slate_date"].dropna().astype(str))
    return [str(day) for day in (today, tomorrow) if str(day) in available]


def eligible_wnba_dates(frame: pd.DataFrame, now: datetime) -> list[str]:
    return eligible_sport_dates(frame, "WNBA", now)


def eligible_mlb_dates(frame: pd.DataFrame, now: datetime) -> list[str]:
    return eligible_sport_dates(frame, "MLB", now)


def configure_runtime_directories() -> None:
    prizepicks.RAW_DIRECTORY = RUNTIME_ROOT / "raw"
    prizepicks.PROCESSED_DIRECTORY = RUNTIME_ROOT / "downloads"
    process_pool.PROCESSED_DIR = RUNTIME_ROOT / "normalized"
    process_pool.ARCHIVE_DIR = RUNTIME_ROOT / "archive"


def valid_export(path: Path) -> bool:
    try:
        columns = {str(column).strip().lower() for column in pd.read_csv(path, nrows=0).columns}
        return REQUIRED_EXPORT_COLUMNS.issubset(columns)
    except (OSError, ValueError, pd.errors.ParserError):
        return False


def find_latest_export(search_directories: list[Path] | None = None) -> Path | None:
    directories = search_directories or [
        Path.home() / "Downloads",
        PROJECT_ROOT / "data" / "pools" / "incoming",
    ]
    candidates: list[Path] = []
    for directory in directories:
        if directory.exists():
            candidates.extend(path for path in directory.glob("*.csv") if path.is_file())
    for path in sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True):
        if valid_export(path):
            return path
    return None


def acquire_pool() -> tuple[Path, Path, int, str, str | None]:
    try:
        payload = prizepicks.download_prizepicks_payload(timeout=30, retries=3)
        raw_path, csv_path, rows = prizepicks.save_pool(payload)
        return raw_path, csv_path, rows, "DIRECT_API", None
    except Exception as error:
        fallback = find_latest_export()
        if fallback is None:
            raise RuntimeError(
                f"Direct PrizePicks capture failed and no valid manual export exists: {error}"
            ) from error
        rows = len(pd.read_csv(fallback))
        return fallback, fallback, rows, "MANUAL_EXPORT_FALLBACK", f"{type(error).__name__}: {error}"


def run_mlb_with_context(normalized_path: Path, slate_date: str) -> dict[str, object]:
    context_path = RUNTIME_ROOT / "mlb_live" / f"mlb_live_context_{slate_date}.csv"
    context_error = None
    try:
        fetch_to_csv(slate_date, context_path)
    except Exception as error:
        context_path = None
        context_error = f"{type(error).__name__}: {error}"
    return run_mlb_pipeline(
        normalized_path, slate_date, MLB_HISTORY, MODEL_RUNS,
        live_context_path=context_path, live_context_error=context_error,
    )


def run_hourly_capture(now: datetime | None = None) -> dict[str, object]:
    current = now or datetime.now(tz=CENTRAL)
    configure_runtime_directories()
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    with single_run_lock(LOCK_PATH):
        raw_path, downloaded_csv, all_sport_rows, mode, direct_error = acquire_pool()
        (_, normalized_path, _, _, normalized, _) = process_pool.process_pool(downloaded_csv)
        wnba_dates = eligible_wnba_dates(normalized, current)
        mlb_dates = eligible_mlb_dates(normalized, current)
        wnba_runs = [run_wnba_pipeline(normalized_path, day, WNBA_HISTORY, MODEL_RUNS) for day in wnba_dates]
        mlb_runs = [run_mlb_with_context(normalized_path, day) for day in mlb_dates]
        manifest = {
            "captured_at": current.astimezone(CENTRAL).isoformat(),
            "acquisition_mode": mode, "direct_api_error": direct_error,
            "raw_path": str(raw_path), "downloaded_csv": str(downloaded_csv),
            "normalized_path": str(normalized_path), "all_sport_rows": all_sport_rows,
            "normalized_rows": len(normalized),
            "normalized_mlb_wnba_rows": int(
                normalized["league"].astype(str).str.upper().isin({"MLB", "WNBA"}).sum()
            ),
            "leagues": normalized["league"].value_counts().to_dict(),
            "model_status_counts": normalized["model_status"].value_counts().to_dict(),
            "unsupported_sports": sorted(
                normalized.loc[
                    normalized["model_status"].eq("UNSUPPORTED_PASS"), "league"
                ].dropna().astype(str).unique().tolist()
            ),
            "wnba_dates_routed": wnba_dates, "wnba_runs": wnba_runs,
            "mlb_dates_routed": mlb_dates, "mlb_runs": mlb_runs,
            "recommendations_enabled": False,
        }
        manifest_path = RUNTIME_ROOT / "latest_capture_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Hourly all-sport PrizePicks capture")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print("Dry-run validates imports only; no network request was made.")
        return
    result = run_hourly_capture()
    print(f"Acquisition mode: {result['acquisition_mode']}")
    print(f"All-sport rows: {result['all_sport_rows']:,}")
    print(f"WNBA dates routed: {result['wnba_dates_routed']}")
    print(f"MLB dates routed: {result['mlb_dates_routed']}")
    print("Recommendations remain disabled.")


if __name__ == "__main__":
    main()
