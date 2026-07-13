from __future__ import annotations

import argparse
import json
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src.imports import prizepicks
from src.imports import process_pool
from src.pipelines.wnba_daily import run_pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = PROJECT_ROOT / "data" / "runtime" / "prizepicks"
MODEL_RUNS = PROJECT_ROOT / "data" / "model_runs"
WNBA_HISTORY = PROJECT_ROOT / "data" / "wnba" / "WNBA_RESULTS_HISTORY.csv"
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


def eligible_wnba_dates(frame: pd.DataFrame, now: datetime) -> list[str]:
    if "league" not in frame.columns or "slate_date" not in frame.columns:
        return []
    wnba = frame[frame["league"].astype(str).str.upper() == "WNBA"]
    today = now.astimezone(CENTRAL).date()
    tomorrow = today + timedelta(days=1)
    available = set(wnba["slate_date"].dropna().astype(str))
    return [str(date) for date in (today, tomorrow) if str(date) in available]


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

        dates = eligible_wnba_dates(normalized, current)
        routed: list[dict[str, object]] = []
        for slate_date in dates:
            routed.append(
                run_pipeline(
                    pool_path=normalized_path,
                    slate_date=slate_date,
                    history_path=WNBA_HISTORY,
                    output_dir=MODEL_RUNS,
                )
            )

        manifest = {
            "captured_at": current.astimezone(CENTRAL).isoformat(),
            "raw_path": str(raw_path),
            "downloaded_csv": str(downloaded_csv),
            "normalized_path": str(normalized_path),
            "all_sport_rows": all_sport_rows,
            "normalized_mlb_wnba_rows": len(normalized),
            "leagues": normalized["league"].value_counts().to_dict(),
            "wnba_dates_routed": dates,
            "wnba_runs": routed,
            "recommendations_enabled": False,
        }
        manifest_path = RUNTIME_ROOT / "latest_capture_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hourly all-sport PrizePicks capture")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
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
    print("Recommendations remain disabled.")


if __name__ == "__main__":
    main()
