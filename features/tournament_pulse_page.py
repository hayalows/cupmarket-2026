from __future__ import annotations

import streamlit as st

from features.live_match_data import (
    format_source_time,
    load_matches,
    should_auto_refresh,
)
from features.overview_v3 import render_overview_v3
from features.product_ui import render_live_feed_notice
from features.tournament_data import DATA_DIR, load_static_data


def load_pulse_data() -> dict:
    matches, score_metadata = load_matches(
        DATA_DIR / "world_cup_2026_matches_latest.csv"
    )
    return {
        "matches": matches,
        "score_metadata": score_metadata,
        "prices": load_static_data()["prices"],
    }


def render_pulse(data: dict, refresh_label: str) -> None:
    matches = data["matches"]
    score_metadata = data["score_metadata"]

    st.markdown(
        '''
        <div class="cm-hero">
            <div class="cm-eyebrow">CupMarket 2026 · Tournament pulse</div>
            <h1>See what happened. Open what matters.</h1>
            <p>Results, live matches, upcoming fixtures and country-market movement now connect directly to the detail that explains them.</p>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    render_live_feed_notice(score_metadata)
    render_overview_v3(matches=matches, prices=data["prices"], metadata={})
    st.caption(
        f"Score source: {score_metadata.get('source', 'Unknown')} · refreshed "
        f"{format_source_time(score_metadata.get('fetched_at_utc'))} · "
        f"{refresh_label}"
    )
    if score_metadata.get("reconciliation_note"):
        st.caption(score_metadata["reconciliation_note"])


@st.fragment(run_every="45s")
def render_active_pulse() -> None:
    data = load_pulse_data()
    if not should_auto_refresh(data["matches"]):
        st.rerun()
    render_pulse(data, "live checks every 45 seconds")


@st.fragment(run_every="5m")
def render_idle_pulse() -> None:
    data = load_pulse_data()
    if should_auto_refresh(data["matches"]):
        st.rerun()
    render_pulse(data, "next check in five minutes")


def render_tournament_pulse_page() -> None:
    initial_data = load_pulse_data()
    if should_auto_refresh(initial_data["matches"]):
        render_active_pulse()
    else:
        render_idle_pulse()
