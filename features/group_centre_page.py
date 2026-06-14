from __future__ import annotations

from pathlib import Path

import streamlit as st

from features.group_centre import load_page_data, render_header, render_matches
from features.live_context import team_context
from features.live_group_view import render_projection, render_provisional
from features.live_match_data import format_source_time, group_freshness
import features.product_ui as product_ui
from features.product_ui import (
    render_live_vs_official_note,
    render_page_guide,
)


def render_data_diagnostics_compat(
    *,
    score_source: str,
    score_refreshed: str,
    model_generated: str,
    pending_updates: int | None = None,
    load_time_ms: float | None = None,
    refresh_key: str | None = None,
) -> None:
    helper = getattr(product_ui, "render_data_diagnostics", None)
    if callable(helper):
        helper(
            score_source=score_source,
            score_refreshed=score_refreshed,
            model_generated=model_generated,
            pending_updates=pending_updates,
            load_time_ms=load_time_ms,
            refresh_key=refresh_key,
        )
        return

    pending_text = (
        f" · {pending_updates} result{'s' if pending_updates != 1 else ''} awaiting model"
        if pending_updates is not None
        else ""
    )
    st.caption(
        f"Scores refreshed {score_refreshed} · Published model {model_generated}"
        f"{pending_text}"
    )
    with st.expander("Data freshness and system details", expanded=False):
        columns = st.columns(4 if pending_updates is not None else 3)
        columns[0].metric("Score source", score_source)
        columns[1].metric("Score feed refreshed", score_refreshed)
        columns[2].metric("Model generated", model_generated)
        if pending_updates is not None:
            columns[3].metric("Results awaiting model", pending_updates)
        if load_time_ms is not None:
            st.caption(f"Page data prepared in {load_time_ms:.0f} ms on this rerun.")
        if refresh_key and st.button(
            "Refresh live scores",
            key=refresh_key,
            help="Clears the score cache and requests the latest match states.",
        ):
            st.cache_data.clear()
            st.rerun()


def render_page(root: Path) -> None:
    data = load_page_data(root)
    matches = data["matches"]
    predictions = data["predictions"]
    strength = data["strength"]
    metadata = data["metadata"]
    source = data["source"]
    freshness = group_freshness(matches, metadata)

    render_header(source, metadata)

    if source.get("warning"):
        st.warning(
            source["warning"]
            + " The latest saved GitHub snapshot is being used instead."
        )

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
    render_data_diagnostics_compat(
        score_source=source.get("source", "Unknown"),
        score_refreshed=format_source_time(source.get("fetched_at_utc")),
        model_generated=format_source_time(metadata.get("generated_at_utc")),
        pending_updates=freshness["pending_model_updates"],
        load_time_ms=data.get("load_time_ms"),
        refresh_key="group_centre_refresh_scores",
    )

    st.caption(
        "This page is a live interpretation layer. Official Elo ratings, tournament "
        "probabilities and country prices update after completed results are processed."
    )
