from pathlib import Path
import json

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


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    for column in ["utc_date", "generated_at_utc", "last_updated"]:
        if column in frame.columns:
            frame[column] = pd.to_datetime(
                frame[column], errors="coerce", utc=True
            )
    return frame


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


matches, score_metadata = load_matches(
    data_dir / "world_cup_2026_matches_latest.csv"
)
latest_predictions = read_csv(
    data_dir / "world_cup_live_predictions_latest.csv"
)
prediction_ledger = read_csv(
    root / "backend" / "state" / "world_cup_prediction_ledger.csv"
)
prices = read_csv(data_dir / "cupmarket_prices_latest.csv")
model_metadata = read_json(data_dir / "phase5_simulation_metadata.json")
predictions = combine_prediction_sources(
    latest_predictions,
    prediction_ledger,
)
freshness = group_freshness(matches, model_metadata)
live_count = (
    int(matches["status"].isin(LIVE_STATUSES).sum())
    if not matches.empty and "status" in matches.columns
    else 0
)
live_status_text = (
    f"{live_count} live match{'es' if live_count != 1 else ''}"
    if live_count
    else "No match live"
)
live_status_class = "updating" if live_count else "attention"
hero_description = (
    "Live matches are active. Open one to follow the changing match outlook, "
    "qualification picture, connected group effects and published-market context."
    if live_count
    else "No match is live right now. Open the next fixture for its pre-match forecast "
    "or review the latest result while waiting for official market repricing."
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

render_page_guide(
    "Useful before, during and after the match",
    "The Match Room changes with the match state instead of becoming an empty live-only page.",
    [
        ("Before kickoff", "Read the forecast and test qualification outcomes."),
        ("During play", "Follow live outlook, group effects and market pressure."),
        ("After full time", "Review the result and see when official repricing catches up."),
    ],
)
render_live_vs_official_note()

source_columns = st.columns(4)
source_columns[0].metric("Score source", score_metadata.get("source", "Unknown"))
source_columns[1].metric(
    "Score feed refreshed",
    format_source_time(score_metadata.get("fetched_at_utc")),
)
source_columns[2].metric(
    "Model generated",
    format_source_time(model_metadata.get("generated_at_utc")),
)
source_columns[3].metric(
    "Results awaiting model",
    freshness["pending_model_updates"],
)

if score_metadata.get("warning"):
    st.warning(
        score_metadata["warning"]
        + " The page has safely fallen back to the latest GitHub snapshot."
    )

if freshness["pending_model_updates"]:
    pending = freshness["pending_model_updates"]
    st.warning(
        f"{pending} completed group match"
        + ("es are" if pending != 1 else " is")
        + " already visible in the score feed but not yet reflected in the "
        "published model probabilities. Final scores and provisional tables are current; "
        "official probabilities and prices will catch up after the next successful model run."
    )
else:
    st.success(
        "The score feed and published group-stage model are currently aligned."
    )

render_match_experience(matches, predictions, prices)
render_project_footer()
