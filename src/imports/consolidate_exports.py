from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = {
    "projection_id", "league", "player_name", "team", "stat_type",
    "line_score", "odds_type", "start_time",
}


def read_valid(path: Path) -> pd.DataFrame | None:
    try:
        frame = pd.read_csv(path, low_memory=False)
    except (OSError, ValueError, pd.errors.ParserError):
        return None
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    if not REQUIRED_COLUMNS.issubset(frame.columns):
        return None
    frame["league"] = frame["league"].fillna("").astype(str).str.strip().str.upper()
    return frame[frame["league"].ne("")].copy()


def consolidate_directory(
    directory: Path,
    output: Path,
    anchor: Path | None = None,
    max_age_hours: float = 24.0,
) -> tuple[Path, dict[str, object]]:
    candidates: list[tuple[Path, pd.DataFrame]] = []
    for path in directory.glob("*.csv"):
        if path.resolve() == output.resolve():
            continue
        frame = read_valid(path)
        if frame is not None and not frame.empty:
            candidates.append((path, frame))
    if not candidates:
        raise FileNotFoundError(f"No valid PrizePicks exports in {directory}")

    newest_path = anchor or max(candidates, key=lambda item: item[0].stat().st_mtime)[0]
    anchor_time = newest_path.stat().st_mtime
    cutoff = anchor_time - max_age_hours * 3600
    recent = [item for item in candidates if item[0].stat().st_mtime >= cutoff]
    recent.sort(key=lambda item: item[0].stat().st_mtime, reverse=True)

    selected: dict[str, tuple[Path, pd.DataFrame]] = {}
    for path, frame in recent:
        for league in frame["league"].unique():
            if league not in selected:
                selected[league] = (path, frame[frame["league"].eq(league)].copy())

    unique_sources = {path.resolve() for path, _ in selected.values()}
    if len(unique_sources) == 1:
        source = next(iter(selected.values()))[0]
        manifest = {
            "mode": "SINGLE_EXPORT", "output": str(source),
            "leagues": sorted(selected),
            "sources": {league: str(path) for league, (path, _) in selected.items()},
        }
        return source, manifest

    rows: list[pd.DataFrame] = []
    sources: dict[str, str] = {}
    for league, (path, frame) in sorted(selected.items()):
        frame["source_export_file"] = path.name
        frame["source_export_mtime_utc"] = datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        ).isoformat()
        rows.append(frame)
        sources[league] = str(path)
    combined = pd.concat(rows, ignore_index=True, sort=False)
    combined = combined.drop_duplicates("projection_id", keep="first")
    output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output, index=False)
    manifest = {
        "mode": "CONSOLIDATED_EXPORTS", "output": str(output),
        "rows": len(combined), "leagues": sorted(selected), "sources": sources,
        "max_age_hours": max_age_hours,
    }
    output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return output, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolidate newest PrizePicks export per league")
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-age-hours", type=float, default=24.0)
    args = parser.parse_args()
    path, manifest = consolidate_directory(
        args.directory, args.output, max_age_hours=args.max_age_hours
    )
    print(f"Saved: {path}")
    print(f"Mode: {manifest['mode']}")
    print(f"Leagues: {', '.join(manifest['leagues'])}")


if __name__ == "__main__":
    main()
