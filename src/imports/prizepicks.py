from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIRECTORY = PROJECT_ROOT / "data" / "pools" / "raw"
PROCESSED_DIRECTORY = PROJECT_ROOT / "data" / "pools" / "processed"

PRIZEPICKS_URL = "https://api.prizepicks.com/projections"

DEFAULT_PARAMETERS = {
    "per_page": 1000,
    "single_stat": "true",
    "game_mode": "pickem",
}

REQUEST_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://app.prizepicks.com",
    "Referer": "https://app.prizepicks.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    ),
}


def utc_timestamp() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")


def safe_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def relationship_id(item: dict[str, Any], relationship_name: str) -> str | None:
    relationships = item.get("relationships", {})
    relationship = relationships.get(relationship_name, {})
    data = relationship.get("data")

    if isinstance(data, dict):
        return str(data.get("id")) if data.get("id") is not None else None

    return None


def build_included_lookup(
    included: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}

    for item in included:
        item_type = str(item.get("type", ""))
        item_id = str(item.get("id", ""))

        if item_type and item_id:
            lookup[(item_type, item_id)] = item

    return lookup


def find_included_item(
    lookup: dict[tuple[str, str], dict[str, Any]],
    item_id: str | None,
    possible_types: tuple[str, ...],
) -> dict[str, Any]:
    if not item_id:
        return {}

    for item_type in possible_types:
        item = lookup.get((item_type, item_id))
        if item:
            return item

    return {}


def flatten_projection_data(payload: dict[str, Any]) -> pd.DataFrame:
    projections = payload.get("data", [])
    included = payload.get("included", [])

    if not isinstance(projections, list):
        raise ValueError("PrizePicks response did not contain a valid data list.")

    if not isinstance(included, list):
        included = []

    lookup = build_included_lookup(included)
    rows: list[dict[str, Any]] = []

    for projection in projections:
        attributes = projection.get("attributes", {})
        projection_id = str(projection.get("id", ""))

        player_id = (
            relationship_id(projection, "new_player")
            or relationship_id(projection, "player")
        )
        league_id = relationship_id(projection, "league")
        game_id = relationship_id(projection, "game")

        player_item = find_included_item(
            lookup,
            player_id,
            ("new_player", "player", "players"),
        )
        league_item = find_included_item(
            lookup,
            league_id,
            ("league", "leagues"),
        )
        game_item = find_included_item(
            lookup,
            game_id,
            ("game", "games"),
        )

        player_attributes = player_item.get("attributes", {})
        league_attributes = league_item.get("attributes", {})
        game_attributes = game_item.get("attributes", {})

        row = {
            "projection_id": projection_id,
            "player_id": player_id,
            "player_name": (
                player_attributes.get("name")
                or attributes.get("name")
                or attributes.get("player_name")
            ),
            "team": (
                player_attributes.get("team")
                or player_attributes.get("team_name")
                or attributes.get("team")
            ),
            "position": (
                player_attributes.get("position")
                or attributes.get("position")
            ),
            "league_id": league_id,
            "league": (
                league_attributes.get("name")
                or league_attributes.get("abbreviation")
                or attributes.get("league")
            ),
            "game_id": game_id,
            "game_description": (
                game_attributes.get("description")
                or attributes.get("description")
            ),
            "start_time": (
                attributes.get("start_time")
                or game_attributes.get("start_time")
            ),
            "stat_type": attributes.get("stat_type"),
            "line_score": attributes.get("line_score"),
            "projection_type": attributes.get("projection_type"),
            "odds_type": attributes.get("odds_type"),
            "is_live": attributes.get("is_live"),
            "status": attributes.get("status"),
            "board_time": attributes.get("board_time"),
            "updated_at": attributes.get("updated_at"),
            "flash_sale_line_score": attributes.get("flash_sale_line_score"),
            "discount_percentage": attributes.get("discount_percentage"),
            "description": attributes.get("description"),
            "source": "PrizePicks",
            "downloaded_at_utc": datetime.utcnow().isoformat(timespec="seconds"),
        }

        known_fields = set(row)
        for key, value in attributes.items():
            output_key = f"projection_{key}"

            if key not in known_fields and output_key not in row:
                row[output_key] = safe_value(value)

        rows.append(row)

    dataframe = pd.DataFrame(rows)

    if dataframe.empty:
        return dataframe

    preferred_columns = [
        "projection_id",
        "league",
        "league_id",
        "player_name",
        "player_id",
        "team",
        "position",
        "stat_type",
        "line_score",
        "projection_type",
        "odds_type",
        "start_time",
        "game_description",
        "description",
        "is_live",
        "status",
        "board_time",
        "updated_at",
        "source",
        "downloaded_at_utc",
    ]

    remaining_columns = [
        column
        for column in dataframe.columns
        if column not in preferred_columns
    ]

    existing_preferred = [
        column
        for column in preferred_columns
        if column in dataframe.columns
    ]

    return dataframe[existing_preferred + remaining_columns]


def download_prizepicks_payload(
    timeout: int = 30,
    retries: int = 3,
) -> dict[str, Any]:
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(
                PRIZEPICKS_URL,
                params=DEFAULT_PARAMETERS,
                headers=REQUEST_HEADERS,
                timeout=timeout,
            )

            if response.status_code == 403:
                raise RuntimeError(
                    "PrizePicks returned HTTP 403. "
                    "The request may have been blocked by Cloudflare."
                )

            response.raise_for_status()

            payload = response.json()

            if not isinstance(payload, dict):
                raise ValueError("PrizePicks returned an unexpected response.")

            return payload

        except (requests.RequestException, ValueError, RuntimeError) as error:
            last_error = error

            if attempt < retries:
                wait_seconds = attempt * 3
                print(
                    f"[WARNING] Attempt {attempt} failed: {error}",
                    file=sys.stderr,
                )
                print(
                    f"[INFO] Retrying in {wait_seconds} seconds...",
                    file=sys.stderr,
                )
                time.sleep(wait_seconds)

    raise RuntimeError(
        f"PrizePicks download failed after {retries} attempts: {last_error}"
    )


def save_pool(
    payload: dict[str, Any],
    sports: list[str] | None = None,
) -> tuple[Path, Path, int]:
    RAW_DIRECTORY.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIRECTORY.mkdir(parents=True, exist_ok=True)

    timestamp = utc_timestamp()

    raw_path = RAW_DIRECTORY / f"prizepicks_raw_{timestamp}.json"
    full_csv_path = (
        PROCESSED_DIRECTORY / f"prizepicks_pool_{timestamp}.csv"
    )

    with raw_path.open("w", encoding="utf-8") as raw_file:
        json.dump(payload, raw_file, indent=2, ensure_ascii=False)

    dataframe = flatten_projection_data(payload)

    if sports and not dataframe.empty and "league" in dataframe.columns:
        requested_sports = {
            sport.strip().upper()
            for sport in sports
            if sport.strip()
        }

        dataframe = dataframe[
            dataframe["league"]
            .fillna("")
            .astype(str)
            .str.upper()
            .isin(requested_sports)
        ].copy()

    if not dataframe.empty:
        dataframe = dataframe.drop_duplicates(
            subset=["projection_id"],
            keep="last",
        )

        sorting_columns = [
            column
            for column in ["league", "start_time", "player_name", "stat_type"]
            if column in dataframe.columns
        ]

        if sorting_columns:
            dataframe = dataframe.sort_values(
                sorting_columns,
                na_position="last",
            )

    dataframe.to_csv(full_csv_path, index=False)

    return raw_path, full_csv_path, len(dataframe)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download and save the current PrizePicks projection pool."
    )

    parser.add_argument(
        "--sports",
        nargs="*",
        default=None,
        help="Optional leagues to keep, such as MLB WNBA.",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds.",
    )

    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Number of download attempts.",
    )

    arguments = parser.parse_args()

    try:
        print("[INFO] Downloading PrizePicks projection board...")

        payload = download_prizepicks_payload(
            timeout=arguments.timeout,
            retries=arguments.retries,
        )

        raw_path, csv_path, row_count = save_pool(
            payload,
            sports=arguments.sports,
        )

        print(f"[SUCCESS] Saved {row_count:,} projections.")
        print(f"[SAVED] Raw JSON: {raw_path}")
        print(f"[SAVED] Processed CSV: {csv_path}")

        if row_count == 0:
            print(
                "[WARNING] The download succeeded, but no projections "
                "matched the requested sports."
            )

        return 0

    except Exception as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
