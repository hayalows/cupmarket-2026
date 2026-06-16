from __future__ import annotations

from pathlib import Path
import time

import pandas as pd
import streamlit as st

from features.live_match_data import load_matches
from features.match_ui import combine_prediction_sources
from features.official_bundle import load_consistent_official_bundle


def load_page_data(root: Path) -> dict:
    started = time.perf_counter()
    data = root / "data"
    state = root / "backend" / "state"
    matches, source = load_matches(data / "world_cup_2026_matches_latest.csv")
    official = load_consistent_official_bundle(
        csv_paths={
            "latest_predictions": data / "world_cup_live_predictions_latest.csv",
            "prediction_ledger": state / "world_cup_prediction_ledger.csv",
            "prices": data / "cupmarket_prices_latest.csv",
        },
        json_paths={
            "metadata": data / "phase5_simulation_metadata.json",
        },
    )
    predictions = combine_prediction_sources(
        official["latest_predictions"],
        official["prediction_ledger"],
    )
    prices = official["prices"]
    strength = (
        dict(zip(prices["team"], prices["cupmarket_price"]))
        if not prices.empty else {}
    )
    return {
        "matches": matches,
        "source": source,
        "predictions": predictions,
        "prices": prices,
        "metadata": official["metadata"],
        "strength": strength,
        "load_time_ms": (time.perf_counter() - started) * 1000,
    }


def render_header(source: dict, metadata: dict) -> None:
    st.markdown(
        '''
        <div class="cm-hero">
            <div class="cm-eyebrow">CupMarket 2026 · Live group intelligence</div>
            <h1>If the matches ended now.</h1>
            <p>Pick a country first. CupMarket finds its group, linked fixtures and provisional table, then adds a full-time projection when a match is live.</p>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def render_matches(context: dict) -> None:
    st.subheader(f'Group {context["group"]} live picture')
    live_matches = context["live_matches"]
    if not live_matches:
        st.caption("No match in this group is currently in play.")
        return
    columns = st.columns(len(live_matches))
    for column, match in zip(columns, live_matches):
        minute = pd.to_numeric(match.get("minute"), errors="coerce")
        clock = f"{int(minute)} min" if pd.notna(minute) else "LIVE"
        column.metric(
            f'{match["home_team"]} vs {match["away_team"]}',
            f'{match["home_score"]}-{match["away_score"]}',
            clock,
        )
    st.info(
        "Current live scores are treated as final only for this provisional view."
    )
