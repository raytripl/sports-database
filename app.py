"""Local Sports Hub dashboard.

This dashboard reads Sports Hub CSV and JSON outputs. It does not alter
production model scoring, v22-control, model thresholds, or promotion gates.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
LIVE_ROOT = DATA / "live"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

if not PYTHON.exists():
    PYTHON = Path(sys.executable)


st.set_page_config(
    page_title="Raymond Sports Hub",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)


CUSTOM_CSS = """
<style>
    .stApp {
        background:
            radial-gradient(
                circle at top right,
                rgba(15, 118, 110, 0.11),
                transparent 30%
            ),
            linear-gradient(
                180deg,
                #07111f 0%,
                #0a1422 52%,
                #07111f 100%
            );
        color: #f8fafc;
    }

    [data-testid="stSidebar"] {
        background: #08121f;
        border-right: 1px solid rgba(148, 163, 184, 0.18);
    }

    [data-testid="stMetric"] {
        background: rgba(15, 23, 42, 0.84);
        border: 1px solid rgba(148, 163, 184, 0.17);
        border-radius: 16px;
        padding: 14px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.20);
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid rgba(148, 163, 184, 0.17);
        border-radius: 16px;
        overflow: hidden;
    }

    .hero {
        padding: 25px 28px;
        border-radius: 22px;
        background:
            linear-gradient(
                135deg,
                rgba(13, 148, 136, 0.26),
                rgba(15, 23, 42, 0.92) 58%
            );
        border: 1px solid rgba(45, 212, 191, 0.28);
        margin-bottom: 18px;
        box-shadow: 0 18px 50px rgba(0, 0, 0, 0.24);
    }

    .hero-title {
        font-size: 2.1rem;
        font-weight: 850;
        margin: 0;
        letter-spacing: -0.04em;
    }

    .hero-subtitle {
        margin-top: 7px;
        color: #cbd5e1;
        font-size: 1rem;
    }

    .status-pill {
        display: inline-block;
        margin-top: 12px;
        margin-right: 8px;
        padding: 6px 11px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 750;
        background: rgba(15, 118, 110, 0.25);
        border: 1px solid rgba(45, 212, 191, 0.34);
        color: #99f6e4;
    }

    .warning-pill {
        display: inline-block;
        margin-top: 12px;
        padding: 6px 11px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 750;
        background: rgba(180, 83, 9, 0.22);
        border: 1px solid rgba(251, 191, 36, 0.30);
        color: #fde68a;
    }

    .prop-card {
        min-height: 214px;
        padding: 18px;
        border-radius: 18px;
        background: rgba(15, 23, 42, 0.92);
        border: 1px solid rgba(148, 163, 184, 0.18);
        box-shadow: 0 14px 34px rgba(0, 0, 0, 0.20);
        margin-bottom: 12px;
    }

    .prop-player {
        font-weight: 850;
        font-size: 1.08rem;
        color: #f8fafc;
    }

    .prop-meta {
        color: #94a3b8;
        margin-top: 3px;
        font-size: 0.86rem;
    }

    .prop-market {
        margin-top: 13px;
        font-size: 1.02rem;
        font-weight: 750;
    }

    .prop-direction {
        margin-top: 8px;
        font-size: 1.35rem;
        font-weight: 900;
    }

    .direction-over {
        color: #5eead4;
    }

    .direction-under {
        color: #fca5a5;
    }

    .prop-score {
        margin-top: 10px;
        color: #cbd5e1;
        font-size: 0.86rem;
        line-height: 1.6;
    }

    .small-note {
        color: #94a3b8;
        font-size: 0.82rem;
    }

    .section-title {
        margin-top: 8px;
        margin-bottom: 10px;
        font-size: 1.25rem;
        font-weight: 820;
    }

    .slip-box {
        padding: 16px;
        border-radius: 16px;
        background: rgba(15, 23, 42, 0.88);
        border: 1px solid rgba(148, 163, 184, 0.17);
    }

    .stButton > button {
        border-radius: 11px;
        font-weight: 760;
    }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def safe_read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    try:
        return pd.read_csv(path, low_memory=False)
    except Exception as error:
        st.warning(f"Could not read {path.name}: {error}")
        return pd.DataFrame()


def safe_read_json(path: Path) -> dict:
    if not path.exists():
        return {}

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def first_column(
    frame: pd.DataFrame,
    candidates: Iterable[str],
) -> str | None:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate

    return None


def string_series(
    frame: pd.DataFrame,
    candidates: Iterable[str],
    default: str = "",
) -> pd.Series:
    column = first_column(frame, candidates)

    if column is None:
        return pd.Series(
            [default] * len(frame),
            index=frame.index,
            dtype="object",
        )

    return (
        frame[column]
        .fillna(default)
        .astype(str)
        .str.strip()
    )


def numeric_series(
    frame: pd.DataFrame,
    candidates: Iterable[str],
    default: float = 0.0,
) -> pd.Series:
    column = first_column(frame, candidates)

    if column is None:
        return pd.Series(
            [default] * len(frame),
            index=frame.index,
            dtype="float64",
        )

    return pd.to_numeric(
        frame[column],
        errors="coerce",
    ).fillna(default)


def normalize_board(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()

    board = frame.copy()

    board["_sport"] = string_series(
        board,
        ["sport", "league"],
    ).str.upper()

    board["_player"] = string_series(
        board,
        ["player", "player_name", "name"],
        "Unknown Player",
    )

    board["_team"] = string_series(
        board,
        ["team", "team_abbreviation"],
    )

    board["_opponent"] = string_series(
        board,
        ["opponent", "opponent_team"],
    )

    board["_prop"] = string_series(
        board,
        ["prop_type", "stat_type", "market"],
        "Unknown Prop",
    )

    board["_direction"] = string_series(
        board,
        [
            "research_direction",
            "path_direction",
            "model_direction",
            "direction",
        ],
        "NO_DIRECTION",
    ).str.upper()

    board["_line"] = numeric_series(
        board,
        ["line", "line_score", "projection"],
    )

    board["_score"] = numeric_series(
        board,
        [
            "composite_score",
            "research_score",
            "decision_strength",
            "model_score",
            "statistical_score",
        ],
    )

    board["_probability"] = numeric_series(
        board,
        [
            "selected_probability",
            "probability",
            "calibrated_probability",
        ],
        0.50,
    )

    board["_selection_path"] = string_series(
        board,
        ["selection_path", "eligibility_status"],
    )

    board["_degrader"] = string_series(
        board,
        ["research_degrader_status"],
        "NONE",
    ).str.upper()

    board["_injury"] = string_series(
        board,
        ["injury_status", "availability_status"],
    )

    board["_lineup"] = numeric_series(
        board,
        ["lineup_confirmed"],
    )

    board["_starter"] = numeric_series(
        board,
        ["starter_confirmed"],
    )

    board["_rank"] = numeric_series(
        board,
        [
            "research_rank",
            "overall_rank",
            "final_rank",
            "diversified_rank",
        ],
        999999,
    )

    return board


def display_probability(value: float) -> str:
    if value <= 1.0:
        value *= 100

    return f"{value:.1f}%"


def display_number(value: float) -> str:
    if pd.isna(value):
        return "—"

    if float(value).is_integer():
        return str(int(value))

    return f"{value:.1f}"


def available_dates() -> list[str]:
    if not LIVE_ROOT.exists():
        return [date.today().isoformat()]

    values = sorted(
        [
            path.name
            for path in LIVE_ROOT.iterdir()
            if path.is_dir()
            and len(path.name) == 10
            and path.name[4] == "-"
            and path.name[7] == "-"
        ],
        reverse=True,
    )

    return values or [date.today().isoformat()]


def render_prop_card(
    row: pd.Series,
    card_key: str,
) -> None:
    direction = str(row.get("_direction", "")).upper()
    direction_class = (
        "direction-over"
        if direction == "OVER"
        else "direction-under"
    )

    matchup = " vs ".join(
        part
        for part in [
            str(row.get("_team", "")).strip(),
            str(row.get("_opponent", "")).strip(),
        ]
        if part
    )

    probability = float(row.get("_probability", 0.50))
    score = float(row.get("_score", 0.0))
    line = float(row.get("_line", 0.0))

    st.markdown(
        f"""
        <div class="prop-card">
            <div class="prop-player">
                {row.get("_player", "Unknown Player")}
            </div>
            <div class="prop-meta">
                {row.get("_sport", "")} · {matchup or "Matchup unavailable"}
            </div>
            <div class="prop-market">
                {row.get("_prop", "Unknown Prop")} · {display_number(line)}
            </div>
            <div class="prop-direction {direction_class}">
                {direction}
            </div>
            <div class="prop-score">
                Model score: <b>{score:.1f}</b><br>
                Probability: <b>{display_probability(probability)}</b><br>
                Path: <b>{row.get("_selection_path", "") or "Research"}</b><br>
                Degrader: <b>{row.get("_degrader", "NONE")}</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    label = (
        "Remove from slip"
        if card_key in st.session_state.slip_keys
        else "Add to slip"
    )

    if st.button(
        label,
        key=f"add_{card_key}",
        width="stretch",
    ):
        if card_key in st.session_state.slip_keys:
            st.session_state.slip_keys.remove(card_key)
        else:
            st.session_state.slip_keys.add(card_key)

        st.rerun()


def run_one_button(selected_date: str) -> tuple[int, str]:
    command = [
        str(PYTHON),
        "-m",
        "src.workflows.run_sports_hub",
        "--date",
        selected_date,
        "--skip-tests",
    ]

    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    return completed.returncode, completed.stdout


def run_tests() -> tuple[int, str]:
    command = [
        str(PYTHON),
        "-m",
        "pytest",
        "-q",
    ]

    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    return completed.returncode, completed.stdout


if "slip_keys" not in st.session_state:
    st.session_state.slip_keys = set()

if "run_output" not in st.session_state:
    st.session_state.run_output = ""

if "run_status" not in st.session_state:
    st.session_state.run_status = None


dates = available_dates()

with st.sidebar:
    st.markdown("## 🎯 Raymond Sports Hub")
    st.caption("Local model dashboard")

    selected_date = st.selectbox(
        "Slate date",
        dates,
        index=0,
    )

    selected_sport = st.radio(
        "Sport",
        ["ALL", "WNBA", "MLB"],
        horizontal=True,
    )

    st.divider()

    if st.button(
        "▶ Run Sports Hub",
        width="stretch",
        type="primary",
    ):
        with st.spinner("Running the complete Sports Hub workflow..."):
            returncode, output = run_one_button(selected_date)

        st.session_state.run_status = returncode
        st.session_state.run_output = output
        st.rerun()

    if st.button(
        "🧪 Run Tests",
        width="stretch",
    ):
        with st.spinner("Running Sports Hub tests..."):
            returncode, output = run_tests()

        st.session_state.run_status = returncode
        st.session_state.run_output = output
        st.rerun()

    if st.button(
        "Clear local slip",
        width="stretch",
    ):
        st.session_state.slip_keys = set()
        st.rerun()

    st.divider()

    st.caption(
        "Research dashboard only. Production remains v22-control. "
        "No automatic promotion or production recommendations."
    )


live = LIVE_ROOT / selected_date

final_board = normalize_board(
    safe_read_csv(live / "final_board.csv")
)

scored_board = normalize_board(
    safe_read_csv(live / "scored_board.csv")
)

research_candidates = normalize_board(
    safe_read_csv(live / "research_slip_candidates.csv")
)

if research_candidates.empty:
    research_candidates = normalize_board(
        safe_read_csv(live / "wnba_research_slip.csv")
    )

optimized_wnba = normalize_board(
    safe_read_csv(live / "wnba_optimized_research_slips.csv")
)

availability = safe_read_csv(
    live / "wnba_availability.csv"
)

mlb_context = safe_read_csv(
    live / "mlb_context.csv"
)

manifest = safe_read_json(
    live / "one_button_manifest.json"
)

pool_manifest = safe_read_json(
    live / "pool_manifest.json"
)


st.markdown(
    f"""
    <div class="hero">
        <div class="hero-title">Raymond Sports Hub</div>
        <div class="hero-subtitle">
            {selected_date} · MLB + WNBA model research, props and slips
        </div>
        <span class="status-pill">v22-control protected</span>
        <span class="status-pill">Research-only enhancements</span>
        <span class="warning-pill">No automatic promotion</span>
    </div>
    """,
    unsafe_allow_html=True,
)


if st.session_state.run_status is not None:
    if st.session_state.run_status == 0:
        st.success("Sports Hub command completed successfully.")
    else:
        st.error(
            "Sports Hub command returned an error. "
            "Open the command output below."
        )

    with st.expander(
        "Command output",
        expanded=st.session_state.run_status != 0,
    ):
        st.code(
            st.session_state.run_output[-30000:],
            language="text",
        )


source_board = (
    research_candidates
    if not research_candidates.empty
    else scored_board
)

if selected_sport != "ALL" and not source_board.empty:
    source_board = source_board[
        source_board["_sport"].eq(selected_sport)
    ].copy()


directional = source_board[
    source_board["_direction"].isin(["OVER", "UNDER"])
].copy()

directional = directional[
    ~directional["_degrader"].eq("HARD_BLOCK")
].copy()

directional = directional.sort_values(
    ["_score", "_rank"],
    ascending=[False, True],
)


metric_columns = st.columns(5)

metric_columns[0].metric(
    "Scored props",
    len(scored_board),
)

metric_columns[1].metric(
    "Research candidates",
    len(directional),
)

metric_columns[2].metric(
    "WNBA availability",
    len(availability),
)

metric_columns[3].metric(
    "MLB context rows",
    len(mlb_context),
)

metric_columns[4].metric(
    "Local slip legs",
    len(st.session_state.slip_keys),
)


tabs = st.tabs(
    [
        "🔥 Top Props",
        "🎟 Research Slips",
        "➕ Slip Builder",
        "🏥 Injuries & Lineups",
        "📈 Board Explorer",
        "✅ Run Status",
    ]
)


with tabs[0]:
    st.markdown(
        '<div class="section-title">Top directional research props</div>',
        unsafe_allow_html=True,
    )

    sport_filter = st.multiselect(
        "Display sports",
        ["WNBA", "MLB"],
        default=(
            ["WNBA", "MLB"]
            if selected_sport == "ALL"
            else [selected_sport]
        ),
        key="top_prop_sport_filter",
    )

    direction_filter = st.multiselect(
        "Direction",
        ["OVER", "UNDER"],
        default=["OVER", "UNDER"],
    )

    minimum_score = st.slider(
        "Minimum model score",
        min_value=0,
        max_value=100,
        value=55,
    )

    cards = directional[
        directional["_sport"].isin(sport_filter)
        & directional["_direction"].isin(direction_filter)
        & directional["_score"].ge(minimum_score)
    ].head(18)

    if cards.empty:
        st.info(
            "No props passed the selected filters. "
            "Lower the minimum score or inspect Board Explorer."
        )
    else:
        card_columns = st.columns(3)

        for position, (index, row) in enumerate(
            cards.iterrows()
        ):
            card_key = (
                f"{selected_date}|"
                f"{row['_sport']}|"
                f"{row['_player']}|"
                f"{row['_prop']}|"
                f"{row['_line']}|"
                f"{row['_direction']}|"
                f"{index}"
            )

            with card_columns[position % 3]:
                render_prop_card(row, card_key)


with tabs[1]:
    st.markdown(
        '<div class="section-title">Generated research slips</div>',
        unsafe_allow_html=True,
    )

    slip_files = [
        ("Power 2-Leg", live / "research_power_2_leg.csv"),
        ("Power 4-Leg", live / "research_power_4_leg.csv"),
        ("Flex 4-Leg", live / "research_flex_4_leg.csv"),
        ("Flex 6-Leg", live / "research_flex_6_leg.csv"),
        (
            "WNBA Optimized",
            live / "wnba_optimized_research_slips.csv",
        ),
    ]

    found_slip = False

    for label, path in slip_files:
        frame = safe_read_csv(path)

        if frame.empty:
            continue

        found_slip = True

        with st.expander(
            f"{label} · {len(frame)} legs",
            expanded=label in {"Power 2-Leg", "Flex 4-Leg"},
        ):
            preferred = [
                column
                for column in [
                    "leg_number",
                    "sport",
                    "player",
                    "team",
                    "opponent",
                    "prop_type",
                    "line",
                    "research_direction",
                    "path_direction",
                    "composite_score",
                    "research_score",
                    "decision_strength",
                    "direction_gap",
                    "probability",
                    "selection_path",
                    "research_degrader_status",
                    "injury_status",
                    "lineup_confirmed",
                    "starter_confirmed",
                ]
                if column in frame.columns
            ]

            st.dataframe(
                frame[preferred] if preferred else frame,
                width="stretch",
                hide_index=True,
            )

            st.download_button(
                f"Download {label}",
                data=frame.to_csv(index=False),
                file_name=path.name,
                mime="text/csv",
                key=f"download_{path.name}",
            )

    if not found_slip:
        st.info(
            "No generated slip files were found for this date. "
            "Run Sports Hub from the sidebar."
        )


with tabs[2]:
    st.markdown(
        '<div class="section-title">Local slip builder</div>',
        unsafe_allow_html=True,
    )

    st.caption(
        "Use Add to slip on Top Props. This builder does not place bets "
        "and does not mark research plays as production-approved."
    )

    selected_records = []

    for index, row in directional.iterrows():
        key = (
            f"{selected_date}|"
            f"{row['_sport']}|"
            f"{row['_player']}|"
            f"{row['_prop']}|"
            f"{row['_line']}|"
            f"{row['_direction']}|"
            f"{index}"
        )

        if key in st.session_state.slip_keys:
            selected_records.append(
                {
                    "sport": row["_sport"],
                    "player": row["_player"],
                    "team": row["_team"],
                    "opponent": row["_opponent"],
                    "prop_type": row["_prop"],
                    "line": row["_line"],
                    "direction": row["_direction"],
                    "model_score": row["_score"],
                    "probability": row["_probability"],
                    "selection_path": row["_selection_path"],
                    "research_degrader_status": row["_degrader"],
                    "slip_mode": "RESEARCH_ONLY",
                    "production_approved": 0,
                }
            )

    local_slip = pd.DataFrame(selected_records)

    if local_slip.empty:
        st.info(
            "Your local slip is empty. Add props from the Top Props tab."
        )
    else:
        same_player_count = (
            local_slip["player"]
            .value_counts()
            .loc[lambda values: values.gt(1)]
        )

        same_game_count = (
            local_slip.assign(
                game_key=local_slip.apply(
                    lambda row: "|".join(
                        sorted(
                            [
                                str(row["team"]),
                                str(row["opponent"]),
                            ]
                        )
                    ),
                    axis=1,
                )
            )["game_key"]
            .value_counts()
            .loc[lambda values: values.gt(2)]
        )

        warning_columns = st.columns(3)

        warning_columns[0].metric(
            "Legs",
            len(local_slip),
        )

        warning_columns[1].metric(
            "Average score",
            f"{local_slip['model_score'].mean():.1f}",
        )

        warning_columns[2].metric(
            "Average probability",
            display_probability(
                local_slip["probability"].mean()
            ),
        )

        if not same_player_count.empty:
            st.warning(
                "Duplicate-player warning: "
                + ", ".join(same_player_count.index)
            )

        if not same_game_count.empty:
            st.warning(
                "Correlation warning: more than two selected legs "
                "come from the same matchup."
            )

        st.dataframe(
            local_slip,
            width="stretch",
            hide_index=True,
        )

        st.download_button(
            "Download my research slip",
            data=local_slip.to_csv(index=False),
            file_name=(
                f"raymond_local_research_slip_"
                f"{selected_date}.csv"
            ),
            mime="text/csv",
            width="stretch",
        )


with tabs[3]:
    context_tabs = st.tabs(
        [
            "WNBA Availability",
            "MLB Context",
            "Pool Status",
        ]
    )

    with context_tabs[0]:
        if availability.empty:
            st.info("No WNBA availability file was found.")
        else:
            st.dataframe(
                availability,
                width="stretch",
                hide_index=True,
            )

    with context_tabs[1]:
        if mlb_context.empty:
            st.info("No MLB live-context file was found.")
        else:
            st.dataframe(
                mlb_context,
                width="stretch",
                hide_index=True,
            )

    with context_tabs[2]:
        if not pool_manifest:
            st.info("No pool manifest was found.")
        else:
            st.json(pool_manifest)


with tabs[4]:
    board_choice = st.selectbox(
        "Board",
        [
            "Research candidates",
            "Combined scored board",
            "Final public board",
            "WNBA optimized candidates",
        ],
    )

    board_map = {
        "Research candidates": research_candidates,
        "Combined scored board": scored_board,
        "Final public board": final_board,
        "WNBA optimized candidates": optimized_wnba,
    }

    explorer = board_map[board_choice].copy()

    if explorer.empty:
        st.info("The selected board has no rows.")
    else:
        searchable = [
            column
            for column in [
                "_player",
                "_team",
                "_opponent",
                "_prop",
                "_direction",
                "_selection_path",
            ]
            if column in explorer.columns
        ]

        search_value = st.text_input(
            "Search player, team or prop",
        ).strip()

        if search_value and searchable:
            combined = (
                explorer[searchable]
                .fillna("")
                .astype(str)
                .agg(" ".join, axis=1)
            )

            explorer = explorer[
                combined.str.contains(
                    search_value,
                    case=False,
                    regex=False,
                )
            ]

        visible_columns = [
            column
            for column in [
                "_sport",
                "_player",
                "_team",
                "_opponent",
                "_prop",
                "_line",
                "_direction",
                "_score",
                "_probability",
                "_selection_path",
                "_degrader",
                "_injury",
                "_lineup",
                "_starter",
            ]
            if column in explorer.columns
        ]

        st.dataframe(
            explorer[visible_columns],
            width="stretch",
            hide_index=True,
            column_config={
                "_sport": "Sport",
                "_player": "Player",
                "_team": "Team",
                "_opponent": "Opponent",
                "_prop": "Prop",
                "_line": st.column_config.NumberColumn(
                    "Line",
                    format="%.1f",
                ),
                "_direction": "Direction",
                "_score": st.column_config.ProgressColumn(
                    "Score",
                    min_value=0,
                    max_value=100,
                    format="%.1f",
                ),
                "_probability": st.column_config.NumberColumn(
                    "Probability",
                    format="%.3f",
                ),
                "_selection_path": "Path",
                "_degrader": "Degrader",
                "_injury": "Injury",
                "_lineup": "Lineup confirmed",
                "_starter": "Starter confirmed",
            },
        )


with tabs[5]:
    st.markdown(
        '<div class="section-title">One-button workflow status</div>',
        unsafe_allow_html=True,
    )

    if manifest:
        status = manifest.get(
            "overall_status",
            "UNKNOWN",
        )

        if status == "SUCCESS":
            st.success("Latest one-button run succeeded.")
        else:
            st.warning(f"Latest status: {status}")

        results = manifest.get("results", [])

        if isinstance(results, list) and results:
            st.dataframe(
                pd.DataFrame(results),
                width="stretch",
                hide_index=True,
            )

        st.json(manifest)
    else:
        st.info(
            "No one_button_manifest.json file was found for this date."
        )

    required_outputs = [
        "pool_manifest.json",
        "standardized_pool.csv",
        "scored_board.csv",
        "wnba_scored_board.csv",
        "mlb_scored_board.csv",
        "research_slip_candidates.csv",
        "research_power_2_leg.csv",
        "research_flex_4_leg.csv",
        "final_board.csv",
        "report.html",
    ]

    output_status = pd.DataFrame(
        [
            {
                "output": filename,
                "status": (
                    "FOUND"
                    if (live / filename).exists()
                    else "MISSING"
                ),
            }
            for filename in required_outputs
        ]
    )

    st.dataframe(
        output_status,
        width="stretch",
        hide_index=True,
    )


st.divider()
st.caption(
    "Raymond Sports Hub · Local research interface · "
    "Production model remains v22-control"
)
