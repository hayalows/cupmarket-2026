from __future__ import annotations

from pathlib import Path

import streamlit as st

from features.group_centre import load_page_data, render_header, render_matches
from features.live_context import team_context
from features.live_group_view import render_projection, render_provisional


def render_page(root: Path) -> None:
    data = load_page_data(root)
    matches = data["matches"]
    predictions = data["predictions"]
    strength = data["strength"]
    render_header(data["source"], data["metadata"])

    if matches.empty:
        st.warning("No group-stage match data is available.")
        return

    group_rows = matches[
        (matches["stage"] == "GROUP_STAGE")
        & matches["home_team"].notna()
        & matches["away_team"].notna()
    ]
    teams = sorted(
        set(group_rows["home_team"]).union(set(group_rows["away_team"]))
    )
    team = st.selectbox("Select a country", teams)
    context = team_context(matches, predictions, team, strength)
    render_matches(context)
    render_provisional(context)

    if context["live_matches"]:
        st.subheader("What is likely by full time?")
        render_projection(matches, predictions, team, strength)
    else:
        st.info(
            "The live projection becomes available when a group-stage match is in play."
        )

    st.caption(
        "This is a separate live interpretation layer. The trained model, Elo ratings, "
        "20,000-simulation market and country prices update only after a final result."
    )
