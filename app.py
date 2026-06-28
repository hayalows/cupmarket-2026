
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import re

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

from features.product_ui import (
    render_live_vs_official_note,
    render_project_credit,
    render_project_footer,
    render_start_here,
)
from features.match_ui import match_stage_label

st.set_page_config(
    page_title="CupMarket 2026",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

APP_ROOT = Path(__file__).resolve().parent
DATA_DIR = APP_ROOT / "data"
HISTORY_DIR = DATA_DIR / "market_history"

PRICES_PATH = DATA_DIR / "cupmarket_prices_latest.csv"
PROBABILITIES_PATH = DATA_DIR / "tournament_probabilities_latest.csv"
GROUP_TABLES_PATH = DATA_DIR / "current_group_tables.csv"
PREDICTIONS_PATH = DATA_DIR / "world_cup_live_predictions_latest.csv"
MATCH_SNAPSHOT_PATH = DATA_DIR / "world_cup_2026_matches_latest.csv"

PHASE3_EVAL_PATH = DATA_DIR / "phase3_goal_model_evaluation.json"
PHASE4_EVAL_PATH = DATA_DIR / "phase4_live_evaluation.json"
PHASE5_META_PATH = DATA_DIR / "phase5_simulation_metadata.json"

API_URL = "https://api.football-data.org/v4/competitions/WC/matches"
GITHUB_WORKFLOW_RUNS_URL = (
    "https://api.github.com/repos/hayalows/cupmarket-2026/"
    "actions/workflows/update-cupmarket.yml/runs?per_page=30"
)
WORKFLOW_STALE_MINUTES = 45

PRODUCT_UI_VERSION = "2.0"
PRODUCT_CSS_PATHS = [
    APP_ROOT / "assets" / "product.css",
    APP_ROOT / "assets" / "group_tools.css",
]

px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = [
    "#5B5FF0",
    "#12B981",
    "#F59E0B",
    "#0EA5E9",
    "#EC4899",
    "#8B5CF6",
]


def inject_product_styles() -> None:
    for stylesheet in PRODUCT_CSS_PATHS:
        if stylesheet.exists():
            css = stylesheet.read_text(encoding="utf-8")
            st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def render_page_header(page: str, health: dict, metadata: dict) -> None:
    page_copy = {
        "Overview": (
            "Tournament intelligence",
            "A live view of matches, probabilities and the country market.",
        ),
        "Match Centre": (
            "Match Centre",
            "Fixtures, scores and model probabilities in one place.",
        ),
        "Country Market": (
            "Country Market",
            "Probability-weighted prices that move as the tournament changes.",
        ),
        "Team Explorer": (
            "Team Explorer",
            "Inspect a country's path, price and tournament outlook.",
        ),
        "Group Tables": (
            "Group Tables",
            "Current standings built from completed tournament results.",
        ),
        "Model Health": (
            "Model Health",
            "Operational status, evaluation metrics and data freshness.",
        ),
        "How It Works": (
            "How CupMarket works",
            "A transparent view of the data, models and pricing logic.",
        ),
    }
    title, description = page_copy.get(
        page,
        (page, "World Cup intelligence powered by live data and simulation."),
    )
    status = str(health.get("status", "Unknown"))
    status_class = status.lower().replace(" ", "-")
    simulations = int(metadata.get("number_of_simulations", 0) or 0)
    generated = format_utc_timestamp(metadata.get("generated_at_utc"))
    st.markdown(
        f'''
        <div class="cm-hero">
            <div class="cm-hero-top">
                <div class="cm-eyebrow">CupMarket 2026 · Live intelligence</div>
                <div class="cm-status {status_class}">
                    <span class="cm-dot"></span>{status}
                </div>
            </div>
            <h1>{title}</h1>
            <p>{description}</p>
            <div class="cm-hero-meta">
                <span class="cm-chip">◉ {simulations:,} simulations</span>
                <span class="cm-chip">↻ Updated {generated}</span>
                <span class="cm-chip">◎ Virtual market · No real money</span>
            </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def render_section_heading(
    title: str,
    description: str,
    kicker: str = "Live data",
) -> None:
    st.markdown(
        f'''
        <div class="cm-section-heading">
            <div class="kicker">{kicker}</div>
            <h2>{title}</h2>
            <p>{description}</p>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def polish_figure(figure, height: int | None = None):
    figure.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#ffffff",
        font=dict(
            family='-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
            color="#4b5568",
            size=13,
        ),
        title_font=dict(color="#10131a", size=18),
        margin=dict(l=24, r=24, t=64, b=24),
        hoverlabel=dict(
            bgcolor="#111827",
            font_color="#ffffff",
            bordercolor="#111827",
        ),
    )
    if height:
        figure.update_layout(height=height)
    figure.update_xaxes(gridcolor="#edf0f5", zeroline=False)
    figure.update_yaxes(gridcolor="#edf0f5", zeroline=False)
    return figure


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    frame = pd.read_csv(path)

    for column in [
        "utc_date",
        "generated_at_utc",
        "prediction_created_at",
        "last_updated",
    ]:
        if column in frame.columns:
            frame[column] = pd.to_datetime(
                frame[column],
                errors="coerce",
                utc=True,
            )

    return frame


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def format_percent(value, digits: int = 1) -> str:
    if pd.isna(value):
        return "—"
    return f"{100 * float(value):.{digits}f}%"


def format_number(value, digits: int = 2) -> str:
    if pd.isna(value):
        return "—"
    return f"{float(value):.{digits}f}"


def score_text(row: pd.Series) -> str:
    home = row.get("home_score_full_time")
    away = row.get("away_score_full_time")

    if pd.isna(home) or pd.isna(away):
        return "vs"

    return f"{int(home)}–{int(away)}"


def nested_get(dictionary, keys, default=None):
    current = dictionary

    for key in keys:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current is None:
            return default

    return current


def parse_api_matches(payload: dict) -> pd.DataFrame:
    rows = []

    for match in payload.get("matches", []):
        rows.append(
            {
                "match_id": match.get("id"),
                "utc_date": match.get("utcDate"),
                "status": match.get("status"),
                "stage": match.get("stage"),
                "group": match.get("group"),
                "home_team": nested_get(
                    match,
                    ["homeTeam", "name"],
                ),
                "away_team": nested_get(
                    match,
                    ["awayTeam", "name"],
                ),
                "home_score_full_time": nested_get(
                    match,
                    ["score", "fullTime", "home"],
                ),
                "away_score_full_time": nested_get(
                    match,
                    ["score", "fullTime", "away"],
                ),
                "last_updated": match.get("lastUpdated"),
            }
        )

    frame = pd.DataFrame(rows)

    if frame.empty:
        return frame

    frame["utc_date"] = pd.to_datetime(
        frame["utc_date"],
        errors="coerce",
        utc=True,
    )

    frame["last_updated"] = pd.to_datetime(
        frame["last_updated"],
        errors="coerce",
        utc=True,
    )

    return frame.sort_values("utc_date").reset_index(drop=True)


@st.cache_data(ttl=60, show_spinner=False)
def fetch_live_matches(token: str) -> tuple[pd.DataFrame, dict]:
    response = requests.get(
        API_URL,
        headers={"X-Auth-Token": token},
        timeout=30,
    )

    response.raise_for_status()

    metadata = {
        "requests_remaining": (
            response.headers.get("X-RequestsAvailable")
            or response.headers.get(
                "X-Requests-Available-Minute"
            )
        ),
        "counter_reset": response.headers.get(
            "X-RequestCounter-Reset"
        ),
        "fetched_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    return parse_api_matches(response.json()), metadata


@st.cache_data(ttl=300, show_spinner=False)
def fetch_workflow_health() -> dict:
    try:
        response = requests.get(
            GITHUB_WORKFLOW_RUNS_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "CupMarket-Streamlit",
            },
            timeout=20,
        )
        response.raise_for_status()
        runs = response.json().get("workflow_runs", [])
    except Exception as exc:
        return {
            "available": False,
            "warning": str(exc),
            "latest_run": None,
            "last_success": None,
            "last_failure": None,
        }

    def summarize(run):
        if not run:
            return None
        return {
            "run_number": run.get("run_number"),
            "event": run.get("event"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "created_at": run.get("created_at"),
            "run_started_at": run.get("run_started_at"),
            "updated_at": run.get("updated_at"),
            "html_url": run.get("html_url"),
            "head_sha": run.get("head_sha"),
        }

    latest = runs[0] if runs else None
    last_success = next(
        (
            run
            for run in runs
            if run.get("status") == "completed"
            and run.get("conclusion") == "success"
        ),
        None,
    )
    failure_conclusions = {
        "failure",
        "cancelled",
        "timed_out",
        "action_required",
        "startup_failure",
        "stale",
    }
    last_failure = next(
        (
            run
            for run in runs
            if run.get("status") == "completed"
            and run.get("conclusion") in failure_conclusions
        ),
        None,
    )

    return {
        "available": True,
        "warning": None,
        "latest_run": summarize(latest),
        "last_success": summarize(last_success),
        "last_failure": summarize(last_failure),
    }


def utc_timestamp(value):
    if not value:
        return pd.NaT
    return pd.to_datetime(value, errors="coerce", utc=True)


def format_utc_timestamp(value) -> str:
    timestamp = utc_timestamp(value)
    if pd.isna(timestamp):
        return "Never"
    return timestamp.strftime("%Y-%m-%d %H:%M UTC")


def build_production_health(
    matches: pd.DataFrame,
    simulation_metadata: dict,
    workflow_health: dict,
) -> dict:
    now = pd.Timestamp.now(tz="UTC")
    latest_run = workflow_health.get("latest_run") or {}
    last_success = workflow_health.get("last_success") or {}
    last_failure = workflow_health.get("last_failure") or {}

    live_finished_group_matches = 0
    if not matches.empty and {"stage", "status"}.issubset(matches.columns):
        live_finished_group_matches = int(
            (
                (matches["stage"] == "GROUP_STAGE")
                & (matches["status"] == "FINISHED")
            ).sum()
        )

    model_finished_group_matches = int(
        simulation_metadata.get("finished_group_matches", 0) or 0
    )
    pending_finished_matches = max(
        0,
        live_finished_group_matches - model_finished_group_matches,
    )

    reasons = []
    latest_status = latest_run.get("status")
    latest_conclusion = latest_run.get("conclusion")

    if not workflow_health.get("available"):
        workflow_label = "Unknown"
        reasons.append("GitHub Actions status could not be loaded")
    elif latest_status in {"queued", "in_progress", "waiting", "requested"}:
        workflow_label = "Updating"
    elif latest_conclusion == "success":
        workflow_label = "Healthy"
    elif latest_run:
        workflow_label = "Failed"
        reasons.append(
            "the latest GitHub Actions run did not complete successfully"
        )
    else:
        workflow_label = "Unknown"
        reasons.append("no GitHub Actions run was found")

    workflow_updated_at = utc_timestamp(latest_run.get("updated_at"))
    workflow_age_minutes = None
    if not pd.isna(workflow_updated_at):
        workflow_age_minutes = max(
            0.0,
            (now - workflow_updated_at).total_seconds() / 60.0,
        )
        if workflow_age_minutes > WORKFLOW_STALE_MINUTES:
            reasons.append(
                f"the latest workflow check is {workflow_age_minutes:.0f} minutes old"
            )

    if pending_finished_matches:
        reasons.append(
            f"{pending_finished_matches} finished group match"
            + ("es are" if pending_finished_matches != 1 else " is")
            + " not yet included in the model"
        )

    model_generated_at = utc_timestamp(
        simulation_metadata.get("generated_at_utc")
    )
    model_age_hours = None
    if pd.isna(model_generated_at):
        reasons.append("no model-generation timestamp is available")
    else:
        model_age_hours = max(
            0.0,
            (now - model_generated_at).total_seconds() / 3600.0,
        )

    status = workflow_label
    if reasons and status == "Healthy":
        status = "Attention"

    return {
        "status": status,
        "stale": bool(reasons),
        "reasons": reasons,
        "latest_run": latest_run,
        "last_success": last_success,
        "last_failure": last_failure,
        "last_success_text": format_utc_timestamp(
            last_success.get("updated_at")
        ),
        "last_failure_text": format_utc_timestamp(
            last_failure.get("updated_at")
        ),
        "model_generated_text": format_utc_timestamp(
            simulation_metadata.get("generated_at_utc")
        ),
        "model_age_hours": model_age_hours,
        "workflow_age_minutes": workflow_age_minutes,
        "live_finished_group_matches": live_finished_group_matches,
        "model_finished_group_matches": model_finished_group_matches,
        "pending_finished_matches": pending_finished_matches,
        "new_matches_processed": int(
            simulation_metadata.get(
                "new_finished_matches_processed",
                0,
            )
            or 0
        ),
    }


def get_match_data() -> tuple[pd.DataFrame, dict]:
    token = None

    try:
        token = st.secrets.get(
            "FOOTBALL_DATA_TOKEN"
        )
    except Exception:
        token = None

    if token:
        try:
            matches, metadata = fetch_live_matches(
                str(token).strip()
            )
            metadata["source"] = "Live API"
            return matches, metadata
        except Exception as exc:
            fallback = read_csv(
                MATCH_SNAPSHOT_PATH
            )
            return fallback, {
                "source": "Saved snapshot",
                "warning": str(exc),
            }

    return read_csv(MATCH_SNAPSHOT_PATH), {
        "source": "Saved snapshot",
        "warning": (
            "No FOOTBALL_DATA_TOKEN was configured "
            "in Streamlit secrets."
        ),
    }


def load_price_history() -> pd.DataFrame:
    if not HISTORY_DIR.exists():
        return pd.DataFrame()

    rows = []

    for path in sorted(
        HISTORY_DIR.glob(
            "cupmarket_prices_*.csv"
        )
    ):
        frame = read_csv(path)

        if frame.empty:
            continue

        timestamp_match = re.search(
            r"(\d{8}T\d{6}Z)",
            path.name,
        )

        file_timestamp = pd.to_datetime(
            timestamp_match.group(1),
            format="%Y%m%dT%H%M%SZ",
            utc=True,
            errors="coerce",
        ) if timestamp_match else pd.NaT

        if "generated_at_utc" not in frame.columns:
            frame["generated_at_utc"] = (
                file_timestamp
            )

        rows.append(
            frame[
                [
                    "team",
                    "cupmarket_price",
                    "generated_at_utc",
                ]
            ]
        )

    if not rows:
        return pd.DataFrame()

    history = pd.concat(
        rows,
        ignore_index=True,
    )

    history = history.dropna(
        subset=[
            "team",
            "cupmarket_price",
            "generated_at_utc",
        ]
    )

    return (
        history
        .drop_duplicates(
            subset=[
                "team",
                "generated_at_utc",
            ],
            keep="last",
        )
        .sort_values(
            [
                "team",
                "generated_at_utc",
            ]
        )
        .reset_index(drop=True)
    )


prices = read_csv(PRICES_PATH)
probabilities = read_csv(PROBABILITIES_PATH)
group_tables = read_csv(GROUP_TABLES_PATH)
predictions = read_csv(PREDICTIONS_PATH)
price_history = load_price_history()

phase3_eval = read_json(PHASE3_EVAL_PATH)
phase4_eval = read_json(PHASE4_EVAL_PATH)
phase5_meta = read_json(PHASE5_META_PATH)

matches, match_metadata = get_match_data()
workflow_health = fetch_workflow_health()
production_health = build_production_health(
    matches,
    phase5_meta,
    workflow_health,
)

inject_product_styles()

NAV_LABELS = {
    "Overview": "◫  Overview",
    "Match Centre": "◉  Match Centre",
    "Country Market": "↗  Country Market",
    "Team Explorer": "◎  Team Explorer",
    "Group Tables": "▤  Group Tables",
    "Model Health": "◌  Model Health",
    "How It Works": "ⓘ  How It Works",
}

with st.sidebar:
    st.markdown(
        '''
        <div class="cm-side-brand">
            <div class="cm-mark">CM</div>
            <div>
                <strong>CupMarket</strong>
                <span>World Cup intelligence project</span>
            </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    page = st.radio(
        "Choose a page",
        list(NAV_LABELS),
        format_func=lambda item: NAV_LABELS[item],
        label_visibility="collapsed",
    )

    st.markdown(
        '<div class="cm-side-label">Live tools</div>',
        unsafe_allow_html=True,
    )
    st.page_link("pages/1_Match_Intelligence.py", label="Match Intelligence", icon="⚽")
    st.page_link("pages/2_Qualification_Lab.py", label="Qualification Lab", icon="🧭")
    st.page_link("pages/3_Live_Group_Centre.py", label="Live Group Centre", icon="📊")

    st.markdown(
        '<div class="cm-side-label">System status</div>',
        unsafe_allow_html=True,
    )

    source = match_metadata.get("source", "Unknown")
    score_time = "Waiting for data"
    if match_metadata.get("fetched_at_utc"):
        score_time = pd.to_datetime(
            match_metadata["fetched_at_utc"],
            utc=True,
        ).strftime("%H:%M UTC")

    simulation_time = "Waiting for model"
    if phase5_meta.get("generated_at_utc"):
        simulation_time = pd.to_datetime(
            phase5_meta["generated_at_utc"],
            utc=True,
        ).strftime("%H:%M UTC")

    st.markdown(
        f'''
        <div class="cm-side-row">
            <b>{production_health.get("status", "Unknown")}</b><br>
            Scores · {source} · {score_time}<br>
            Model · {simulation_time}
        </div>
        ''',
        unsafe_allow_html=True,
    )

    if match_metadata.get("warning"):
        st.caption(match_metadata["warning"])

    st.caption("Match data provided by football-data.org")
    render_project_credit(compact=True)

render_page_header(page, production_health, phase5_meta)


if page == "Overview":
    finished_count = int(
        (
            matches.get(
                "status",
                pd.Series(dtype=str),
            )
            == "FINISHED"
        ).sum()
    ) if not matches.empty else 0

    live_count = int(
        matches.get(
            "status",
            pd.Series(dtype=str),
        ).isin(
            ["IN_PLAY", "PAUSED"]
        ).sum()
    ) if not matches.empty else 0

    upcoming_count = int(
        matches.get(
            "status",
            pd.Series(dtype=str),
        ).isin(
            ["TIMED", "SCHEDULED"]
        ).sum()
    ) if not matches.empty else 0

    top_team = "—"
    top_price = "—"
    champion_probability = "—"

    if not prices.empty:
        leader = prices.sort_values(
            "cupmarket_price",
            ascending=False,
        ).iloc[0]

        top_team = leader["team"]
        top_price = format_number(
            leader["cupmarket_price"]
        )
        champion_probability = (
            format_percent(
                leader["prob_champion"]
            )
            if "prob_champion"
            in leader.index
            else "—"
        )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Finished matches",
        finished_count,
    )
    col2.metric(
        "Live matches",
        live_count,
    )
    col3.metric(
        "Upcoming matches",
        upcoming_count,
    )
    col4.metric(
        "Market leader",
        top_team,
        delta=(
            f"Price {top_price}"
            if top_price != "—"
            else None
        ),
    )

    render_start_here()

    render_section_heading(
        "Market leaders",
        "The highest probability-weighted country values right now.",
        "Market pulse",
    )

    if prices.empty:
        st.info(
            "No market-price file was found."
        )
    else:
        leader_table = prices[
            [
                "market_rank",
                "team",
                "group",
                "cupmarket_price",
                "prob_reach_round_32",
                "prob_reach_quarter_final",
                "prob_reach_final",
                "prob_champion",
            ]
        ].head(12).copy()

        for column in [
            "prob_reach_round_32",
            "prob_reach_quarter_final",
            "prob_reach_final",
            "prob_champion",
        ]:
            leader_table[column] = (
                leader_table[column]
                .map(format_percent)
            )

        leader_table = leader_table.rename(
            columns={
                "market_rank": "Rank",
                "team": "Country",
                "group": "Group",
                "cupmarket_price": "Price",
                "prob_reach_round_32": "Reach R32",
                "prob_reach_quarter_final": "Reach QF",
                "prob_reach_final": "Reach final",
                "prob_champion": "Champion",
            }
        )

        st.dataframe(
            leader_table,
            use_container_width=True,
            hide_index=True,
        )

    render_section_heading(
        "Next matches",
        "Upcoming fixtures and live tournament status.",
        "Match calendar",
    )

    if matches.empty:
        st.info(
            "No match file was found."
        )
    else:
        next_matches = (
            matches[
                matches["status"].isin(
                    [
                        "TIMED",
                        "SCHEDULED",
                        "IN_PLAY",
                        "PAUSED",
                    ]
                )
            ]
            .sort_values("utc_date")
            .head(8)
            .copy()
        )

        if next_matches.empty:
            st.write(
                "No upcoming matches."
            )
        else:
            next_matches["kickoff_utc"] = (
                next_matches["utc_date"]
                .dt.strftime(
                    "%Y-%m-%d %H:%M"
                )
            )
            next_matches["match_stage_label"] = next_matches.apply(
                match_stage_label,
                axis=1,
            )

            next_display = next_matches[
                [
                    "kickoff_utc",
                    "status",
                    "home_team",
                    "away_team",
                    "match_stage_label",
                ]
            ].rename(
                columns={
                    "kickoff_utc": "Kickoff · UTC",
                    "status": "Status",
                    "home_team": "Home",
                    "away_team": "Away",
                    "match_stage_label": "Stage",
                }
            )

            st.dataframe(
                next_display,
                use_container_width=True,
                hide_index=True,
            )

    render_section_heading(
        "How to read the leader",
        "Price combines the value of every possible tournament finish.",
        "Interpretation",
    )
    st.write(
        f"{top_team} currently has the highest "
        f"CupMarket expected value. Its estimated "
        f"championship probability is "
        f"{champion_probability}. The price also "
        f"includes the value of reaching earlier "
        f"knockout stages, so it is not the same "
        f"as championship probability."
    )


elif page == "Match Centre":
    render_section_heading(
        "Fixtures and forecasts",
        "Filter the tournament and compare scores with saved model probabilities.",
        "Match centre",
    )

    render_live_vs_official_note()

    if st.button(
        "Refresh live scores",
        help=(
            "Clears the 60-second cache. "
            "Avoid repeated refreshes because "
            "the API is rate-limited."
        ),
    ):
        st.cache_data.clear()
        st.rerun()

    if matches.empty:
        st.warning(
            "No matches are available."
        )
    else:
        status_options = sorted(
            matches["status"]
            .dropna()
            .unique()
        )

        selected_statuses = st.multiselect(
            "Match status",
            status_options,
            default=status_options,
        )

        filtered = matches[
            matches["status"].isin(
                selected_statuses
            )
        ].copy()

        filtered["kickoff_utc"] = (
            filtered["utc_date"]
            .dt.strftime(
                "%Y-%m-%d %H:%M"
            )
        )

        filtered["score"] = filtered.apply(
            score_text,
            axis=1,
        )
        filtered["match_stage_label"] = filtered.apply(
            match_stage_label,
            axis=1,
        )

        prediction_display = pd.DataFrame()

        if not predictions.empty:
            prediction_display = predictions[
                [
                    "match_id",
                    "expected_home_goals",
                    "expected_away_goals",
                    "prob_home_win",
                    "prob_draw",
                    "prob_away_win",
                    "display_label",
                    "most_likely_score",
                ]
            ].drop_duplicates(
                "match_id",
                keep="last",
            )

            filtered = filtered.merge(
                prediction_display,
                on="match_id",
                how="left",
            )

        display_columns = [
            "kickoff_utc",
            "status",
            "home_team",
            "score",
            "away_team",
            "match_stage_label",
        ]

        for optional in [
            "expected_home_goals",
            "expected_away_goals",
            "prob_home_win",
            "prob_draw",
            "prob_away_win",
            "display_label",
            "most_likely_score",
        ]:
            if optional in filtered.columns:
                display_columns.append(
                    optional
                )

        match_display = filtered[display_columns].copy()

        for probability_column in [
            "prob_home_win",
            "prob_draw",
            "prob_away_win",
        ]:
            if probability_column in match_display.columns:
                match_display[probability_column] = match_display[
                    probability_column
                ].map(format_percent)

        for goals_column in [
            "expected_home_goals",
            "expected_away_goals",
        ]:
            if goals_column in match_display.columns:
                match_display[goals_column] = match_display[
                    goals_column
                ].round(2)

        match_display = match_display.rename(
            columns={
                "kickoff_utc": "Kickoff · UTC",
                "status": "Status",
                "home_team": "Home",
                "score": "Score",
                "away_team": "Away",
                "match_stage_label": "Stage",
                "expected_home_goals": "Home xG",
                "expected_away_goals": "Away xG",
                "prob_home_win": "Home win",
                "prob_draw": "Draw",
                "prob_away_win": "Away win",
                "display_label": "Model view",
                "most_likely_score": "Likely score",
            }
        )

        st.dataframe(
            match_display,
            use_container_width=True,
            hide_index=True,
        )

        if not prediction_display.empty:
            st.caption(
                "Match probabilities are the latest "
                "saved model outputs. Live scores can "
                "refresh every 60 seconds, but the "
                "probabilities update only when the "
                "model pipeline produces a new file."
            )


elif page == "Country Market":
    render_section_heading(
        "Country prices",
        "Prices update after completed matches and a fresh tournament simulation.",
        "Market",
    )

    if prices.empty:
        st.warning(
            "No CupMarket price file was found."
        )
    else:
        market_table = prices.copy()

        if "price_change_percent" in market_table.columns:
            market_table[
                "price_change_percent"
            ] = market_table[
                "price_change_percent"
            ].round(2)

        market_columns = [
            column
            for column in [
                "market_rank",
                "team",
                "group",
                "cupmarket_price",
                "previous_price",
                "price_change",
                "price_change_percent",
                "prob_reach_round_32",
                "prob_reach_quarter_final",
                "prob_reach_final",
                "prob_champion",
            ]
            if column in market_table.columns
        ]
        market_display = market_table[market_columns].copy()

        for probability_column in [
            "prob_reach_round_32",
            "prob_reach_quarter_final",
            "prob_reach_final",
            "prob_champion",
        ]:
            if probability_column in market_display.columns:
                market_display[probability_column] = market_display[
                    probability_column
                ].map(format_percent)

        market_display = market_display.rename(
            columns={
                "market_rank": "Rank",
                "team": "Country",
                "group": "Group",
                "cupmarket_price": "Price",
                "previous_price": "Previous",
                "price_change": "Change",
                "price_change_percent": "Change %",
                "prob_reach_round_32": "Reach R32",
                "prob_reach_quarter_final": "Reach QF",
                "prob_reach_final": "Reach final",
                "prob_champion": "Champion",
            }
        )

        st.dataframe(
            market_display,
            use_container_width=True,
            hide_index=True,
        )

        chart_data = prices.head(
            20
        ).sort_values(
            "cupmarket_price"
        )

        figure = px.bar(
            chart_data,
            x="cupmarket_price",
            y="team",
            orientation="h",
            title=(
                "Top 20 countries by "
                "CupMarket price"
            ),
        )

        polish_figure(figure)
        st.plotly_chart(
            figure,
            use_container_width=True,
        )

        if not price_history.empty:
            selected_teams = st.multiselect(
                "Price-history teams",
                sorted(
                    price_history[
                        "team"
                    ].unique()
                ),
                default=list(
                    prices.head(5)[
                        "team"
                    ]
                ),
            )

            history_filtered = (
                price_history[
                    price_history[
                        "team"
                    ].isin(selected_teams)
                ]
            )

            if not history_filtered.empty:
                history_chart = px.line(
                    history_filtered,
                    x="generated_at_utc",
                    y="cupmarket_price",
                    color="team",
                    markers=True,
                    title=(
                        "CupMarket price history"
                    ),
                )

                st.plotly_chart(
                    history_chart,
                    use_container_width=True,
                )
        else:
            st.info(
                "Price history will appear after "
                "more than one simulation snapshot "
                "has been copied into the app."
            )


elif page == "Team Explorer":
    render_section_heading(
        "Explore a country",
        "See price, stage probabilities and the shape of a country's path.",
        "Country profile",
    )

    if prices.empty:
        st.warning(
            "No tournament probability file "
            "was found."
        )
    else:
        team = st.selectbox(
            "Select a country",
            prices["team"].tolist(),
        )

        team_row = prices[
            prices["team"] == team
        ].iloc[0]

        col1, col2, col3, col4 = st.columns(
            4
        )

        col1.metric(
            "CupMarket price",
            format_number(
                team_row[
                    "cupmarket_price"
                ]
            ),
        )

        col2.metric(
            "Reach Round of 32",
            format_percent(
                team_row[
                    "prob_reach_round_32"
                ]
            ),
        )

        col3.metric(
            "Reach quarter-final",
            format_percent(
                team_row[
                    "prob_reach_quarter_final"
                ]
            ),
        )

        col4.metric(
            "Win tournament",
            format_percent(
                team_row[
                    "prob_champion"
                ]
            ),
        )

        stage_frame = pd.DataFrame(
            {
                "Stage": [
                    "Round of 32",
                    "Round of 16",
                    "Quarter-final",
                    "Semi-final",
                    "Final",
                    "Champion",
                ],
                "Probability": [
                    team_row[
                        "prob_reach_round_32"
                    ],
                    team_row[
                        "prob_reach_round_16"
                    ],
                    team_row[
                        "prob_reach_quarter_final"
                    ],
                    team_row[
                        "prob_reach_semi_final"
                    ],
                    team_row[
                        "prob_reach_final"
                    ],
                    team_row[
                        "prob_champion"
                    ],
                ],
            }
        )

        stage_chart = px.bar(
            stage_frame,
            x="Stage",
            y="Probability",
            title=(
                f"{team}: probability of "
                "reaching each stage"
            ),
        )

        stage_chart.update_yaxes(
            tickformat=".0%"
        )

        polish_figure(stage_chart)
        st.plotly_chart(
            stage_chart,
            use_container_width=True,
        )

        st.subheader("Group-position probabilities")

        group_position_frame = pd.DataFrame(
            {
                "Outcome": [
                    "Finish first",
                    "Finish second",
                    "Finish third",
                    "Qualify as best third",
                ],
                "Probability": [
                    team_row.get(
                        "prob_finish_1st_group",
                        0,
                    ),
                    team_row.get(
                        "prob_finish_2nd_group",
                        0,
                    ),
                    team_row.get(
                        "prob_finish_3rd_group",
                        0,
                    ),
                    team_row.get(
                        "prob_best_third_qualifier",
                        0,
                    ),
                ],
            }
        )

        st.dataframe(
            group_position_frame.assign(
                Probability=group_position_frame[
                    "Probability"
                ].map(format_percent)
            ),
            use_container_width=True,
            hide_index=True,
        )


elif page == "Group Tables":
    render_section_heading(
        "Current standings",
        "Official completed results translated into live group tables.",
        "Groups",
    )

    if group_tables.empty:
        st.warning(
            "No group-table file was found."
        )
    else:
        for group in sorted(
            group_tables["group"].unique()
        ):
            st.subheader(
                f"Group {group}"
            )

            table = (
                group_tables[
                    group_tables[
                        "group"
                    ] == group
                ]
                .sort_values("position")
                .copy()
            )

            group_display = table[
                [
                    "position",
                    "team",
                    "played",
                    "wins",
                    "draws",
                    "losses",
                    "goals_for",
                    "goals_against",
                    "goal_difference",
                    "points",
                ]
            ].rename(
                columns={
                    "position": "Pos",
                    "team": "Country",
                    "played": "P",
                    "wins": "W",
                    "draws": "D",
                    "losses": "L",
                    "goals_for": "GF",
                    "goals_against": "GA",
                    "goal_difference": "GD",
                    "points": "Pts",
                }
            )

            st.dataframe(
                group_display,
                use_container_width=True,
                hide_index=True,
            )


elif page == "Model Health":
    render_section_heading(
        "Production pipeline",
        "Workflow health, freshness and historical evaluation in one place.",
        "Operations",
    )
    health_columns = st.columns(4)
    health_columns[0].metric(
        "Workflow status",
        production_health.get("status", "Unknown"),
    )
    health_columns[1].metric(
        "Last successful run",
        production_health.get("last_success_text", "Never"),
    )
    health_columns[2].metric(
        "Last failed run",
        production_health.get("last_failure_text", "Never"),
    )
    health_columns[3].metric(
        "New matches processed",
        production_health.get("new_matches_processed", 0),
    )

    freshness_columns = st.columns(4)
    freshness_columns[0].metric(
        "Model last refreshed",
        production_health.get("model_generated_text", "Never"),
    )
    freshness_columns[1].metric(
        "Live finished group matches",
        production_health.get("live_finished_group_matches", 0),
    )
    freshness_columns[2].metric(
        "Matches inside model",
        production_health.get("model_finished_group_matches", 0),
    )
    freshness_columns[3].metric(
        "Pending model updates",
        production_health.get("pending_finished_matches", 0),
    )

    if production_health.get("stale"):
        st.error(
            "Data-staleness warning: "
            + "; ".join(production_health.get("reasons", []))
            + "."
        )
    else:
        st.success(
            "The automation is healthy and all currently finished "
            "group-stage matches are included in the model."
        )

    if workflow_health.get("warning"):
        st.warning(
            "GitHub workflow status could not be checked: "
            + workflow_health["warning"]
        )

    latest_run_url = (
        production_health.get("latest_run", {}).get("html_url")
    )
    if latest_run_url:
        st.link_button(
            "Open latest GitHub Actions run",
            latest_run_url,
        )

    st.caption(
        "The workflow-status check is cached for five minutes. "
        "A model refresh is considered behind when the live API shows "
        "more completed group matches than the saved simulation contains."
    )

    if phase3_eval:
        st.subheader(
            "Historical holdout performance"
        )

        metrics = [
            (
                "Outcome accuracy",
                phase3_eval.get(
                    "outcome_accuracy"
                ),
                "percent",
            ),
            (
                "Log loss",
                phase3_eval.get(
                    "outcome_log_loss"
                ),
                "number",
            ),
            (
                "Brier score",
                phase3_eval.get(
                    "outcome_multiclass_brier"
                ),
                "number",
            ),
            (
                "Exact-score accuracy",
                phase3_eval.get(
                    "exact_score_accuracy"
                ),
                "percent",
            ),
        ]

        columns = st.columns(4)

        for column, (
            label,
            value,
            format_type,
        ) in zip(columns, metrics):
            if value is None:
                displayed = "—"
            elif format_type == "percent":
                displayed = format_percent(
                    value
                )
            else:
                displayed = format_number(
                    value,
                    digits=4,
                )

            column.metric(
                label,
                displayed,
            )

    if phase4_eval:
        st.subheader(
            "Live published-prediction scorecard"
        )

        eligible = phase4_eval.get(
            "eligible_completed_predictions",
            0,
        )

        st.write(
            "Eligible completed predictions:",
            eligible,
        )

        if eligible:
            st.json(phase4_eval)
        else:
            st.info(
                phase4_eval.get(
                    "message",
                    "No eligible live results yet.",
                )
            )

    if phase5_meta:
        st.subheader(
            "Tournament simulation"
        )

        simulation_columns = st.columns(
            4
        )

        simulation_columns[0].metric(
            "Simulations",
            f"{phase5_meta.get('number_of_simulations', 0):,}",
        )

        simulation_columns[1].metric(
            "Finished group matches",
            phase5_meta.get(
                "finished_group_matches",
                0,
            ),
        )

        simulation_columns[2].metric(
            "Remaining group matches",
            phase5_meta.get(
                "remaining_group_matches",
                0,
            ),
        )

        simulation_columns[3].metric(
            "Runtime",
            (
                f"{phase5_meta.get('simulation_seconds', 0):.1f}s"
            ),
        )

        st.write(
            "**Bracket mode:**",
            phase5_meta.get(
                "bracket_mode",
                "Unknown",
            ),
        )

        limitations = phase5_meta.get(
            "limitations",
            [],
        )

        if limitations:
            st.write("**Known limitations:**")
            for limitation in limitations:
                st.write(
                    f"- {limitation}"
                )


elif page == "How It Works":
    render_section_heading(
        "From data to price",
        "The complete path from a final whistle to a new CupMarket value.",
        "Method",
    )

    st.markdown(
        """
### Data layer

Historical international results build the original ratings and goal models.  
The football API supplies fixtures, statuses, and scores.

### Frozen baseline

The pre-tournament model remains unchanged. It records what the system believed before the tournament.

### Live state

After a match finishes, the live updater changes Elo ratings and recent attacking, defensive, and points form. It then creates new probabilities for future matches.

### Tournament simulator

Completed results are treated as facts. Remaining matches are simulated thousands of times. The engine builds group tables, selects the best third-placed teams, and simulates the knockout rounds.

### Country price

A country receives different settlement values depending on where it exits the tournament. Its current price is the probability-weighted value of all those possible outcomes.

### During a live match

- Refreshing a live page requests the latest score state from the API.
- Match Intelligence compares the current-score projection with the original pre-match forecast.
- Qualification Lab switches to provisional standings and in-play qualification estimates.
- Live Group Centre follows simultaneous matches and shows what the next goal could change.

### After the final whistle

The official Elo ratings, tournament probabilities and country prices update after the automated model pipeline processes the completed match. Live estimates are clearly separated from the official market.
        """
    )

    st.warning(
        "CupMarket is a virtual analytics game. "
        "It does not accept real-money wagers."
    )

render_project_footer()
