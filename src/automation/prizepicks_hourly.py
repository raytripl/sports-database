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
from src.pipelines.mlb_daily import run_pipeline as run_mlb_pipeline
from src.pipelines.wnba_daily import run_pipeline as run_wnba_pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = PROJECT_ROOT / "data" / "runtime" / "prizepicks"
MODEL_RUNS = PROJECT_ROOT / "data" / "model_runs"
WNBA_HISTORY = PROJECT_ROOT / "data" / "wnba" / "WNBA_RESULTS_HISTORY.csv"
MLB_HISTORY = PROJECT_ROOT / "data" / "mlb" / "MLB_RESULTS_HISTORY.csv"
LOCK_PATH = RUNTIME_ROOT / "hourly_capture.lock"
CENTRAL = ZoneInfo("America/Chicago")


@contextmanager
def single_run_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise RuntimeError("Another PrizePicks capture is already running") from error
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


def run_hourly_capture(now: datetime | None = None) -> dict[str, object]:
    current = now or datetime.now(tz=CENTRAL)
    configure_runtime_directories()
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)

    with single_run_lock(LOCK_PATH):
        payload = prizepicks.download_prizepicks_payload(timeout=30, retries=3)
        raw_path, downloaded_csv, all_sport_rows = prizepicks.save_pool(payload)
        (
            _processed_file,
            normalized_path,
            _standard_file,
            _standard_latest,
            normalized,
            _standard,
        ) = process_pool.process_pool(downloaded_csv)

        wnba_dates = eligible_wnba_dates(normalized, current)
        mlb_dates = eligible_mlb_dates(normalized, current)
        wnba_runs = [
            run_wnba_pipeline(normalized_path, slate, WNBA_HISTORY, MODEL_RUNS)
            for slate in wnba_dates
        ]
        mlb_runs = [
            run_mlb_pipeline(normalized_path, slate, MLB_HISTORY, MODEL_RUNS)
            for slate in mlb_dates
        ]

        manifest = {
            "captured_at": current.astimezone(CENTRAL).isoformat(),
            "raw_path": str(raw_path),
            "downloaded_csv": str(downloaded_csv),
            "normalized_path": str(normalized_path),
            "all_sport_rows": all_sport_rows,
            "normalized_mlb_wnba_rows": len(normalized),
            "leagues": normalized["league"].value_counts().to_dict(),
            "wnba_dates_routed": wnba_dates,
            "wnba_runs": wnba_runs,
            "mlb_dates_routed": mlb_dates,
            "mlb_runs": mlb_runs,
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
    print("=" * 70)
    print("SPORTS HUB PRIZEPICKS HOURLY CAPTURE")
    print("=" * 70)
    print(f"All-sport rows: {result['all_sport_rows']:,}")
    print(f"Normalized MLB/WNBA rows: {result['normalized_mlb_wnba_rows']:,}")
    print(f"WNBA dates routed: {result['wnba_dates_routed']}")
    print(f"MLB dates routed: {result['mlb_dates_routed']}")
    print("Recommendations remain disabled.")


if __name__ == "__main__":
    main()
