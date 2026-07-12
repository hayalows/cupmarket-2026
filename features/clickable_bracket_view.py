from __future__ import annotations

import streamlit as st

from features.bracket_view import _confirmed_source
from features.reliable_clickable_bracket import render_bracket_tree


def render_dynamic_bracket_view(data: dict) -> None:
    st.markdown("### Full bracket")
    st.caption(
        "Follow the official knockout path from the Round of 32 to the final. "
        "Tap or click any official match card to open it in Match Hub."
    )

    source = _confirmed_source(data)
    if source.empty:
        st.info("The official knockout bracket has not been published yet.")
        return

    render_bracket_tree(source)

    with st.expander("How to read the bracket", expanded=False):
        st.markdown(
            "**Regular time:** the match was decided during normal play.\n\n"
            "**After extra time:** the displayed score includes extra-time goals.\n\n"
            "**Pens 4–3:** the main score shows goals from play; the shootout score appears in the status label.\n\n"
            "**Tap or click a match:** opens that fixture in Match Hub.\n\n"
            "**Green-highlighted country:** advanced from a finished match.\n\n"
            "**Red match border:** match is currently live.\n\n"
            "**Solid connector:** winner moves to the next round.\n\n"
            "**Dashed connector:** semi-final loser moves to the third-place match."
        )
