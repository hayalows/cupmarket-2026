from __future__ import annotations

from pathlib import Path
import json

import pandas as pd
import streamlit as st

from features.live_context import team_context
from features.live_group_view import render_projection, render_provisional
from features.live_match_data import format_source_time, load_matches
from features.match_ui import combine_prediction_sources


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


def load_page_data(root: Path) -> dict:
    data = root / "data"
    matches, source = load_matches(data / "world_cup_2026_matches_latest.csv")
    latest = read_csv(data / "world_cup_live_predictions_latest.csv")
    ledger = read_csv(
        root / "backend" / "state" / "world_cup_prediction_ledger.csv"
    )
    predictions = combine_prediction_sources(latest, ledger)
    prices = read_csv(data / "cupmarket_prices_latest.csv")
    metadata = read_json(data / "phase5_simulation_metadata.json")
    strength = (
        dict(zip(prices["team"], prices["cupmarket_price"]))
        if not prices.empty else {}
    )
    return {
        "matches": matches,
        "source": source,
        "predictions": predictions,
        "prices": prices,
        "metadata": metadata,
        "strength": strength,
    }


def render_header(source: dict, metadata: dict) -> None:
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
    columns = st.columns(3)
    columns[0].metric("Score source", source.get("source", "Unknown"))
    columns[1].metric(
        "Score feed refreshed", format_source_time(source.get("fetched_at_utc"))
    )
    columns[2].metric(
        "Published model", format_source_time(metadata.get("generated_at_utc"))
    )
    if st.button("Refresh live scores"):
        st.cache_data.clear()
        st.rerun()
    if source.get("warning"):
        st.warning(source["warning"] + " Showing the latest saved snapshot instead.")
