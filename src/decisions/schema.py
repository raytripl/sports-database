from __future__ import annotations

from src.db import connect


SCHEMA = """
CREATE TABLE IF NOT EXISTS model_decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,

    slate_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    sport TEXT NOT NULL,

    game_id TEXT,
    game_time TEXT,

    player TEXT NOT NULL,
    player_id TEXT,
    team TEXT,
    opponent TEXT,

    prop_type TEXT NOT NULL,
    line REAL NOT NULL,
    direction TEXT NOT NULL,

    model_version TEXT NOT NULL DEFAULT 'v17.3',
    operating_revision TEXT NOT NULL DEFAULT 'Evidence-Enforced Revision B',

    model_score REAL,
    grade TEXT,
    overall_rank INTEGER,
    same_player_rank INTEGER,

    opportunity_score REAL,
    suppression_score REAL,
    matchup_score REAL,
    skill_score REAL,
    role_score REAL,
    workload_score REAL,
    coach_score REAL,
    manager_score REAL,
    ceiling_risk_score REAL,
    line_value_score REAL,
    evidence_agreement_score REAL,

    recommended INTEGER NOT NULL DEFAULT 0,
    entry_type TEXT,

    lineup_confirmed INTEGER,
    batting_order INTEGER,
    starter_confirmed INTEGER,
    injury_status TEXT,
    minutes_restriction TEXT,
    expected_minutes REAL,
    expected_plate_appearances REAL,
    expected_innings REAL,
    expected_pitch_count REAL,

    opponent_k_percent REAL,
    opponent_k_percent_vs_hand REAL,
    confirmed_lineup_k_percent REAL,

    over_reason TEXT,
    under_reason TEXT,
    red_flags TEXT,
    decision_reason TEXT,

    source_pool_file TEXT,
    snapshot_id TEXT,

    UNIQUE (
        slate_date,
        sport,
        player,
        prop_type,
        line,
        direction,
        snapshot_id
    )
);


CREATE TABLE IF NOT EXISTS prop_results (
    result_id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER NOT NULL,

    resolved_at TEXT,
    status TEXT NOT NULL,

    actual_value REAL,
    margin REAL,

    minutes REAL,
    plate_appearances REAL,
    innings REAL,
    pitch_count REAL,
    batters_faced REAL,

    starting_status TEXT,
    actual_batting_order INTEGER,

    opportunity_received TEXT,
    result_notes TEXT,
    error_classification TEXT,
    process_quality TEXT,
    model_change_required INTEGER DEFAULT 0,

    FOREIGN KEY (decision_id)
        REFERENCES model_decisions(decision_id)
        ON DELETE CASCADE,

    UNIQUE (decision_id)
);


CREATE TABLE IF NOT EXISTS historical_prop_lines (
    line_id INTEGER PRIMARY KEY AUTOINCREMENT,

    captured_at TEXT NOT NULL,
    slate_date TEXT NOT NULL,
    sport TEXT NOT NULL,

    player TEXT NOT NULL,
    team TEXT,
    opponent TEXT,

    prop_type TEXT NOT NULL,
    line REAL NOT NULL,

    over_odds TEXT,
    under_odds TEXT,
    source TEXT,
    line_tier TEXT,
    is_standard_line INTEGER NOT NULL DEFAULT 0,
    projection_type TEXT,
    odds_type TEXT,
    payout_modifier REAL,
    capture_id TEXT,

    is_opening_line INTEGER DEFAULT 0,
    is_closing_line INTEGER DEFAULT 0
);


CREATE TABLE IF NOT EXISTS team_daily_stats (
    team_stat_id INTEGER PRIMARY KEY AUTOINCREMENT,

    stat_date TEXT NOT NULL,
    sport TEXT NOT NULL,
    team TEXT NOT NULL,

    opponent TEXT,
    home_away TEXT,

    pace REAL,
    offensive_rating REAL,
    defensive_rating REAL,

    points_allowed REAL,
    rebounds_allowed REAL,
    assists_allowed REAL,
    fantasy_points_allowed REAL,

    offensive_rebound_rate REAL,
    defensive_rebound_rate REAL,
    turnover_rate REAL,
    three_point_attempt_rate REAL,

    strikeout_rate REAL,
    strikeout_rate_vs_rhp REAL,
    strikeout_rate_vs_lhp REAL,
    walk_rate REAL,
    ops REAL,
    obp REAL,
    slg REAL,
    iso REAL,
    runs_per_game REAL,

    bullpen_era REAL,
    bullpen_whip REAL,
    bullpen_usage_last_3_days REAL,

    source TEXT,

    UNIQUE (stat_date, sport, team)
);


CREATE TABLE IF NOT EXISTS manager_profiles (
    manager_profile_id INTEGER PRIMARY KEY AUTOINCREMENT,

    updated_at TEXT NOT NULL,
    season INTEGER NOT NULL,
    team TEXT NOT NULL,
    manager TEXT NOT NULL,

    starter_avg_pitches REAL,
    starter_avg_innings REAL,
    pct_reaching_90_pitches REAL,
    pct_reaching_100_pitches REAL,
    pct_finishing_6_innings REAL,

    early_hook_rate REAL,
    third_time_through_rate REAL,
    hook_after_3_runs_rate REAL,
    bullpen_aggressiveness REAL,

    rookie_leash_score REAL,
    veteran_leash_score REAL,

    pinch_hit_rate REAL,
    platoon_substitution_rate REAL,

    sample_size INTEGER,
    source TEXT,

    UNIQUE (season, team, manager)
);


CREATE TABLE IF NOT EXISTS coach_profiles (
    coach_profile_id INTEGER PRIMARY KEY AUTOINCREMENT,

    updated_at TEXT NOT NULL,
    season INTEGER NOT NULL,
    team TEXT NOT NULL,
    coach TEXT NOT NULL,

    rotation_size REAL,
    starter_minutes_average REAL,
    minutes_volatility REAL,

    closing_lineup_stability REAL,
    small_ball_rate REAL,
    double_big_rate REAL,

    blowout_substitution_time REAL,
    back_to_back_minutes_adjustment REAL,
    foul_trouble_hook_rate REAL,
    starter_return_adjustment REAL,

    sample_size INTEGER,
    source TEXT,

    UNIQUE (season, team, coach)
);


CREATE TABLE IF NOT EXISTS wnba_availability_snapshots (
    availability_id INTEGER PRIMARY KEY AUTOINCREMENT,

    snapshot_id TEXT NOT NULL,
    slate_date TEXT NOT NULL,
    captured_at TEXT NOT NULL,

    player TEXT NOT NULL,
    team TEXT,
    injury_status TEXT NOT NULL,
    lineup_confirmed INTEGER,
    starter_confirmed INTEGER,
    expected_minutes REAL,
    minutes_restriction TEXT,

    source TEXT NOT NULL,
    notes TEXT,

    UNIQUE (snapshot_id, player, captured_at, source)
);


CREATE TABLE IF NOT EXISTS wnba_on_off_splits (
    split_id INTEGER PRIMARY KEY AUTOINCREMENT,

    generated_at TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    season INTEGER NOT NULL,
    team TEXT,
    player TEXT NOT NULL,
    teammate TEXT NOT NULL,
    metric TEXT NOT NULL,

    with_games INTEGER NOT NULL,
    without_games INTEGER NOT NULL,
    with_average REAL,
    without_average REAL,
    without_minus_with REAL,
    with_per_minute REAL,
    without_per_minute REAL,
    sample_confidence REAL,
    sample_flag TEXT,
    source TEXT,

    UNIQUE (as_of_date, player, teammate, metric, team)
);


CREATE INDEX IF NOT EXISTS idx_decisions_slate
ON model_decisions (slate_date, sport);

CREATE INDEX IF NOT EXISTS idx_decisions_player
ON model_decisions (player, prop_type);

CREATE INDEX IF NOT EXISTS idx_decisions_grade
ON model_decisions (grade, direction);

CREATE INDEX IF NOT EXISTS idx_results_status
ON prop_results (status);

CREATE INDEX IF NOT EXISTS idx_lines_player
ON historical_prop_lines (slate_date, player, prop_type);

CREATE INDEX IF NOT EXISTS idx_wnba_availability_snapshot
ON wnba_availability_snapshots (snapshot_id, player, captured_at);

CREATE INDEX IF NOT EXISTS idx_wnba_on_off_player
ON wnba_on_off_splits (as_of_date, player, teammate, metric);
"""


def initialize_schema() -> None:
    with connect() as connection:
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.executescript(SCHEMA)
        existing = {
            row[1]
            for row in connection.execute("PRAGMA table_info(historical_prop_lines)")
        }
        additions = {
            "line_tier": "TEXT",
            "is_standard_line": "INTEGER NOT NULL DEFAULT 0",
            "projection_type": "TEXT",
            "odds_type": "TEXT",
            "payout_modifier": "REAL",
            "capture_id": "TEXT",
        }
        for column, definition in additions.items():
            if column not in existing:
                connection.execute(
                    f"ALTER TABLE historical_prop_lines ADD COLUMN {column} {definition}"
                )

    print("[OK] Model Decision Log schema initialized.")


if __name__ == "__main__":
    initialize_schema()
