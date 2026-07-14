from __future__ import annotations

import argparse
import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from pypdf import PdfReader

from src.db import connect
from src.decisions.schema import initialize_schema


EASTERN = ZoneInfo("America/New_York")
BASE_URL = "https://ak-static.cms.nba.com/referee/wnba_injury"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_ROOT = PROJECT_ROOT / "data" / "wnba" / "injury_reports"
VALID_STATUSES = {"AVAILABLE", "PROBABLE", "QUESTIONABLE", "DOUBTFUL", "OUT"}


def floor_quarter_hour(value: datetime) -> datetime:
    eastern = value.astimezone(EASTERN)
    return eastern.replace(minute=eastern.minute // 15 * 15, second=0, microsecond=0)


def report_url(value: datetime) -> str:
    stamp = value.astimezone(EASTERN).strftime("%Y-%m-%d_%I_%M%p")
    return f"{BASE_URL}/Injury-Report_{stamp}.pdf"


def candidate_times(now: datetime, lookback_hours: float = 8.0) -> list[datetime]:
    latest = floor_quarter_hour(now)
    count = int(lookback_hours * 4) + 1
    return [latest - timedelta(minutes=15 * index) for index in range(count)]


def download_latest(now: datetime | None = None, lookback_hours: float = 8.0) -> tuple[bytes, str, datetime]:
    current = now or datetime.now(timezone.utc)
    for candidate in candidate_times(current, lookback_hours):
        url = report_url(candidate)
        response = requests.get(url, timeout=20)
        if response.status_code == 404:
            continue
        response.raise_for_status()
        if not response.content.startswith(b"%PDF"):
            raise ValueError(f"WNBA report response is not a PDF: {url}")
        return response.content, url, candidate
    raise FileNotFoundError("No official WNBA injury report found in the lookback window")


def positioned_pages(pdf_bytes: bytes) -> list[list[tuple[float, float, str]]]:
    pages = []
    for page in PdfReader(io.BytesIO(pdf_bytes)).pages:
        items: list[tuple[float, float, str]] = []

        def visitor(text, _cm, tm, _font, _size):
            clean = str(text).strip()
            if clean:
                items.append((round(float(tm[4]), 1), round(float(tm[5]), 1), clean))

        page.extract_text(visitor_text=visitor)
        pages.append(items)
    return pages


def parse_positioned_pages(pages: list[list[tuple[float, float, str]]]) -> pd.DataFrame:
    output: list[dict[str, str]] = []
    current = {"game_date": "", "game_time": "", "matchup": "", "team": ""}
    for items in pages:
        grouped: dict[float, list[tuple[float, str]]] = {}
        for x, y, text in items:
            grouped.setdefault(round(y, 1), []).append((x, text))
        for y in sorted(grouped):
            columns = {key: [] for key in ("date", "time", "matchup", "team", "player", "status", "reason")}
            for x, text in sorted(grouped[y]):
                if x < 100:
                    columns["date"].append(text)
                elif x < 190:
                    columns["time"].append(text)
                elif x < 260:
                    columns["matchup"].append(text)
                elif x < 420:
                    columns["team"].append(text)
                elif x < 580:
                    columns["player"].append(text)
                elif x < 665:
                    columns["status"].append(text)
                else:
                    columns["reason"].append(text)
            date = " ".join(columns["date"])
            if date and date[0].isdigit() and "/" in date:
                current["game_date"] = pd.Timestamp(date).strftime("%Y-%m-%d")
            time = " ".join(columns["time"]).replace(" (ET)", "")
            if time and time[0].isdigit():
                current["game_time"] = time
            matchup = "".join(columns["matchup"])
            if "@" in matchup:
                current["matchup"] = matchup
            team = " ".join(columns["team"])
            if team and team != "Team":
                current["team"] = team
            player_tokens = columns["player"]
            status = " ".join(columns["status"]).upper()
            reason = " ".join(columns["reason"])
            if player_tokens and "," in " ".join(player_tokens) and status in VALID_STATUSES:
                surname, given = " ".join(player_tokens).split(",", 1)
                output.append(current.copy() | {
                    "player": f"{given.strip()} {surname.strip()}",
                    "injury_status": status,
                    "reason": reason,
                })
            elif reason and output:
                output[-1]["reason"] = (output[-1]["reason"] + " " + reason).strip()
    frame = pd.DataFrame(output)
    required = {"game_date", "matchup", "team", "player", "injury_status"}
    if frame.empty or frame[list(required)].replace("", pd.NA).isna().any().any():
        raise ValueError("Official WNBA report parsed with missing required fields")
    return frame.drop_duplicates(["game_date", "matchup", "team", "player"], keep="last")


def parse_pdf(pdf_bytes: bytes) -> pd.DataFrame:
    return parse_positioned_pages(positioned_pages(pdf_bytes))


def compare_reports(previous: pd.DataFrame, current: pd.DataFrame) -> pd.DataFrame:
    keys = ["game_date", "matchup", "team", "player"]
    old = previous.set_index(keys) if not previous.empty else pd.DataFrame().set_index(pd.MultiIndex.from_tuples([], names=keys))
    new = current.set_index(keys)
    rows = []
    for key in old.index.union(new.index):
        before = old.loc[key]["injury_status"] if key in old.index else None
        after = new.loc[key]["injury_status"] if key in new.index else None
        if before != after:
            rows.append(dict(zip(keys, key)) | {"previous_status": before, "current_status": after})
    return pd.DataFrame(rows)


def capture_latest(now: datetime | None = None, lookback_hours: float = 8.0) -> dict[str, object]:
    pdf_bytes, url, report_time = download_latest(now, lookback_hours)
    frame = parse_pdf(pdf_bytes)
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    report_id = digest[:16]
    archive = ARCHIVE_ROOT / report_time.strftime("%Y-%m-%d") / Path(url).name
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(pdf_bytes)
    initialize_schema()
    with connect() as connection:
        previous_id = connection.execute(
            "SELECT report_id FROM wnba_official_injury_reports ORDER BY report_timestamp DESC LIMIT 1"
        ).fetchone()
        previous = pd.DataFrame()
        if previous_id and previous_id[0] != report_id:
            previous = pd.read_sql_query(
                "SELECT game_date, game_time, matchup, team, player, injury_status, reason FROM wnba_official_availability WHERE report_id = ?",
                connection, params=(previous_id[0],),
            )
        connection.execute(
            "INSERT OR IGNORE INTO wnba_official_injury_reports VALUES (?, ?, ?, ?, ?, ?, ?)",
            (report_id, report_time.isoformat(), datetime.now(timezone.utc).isoformat(), url, digest, str(archive), len(frame)),
        )
        for row in frame.to_dict("records"):
            connection.execute(
                "INSERT OR REPLACE INTO wnba_official_availability VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (report_id, row["game_date"], row["game_time"], row["matchup"], row["team"], row["player"], row["injury_status"], row["reason"]),
            )
    changes = compare_reports(previous, frame) if not previous.empty else pd.DataFrame()
    csv_path = archive.with_suffix(".csv")
    frame.assign(captured_at=report_time.isoformat(), source=url).to_csv(csv_path, index=False)
    manifest = {
        "report_id": report_id, "report_timestamp": report_time.isoformat(), "source_url": url,
        "archive_path": str(archive), "csv_path": str(csv_path), "rows": len(frame),
        "changes_from_previous": len(changes), "recommendations_enabled": False,
    }
    archive.with_suffix(".json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture the latest official WNBA injury report")
    parser.add_argument("--lookback-hours", type=float, default=8.0)
    args = parser.parse_args()
    print(json.dumps(capture_latest(lookback_hours=args.lookback_hours), indent=2))


if __name__ == "__main__":
    main()
