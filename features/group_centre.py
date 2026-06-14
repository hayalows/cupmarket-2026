from __future__ import annotations

from pathlib import Path
import json
import time

import pandas as pd
import streamlit as st

from features.live_match_data import load_matches
from features.match_ui import combine_prediction_sources


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
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def cached_csv(path: Path) -> pd.DataFrame:
    return read_csv(str(path), file_version(path))


def cached_json(path: Path) -> dict:
    return read_json(str(path), file_version(path))


def load_page_data(root: Path) -> dict:
    started = time.perf_counter()
    data = root / "data"
    matches, source = load_matches(data / "world_cup_2026_matches_latest.csv")
    latest = cached_csv(data / "world_cup_live_predictions_latest.csv")
    ledger = cached_csv(
        root / "backend" / "state" / "world_cup_prediction_ledger.csv"
    )
    predictions = combine_prediction_sources(latest, ledger)
    prices = cached_csv(data / "cupmarket_prices_latest.csv")
    metadata = cached_json(data / "phase5_simulation_metadata.json")
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
