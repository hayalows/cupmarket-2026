from __future__ import annotations

import pandas as pd
import streamlit as st

import features.match_hub as base
from features.live_match_data import format_source_time, load_matches
from features.product_ui import render_live_feed_notice
from features.tournament_data import DATA_DIR, load_static_data


def inject_styles() -> None:
    base.inject_styles()


def load_match_hub_data() -> dict:
    matches, source = load_matches(DATA_DIR / "world_cup_2026_matches_latest.csv")
    return {
        "matches": matches,
        "source": source,
        "static": load_static_data(),
    }


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
                "Open match intelligence",
                key=f"hub_v2_live_{int(match['match_id'])}",
                use_container_width=True,
            ):
                base._open_match_room(int(match["match_id"]))


def _render_results_safe(
    matches: pd.DataFrame,
    static: dict[str, pd.DataFrame],
) -> None:
    finished = (
        matches[matches["status"].isin(base.FINISHED_STATUSES)]
        .copy()
        .sort_values("utc_date", ascending=False)
    )
    prediction_ledger = static["prediction_ledger"]
    processed = static["processed_ledger"]
    history = static["history"]

    verified = 0
    correct = 0
    for row in finished.itertuples(index=False):
        match = pd.Series(row._asdict())
        prediction, source = base.reference_prediction(prediction_ledger, match)
        if source == "Saved pre-match forecast" and not prediction.empty:
            verified += 1
            correct += int(
                base._prediction_outcome(prediction) == base.actual_outcome(match)
            )

    summary = st.columns(3)
    summary[0].metric("Completed matches", len(finished))
    summary[1].metric("Verified pre-match records", verified)
    summary[2].metric(
        "Leading-outcome accuracy",
        f"{100 * correct / verified:.1f}%" if verified else "—",
    )
    if verified < 10:
        st.caption(
            "Early sample: performance measures can change materially as more verified matches are completed."
        )

    if finished.empty:
        st.info("No completed matches yet.")
        return

    countries = sorted(set(finished["home_team"]).union(set(finished["away_team"])))
    groups = sorted(finished["group"].dropna().astype(str).unique())
    with st.popover("Filter results", use_container_width=True):
        country = st.selectbox(
            "Country",
            ["All countries", *countries],
            key="match_hub_results_country",
        )
        group = st.selectbox(
            "Group",
            ["All groups", *groups],
            key="match_hub_results_group",
        )

    filtered = finished.copy()
    if country != "All countries":
        filtered = filtered[
            (filtered["home_team"] == country)
            | (filtered["away_team"] == country)
        ]
    if group != "All groups":
        filtered = filtered[filtered["group"].astype(str) == group]

    if filtered.empty:
        st.info(
            "No completed match meets both selected filters. Change the country or group filter."
        )
        return

    review_table, match_ids = base._finished_review_rows(
        filtered,
        prediction_ledger,
    )
    event = st.dataframe(
        review_table,
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key="match_hub_results_table_v2",
    )
    selected_rows = getattr(getattr(event, "selection", None), "rows", [])
    requested = st.session_state.pop("cupmarket_match_hub_match_id", None)
    selected_id = (
        requested
        if requested in match_ids
        else st.session_state.get("match_hub_selected_result")
    )
    if selected_rows:
        row_index = int(selected_rows[0])
        if 0 <= row_index < len(match_ids):
            selected_id = match_ids[row_index]
    if selected_id not in match_ids:
        selected_id = match_ids[0]

    st.session_state["match_hub_selected_result"] = int(selected_id)
    selected_rows_frame = filtered[filtered["match_id"] == int(selected_id)]
    if selected_rows_frame.empty:
        st.info("The selected result is no longer available under the current filters.")
        return
    base._render_result_detail(
        selected_rows_frame.iloc[0],
        prediction_ledger,
        processed,
        history,
    )


def render_match_hub(data: dict | None = None) -> None:
    page_data = data or load_match_hub_data()
    matches = page_data["matches"]
    source = page_data["source"]
    static = page_data["static"]

    st.markdown(
        '''
        <div class="cm-hero">
            <div class="cm-eyebrow">CupMarket 2026 · Fixtures & results</div>
            <h1>Every match, one clear path.</h1>
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
    render_live_feed_notice(source)

    if view == "Live":
        _render_live_safe(matches)
    elif view == "Results":
        _render_results_safe(matches, static)
    else:
        base._render_upcoming(matches, static)
