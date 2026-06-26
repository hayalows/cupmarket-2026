import pandas as pd
import streamlit as st

from features.bracket_view import (
    STAGE_ALIASES,
    _confirmed_source,
    _projected_round32,
    _render_confirmed_cards,
    _render_projected_r32,
    _render_stage_forecast,
)


def render_stage_bracket_view(data: dict) -> None:
    st.markdown("### Stage view")
    st.caption("Mobile-friendly view. Pick one stage instead of squeezing the full bracket into five columns.")

    mode = st.radio(
        "Data shown",
        ["Confirmed + projected", "Confirmed only", "Projected only"],
        horizontal=True,
        key="cupmarket_stage_bracket_mode",
    )
    stage = st.selectbox("Stage", list(STAGE_ALIASES.keys()), key="cupmarket_stage_bracket_stage")

    source = _confirmed_source(data)
    projected = _projected_round32(data)
    prices = data.get("prices", pd.DataFrame())
    if not isinstance(prices, pd.DataFrame):
        prices = pd.DataFrame()

    rendered = False
    if mode != "Projected only":
        rendered = _render_confirmed_cards(source, stage, limit=16)
    if not rendered and mode != "Confirmed only":
        if stage == "Round of 32":
            rendered = _render_projected_r32(projected, limit=16)
        else:
            rendered = _render_stage_forecast(prices, stage, limit=10)
    if not rendered:
        st.info("Waiting for bracket data for this stage.")

    with st.expander("What can change this?", expanded=False):
        st.write(
            "Projected slots can change after remaining group matches, third-place ranking changes, "
            "or a new model run. Confirmed fixtures should stay fixed once both teams are official."
        )
