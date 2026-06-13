from __future__ import annotations

from pathlib import Path
import json

import pandas as pd
import plotly.express as px
import streamlit as st

from features.live_context import team_context
from features.live_match_data import format_source_time, load_matches
from features.match_ui import combine_prediction_sources
from features.team_projection import project_team

st.set_page_config(
    page_title="CupMarket Live Group Centre",
    page_icon="◉",
    layout="wide",
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

for stylesheet in [ROOT / "assets" / "product.css", ROOT / "assets" / "group_tools.css"]:
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
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def percent(value: float) -> str:
    return f"{100 * float(value):.1f}%"


def table_view(rows: list[dict]) -> pd.DataFrame:
    columns = [
        "position", "team", "played", "wins", "draws", "losses",
        "goal_difference", "points",
    ]
    return pd.DataFrame(rows)[columns].rename(
        columns={
            "position": "Pos", "team": "Country", "played": "P",
            "wins": "W", "draws": "D", "losses": "L",
            "goal_difference": "GD", "points": "Pts",
        }
    )


matches, source = load_matches(DATA / "world_cup_2026_matches_latest.csv")
latest_predictions = read_csv(DATA / "world_cup_live_predictions_latest.csv")
ledger = read_csv(
    ROOT / "backend" / "state" / "world_cup_prediction_ledger.csv"
)
predictions = combine_prediction_sources(latest_predictions, ledger)
prices = read_csv(DATA / "cupmarket_prices_latest.csv")
metadata = read_json(DATA / "phase5_simulation_metadata.json")
strength = (
    dict(zip(prices["team"], prices["cupmarket_price"]))
    if not prices.empty else {}
)

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026 · Live group intelligence</div>
        <h1>If the matches ended now.</h1>
        <p>Follow simultaneous group matches, provisional standings and a current-score qualification projection.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)

source_columns = st.columns(3)
source_columns[0].metric("Score source", source.get("source", "Unknown"))
source_columns[1].metric(
    "Score feed refreshed", format_source_time(source.get("fetched_at_utc"))
)
source_columns[2].metric(
    "Published model", format_source_time(metadata.get("generated_at_utc"))
)

if st.button("Refresh live scores"):
    st.cache_data.clear()
    st.rerun()

if source.get("warning"):
    st.warning(source["warning"] + " Showing the latest saved snapshot instead.")
