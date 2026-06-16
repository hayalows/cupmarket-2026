from __future__ import annotations

from pathlib import Path

import streamlit as st

from features.group_centre import load_page_data, render_header, render_matches
from features.live_context import team_context
from features.live_group_view import render_projection, render_provisional
from features.live_match_data import format_source_time, group_freshness
from features.product_ui import (
    render_data_diagnostics,
    render_live_feed_notice,
    render_live_vs_official_note,
    render_official_data_caption,
    render_page_guide,
)


def render_page(root: Path, data: dict | None = None) -> None:
    page_data = data or load_page_data(root)
    matches = page_data["matches"]
    predictions = page_data["predictions"]
    strength = page_data["strength"]
    metadata = page_data["metadata"]
    source = page_data["source"]
    freshness = group_freshness(matches, metadata)

    render_header(source, metadata)
    render_live_feed_notice(source)

    if matches.empty:
        st.warning("No group-stage match data is available.")
        return

    group_rows = matches[
        (matches["stage"] == "GROUP_STAGE")
        & matches["home_team"].notna()
        & matches["away_team"].notna()
    ]
    teams = sorted(set(group_rows["home_team"]).union(set(group_rows["away_team"])))

    team = st.selectbox("Select a country", teams)
    context = team_context(matches, predictions, team, strength)
    render_matches(context)
    render_provisional(context)

    if context["live_matches"]:
        st.subheader("What is likely by full time?")
        render_projection(matches, predictions, team, strength)
    else:
        st.info(
            "No match in this group is live. The provisional table reflects completed "
            "results, and the full-time projection will activate automatically during play."
        )

    render_page_guide(
        "Follow the group as one connected system",
        "Use this page when two fixtures can change the same table at once.",
        [
            ("Pick", "Choose a country and CupMarket finds its group."),
            ("Read", "See linked fixtures and the provisional table."),
            ("Project", "Estimate the final group outcome during live play."),
        ],
    )
    render_live_vs_official_note()
    render_data_diagnostics(
        score_source=source.get("source", "Unknown"),
        score_refreshed=format_source_time(source.get("fetched_at_utc")),
        model_generated=format_source_time(metadata.get("generated_at_utc")),
        pending_updates=freshness["pending_model_updates"],
        technical_details=source.get("technical_warning"),
        load_time_ms=page_data.get("load_time_ms"),
        refresh_key="group_centre_refresh_scores",
        token_configured=source.get("token_configured"),
        feed_state=source.get("feed_state"),
        requests_remaining=source.get("requests_remaining"),
    )
    render_official_data_caption(page_data["prices"])

    st.caption(
        "This page is a live interpretation layer. Official Elo ratings, tournament "
        "probabilities and country prices update after completed results are processed."
    )
