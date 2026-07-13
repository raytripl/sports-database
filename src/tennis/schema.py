from __future__ import annotations

from contextlib import closing

from src.db import connect


SCHEMA = """
CREATE TABLE IF NOT EXISTS tennis_captures (
    capture_id TEXT PRIMARY KEY,
    captured_at TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    total_rows INTEGER NOT NULL,
    standard_rows INTEGER NOT NULL,
    model_status TEXT NOT NULL DEFAULT 'RESEARCH_ONLY',
    recommendations_enabled INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tennis_players (
    player_key TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    prizepicks_player_id TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tennis_prop_lines (
    tennis_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
    capture_id TEXT NOT NULL,
    projection_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    slate_date TEXT,
    start_time TEXT,
    player_key TEXT NOT NULL,
    player_name TEXT NOT NULL,
    prizepicks_player_id TEXT,
    opponent_key TEXT,
    opponent_name TEXT,
    prop_type TEXT NOT NULL,
    line REAL NOT NULL,
    odds_type TEXT,
    line_tier TEXT,
    is_standard_line INTEGER NOT NULL DEFAULT 0,
    projection_type TEXT,
    status TEXT,
    direction TEXT NOT NULL DEFAULT 'PASS',
    grade TEXT NOT NULL DEFAULT 'UNSUPPORTED',
    recommended INTEGER NOT NULL DEFAULT 0,
    decision_reason TEXT NOT NULL DEFAULT 'Tennis model not validated',
    source_file TEXT NOT NULL,
    FOREIGN KEY (capture_id) REFERENCES tennis_captures(capture_id),
    FOREIGN KEY (player_key) REFERENCES tennis_players(player_key),
    UNIQUE(capture_id, projection_id)
);

CREATE INDEX IF NOT EXISTS idx_tennis_lines_player_prop
ON tennis_prop_lines(player_key, prop_type, captured_at);

CREATE INDEX IF NOT EXISTS idx_tennis_lines_slate
ON tennis_prop_lines(slate_date, is_standard_line);

CREATE TABLE IF NOT EXISTS tennis_matches (
    match_id TEXT PRIMARY KEY,
    match_date TEXT NOT NULL,
    tour TEXT,
    tournament TEXT,
    surface TEXT,
    round TEXT,
    best_of INTEGER,
    player_one_key TEXT NOT NULL,
    player_two_key TEXT NOT NULL,
    winner_key TEXT,
    score TEXT,
    match_status TEXT,
    source TEXT NOT NULL,
    captured_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tennis_player_match_stats (
    match_id TEXT NOT NULL,
    player_key TEXT NOT NULL,
    opponent_key TEXT NOT NULL,
    sets_won INTEGER,
    games_won INTEGER,
    aces INTEGER,
    double_faults INTEGER,
    break_points_won INTEGER,
    tie_breaks_won INTEGER,
    service_points INTEGER,
    first_serves_in INTEGER,
    first_serve_points_won INTEGER,
    second_serve_points_won INTEGER,
    break_points_faced INTEGER,
    break_points_saved INTEGER,
    retired INTEGER NOT NULL DEFAULT 0,
    walkover INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(match_id, player_key),
    FOREIGN KEY (match_id) REFERENCES tennis_matches(match_id)
);

CREATE VIEW IF NOT EXISTS tennis_latest_standard_lines AS
SELECT line.*
FROM tennis_prop_lines AS line
JOIN (
    SELECT projection_id, MAX(captured_at) AS latest_captured_at
    FROM tennis_prop_lines
    WHERE is_standard_line = 1
    GROUP BY projection_id
) AS latest
ON line.projection_id = latest.projection_id
AND line.captured_at = latest.latest_captured_at;
"""


def initialize_tennis_schema() -> None:
    with closing(connect()) as connection:
        with connection:
            connection.executescript(SCHEMA)
