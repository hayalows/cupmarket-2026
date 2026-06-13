from pathlib import Path
import json

import pandas as pd
import streamlit as st

from features.live_match_data import (
    format_source_time,
    group_freshness,
    load_matches,
)
from features.match_ui import combine_prediction_sources
from features.qualification_ui import render_qualification_lab

st.set_page_config(
    page_title="CupMarket Qualification Lab",
    page_icon="◇",
    layout="wide",
)

root = Path(__file__).resolve().parents[1]
data_dir = root / "data"

for stylesheet in [
    root / "assets" / "product.css",
    root / "assets" / "group_tools.css",
]:
    if stylesheet.exists():
        st.markdown(
            f"<style>{stylesheet.read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True,
        )


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
group_tables = read_csv(data_dir / "current_group_tables.csv")
model_metadata = read_json(data_dir / "phase5_simulation_metadata.json")
predictions = combine_prediction_sources(
    latest_predictions,
    prediction_ledger,
)
freshness = group_freshness(matches, model_metadata)

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026 · Qualification scenarios</div>
        <h1>What does the next result change?</h1>
        <p>Live results set the current table. The latest published model forecasts the matches still to come.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)

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

if st.button(
    "Refresh live score feed",
    help="Clears the 60-second score cache and requests the latest match states.",
):
    st.cache_data.clear()
    st.rerun()

if score_metadata.get("warning"):
    st.warning(
        score_metadata["warning"]
        + " The page has safely fallen back to the latest GitHub snapshot."
    )

render_qualification_lab(
    matches,
    predictions,
    prices,
    group_tables,
    {"pending_finished_matches": freshness["pending_model_updates"]},
)
