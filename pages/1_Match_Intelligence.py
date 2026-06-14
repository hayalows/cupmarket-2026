from pathlib import Path
import json
import time

import pandas as pd
import streamlit as st

from backend.live_qualification import LIVE_STATUSES
from features.live_match_data import (
    format_source_time,
    group_freshness,
    load_matches,
)
from features.live_match_experience import render_match_experience
from features.match_ui import combine_prediction_sources
from features.product_ui import (
    inject_styles,
    render_data_diagnostics,
    render_live_vs_official_note,
    render_page_guide,
    render_project_footer,
    render_specialist_sidebar,
)

st.set_page_config(
    page_title="CupMarket Live Match Room",
    page_icon="⚽",
    layout="wide",
)

root = Path(__file__).resolve().parents[1]
data_dir = root / "data"

inject_styles(root)
render_specialist_sidebar("match")


def file_version(path: Path) -> int:
    return path.stat().st_mtime_ns if path.exists() else 0


@st.cache_data(show_spinner=False)
def read_csv(path_text: str, version: int) -> pd.DataFrame:
    path = Path(path_text)
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    for column in ["utc_date", "generated_at_utc", "last_updated"]:
        if column in frame.columns:
            frame[column] = pd.to_datetime(
                frame[column], errors="coerce", utc=True
            )
    return frame


@st.cache_data(show_spinner=False)
def read_json(path_text: str, version: int) -> dict:
    path = Path(path_text)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def cached_csv(path: Path) -> pd.DataFrame:
    return read_csv(str(path), file_version(path))


def cached_json(path: Path) -> dict:
    return read_json(str(path), file_version(path))


load_started = time.perf_counter()
matches, score_metadata = load_matches(
    data_dir / "world_cup_2026_matches_latest.csv"
)
latest_predictions = cached_csv(
    data_dir / "world_cup_live_predictions_latest.csv"
)
prediction_ledger = cached_csv(
    root / "backend" / "state" / "world_cup_prediction_ledger.csv"
)
prices = cached_csv(data_dir / "cupmarket_prices_latest.csv")
model_metadata = cached_json(data_dir / "phase5_simulation_metadata.json")
predictions = combine_prediction_sources(
    latest_predictions,
    prediction_ledger,
)
freshness = group_freshness(matches, model_metadata)
load_time_ms = (time.perf_counter() - load_started) * 1000
live_count = (
    int(matches["status"].isin(LIVE_STATUSES).sum())
    if not matches.empty and "status" in matches.columns
    else 0
)
live_status_text = (
    f"{live_count} live match{'es' if live_count != 1 else ''}"
    if live_count
    else "Forecast mode"
)
live_status_class = "updating" if live_count else "attention"
hero_description = (
    "Live matches are active. Open one to follow the changing match outlook, "
    "qualification picture, connected group effects and published-market context."
    if live_count
    else "No match is live right now. The next fixture is selected below for immediate "
    "forecast access, and the latest completed result is one tap away."
)

st.markdown(
    f'''
    <div class="cm-hero">
        <div class="cm-hero-top">
            <div class="cm-eyebrow">CupMarket 2026 · Match intelligence</div>
            <div class="cm-status {live_status_class}">
                <span class="cm-dot"></span>{live_status_text}
            </div>
        </div>
        <h1>Open the match. Understand the consequences.</h1>
        <p>{hero_description}</p>
    </div>
    ''',
    unsafe_allow_html=True,
)

if score_metadata.get("warning"):
    st.warning(
        score_metadata["warning"]
        + " The latest saved GitHub snapshot is being used instead."
    )

if freshness["pending_model_updates"]:
    pending = freshness["pending_model_updates"]
    st.warning(
        f"{pending} completed group match"
        + ("es are" if pending != 1 else " is")
        + " visible in the score feed but not yet reflected in official probabilities "
        "and prices. Final scores are current; published market values update after the "
        "next successful model run."
    )

# Primary user task appears before onboarding and operational telemetry.
render_match_experience(matches, predictions, prices)

render_page_guide(
    "Useful before, during and after the match",
    "The Match Room adapts to the real match state.",
    [
        ("Before kickoff", "Read the forecast and test qualification outcomes."),
        ("During play", "Follow live outlook, group effects and market pressure."),
        ("After full time", "Review the result and wait for official repricing."),
    ],
)
render_live_vs_official_note()
render_data_diagnostics(
    score_source=score_metadata.get("source", "Unknown"),
    score_refreshed=format_source_time(score_metadata.get("fetched_at_utc")),
    model_generated=format_source_time(model_metadata.get("generated_at_utc")),
    pending_updates=freshness["pending_model_updates"],
    warning=(
        score_metadata.get("warning")
        + " Showing the latest saved GitHub snapshot."
        if score_metadata.get("warning")
        else None
    ),
    load_time_ms=load_time_ms,
    refresh_key="match_room_refresh_scores",
)
render_project_footer()
