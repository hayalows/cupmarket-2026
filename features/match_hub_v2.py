from __future__ import annotations

import pandas as pd
import streamlit as st

import features.match_hub as base
from features.live_match_data import format_source_time, load_matches
from features.tournament_data import DATA_DIR, load_static_data


def inject_styles() -> None:
    base.inject_styles()


def _open_upcoming(match_id: int) -> None:
    st.session_state["cupmarket_match_hub_view"] = "Upcoming"
    st.session_state["cupmarket_match_hub_match_id"] = int(match_id)


def _render_live_safe(matches: pd.DataFrame) -> None:
    live = matches[matches["status"].isin(base.LIVE_STATUSES)].copy().sort_values("utc_date")
    if live.empty:
        upcoming = matches[matches["status"].isin(base.UPCOMING_STATUSES)].copy().sort_values("utc_date")
        st.info("No match is live. The next fixture is ready in Upcoming.")
        if not upcoming.empty:
            next_id = int(upcoming.iloc[0]["match_id"])
            st.button(
                "Open next fixture",
                type="primary",
                use_container_width=True,
                on_click=_open_upcoming,
                args=(next_id,),
            )
        return

    for row in live.itertuples(index=False):
        match = pd.Series(row._asdict())
        minute = pd.to_numeric(match.get("minute"), errors="coerce")
        clock = (
            "HT"
            if str(match.get("status")) == "PAUSED"
            else (f"{int(minute)}'" if pd.notna(minute) else "LIVE")
        )
        with st.container(border=True):
            st.markdown(
                f"**{match.get('home_team')} {base._score(match)} {match.get('away_team')}**"
            )
            st.caption(f"{clock} · {base._group(match.get('group'))}")
            if st.button(
                "Open live intelligence",
                key=f"hub_v2_live_{int(match['match_id'])}",
                use_container_width=True,
            ):
                base._open_match_room(int(match["match_id"]))


def render_match_hub() -> None:
    matches, source = load_matches(DATA_DIR / "world_cup_2026_matches_latest.csv")
    static = load_static_data()

    st.markdown(
        '''
        <div class="cm-hero">
            <div class="cm-eyebrow">CupMarket 2026 · Match Hub</div>
            <h1>Every match, one consistent path.</h1>
            <p>Move from live action to completed-result review or the next fixture without learning a different navigation system.</p>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    requested = st.session_state.pop("cupmarket_match_hub_view", None)
    options = ["Live", "Results", "Upcoming"]
    default = (
        "Live"
        if not matches.empty and matches["status"].isin(base.LIVE_STATUSES).any()
        else "Results"
    )
    if requested in options:
        st.session_state["match_hub_view_control"] = requested
    elif st.session_state.get("match_hub_view_control") not in options:
        st.session_state["match_hub_view_control"] = default

    view = st.segmented_control(
        "Match view",
        options,
        key="match_hub_view_control",
        selection_mode="single",
    ) or default

    st.caption(
        f"Score source: {source.get('source', 'Unknown')} · refreshed "
        f"{format_source_time(source.get('fetched_at_utc'))}"
    )
    if source.get("warning"):
        st.warning(source["warning"] + " Showing the latest saved snapshot.")

    if view == "Live":
        _render_live_safe(matches)
    elif view == "Results":
        base._render_results(matches, static)
    else:
        base._render_upcoming(matches, static)
