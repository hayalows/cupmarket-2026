from __future__ import annotations

import streamlit as st

from features.bracket_view import _confirmed_source
from features.clickable_bracket import render_bracket_tree


def render_dynamic_bracket_view(data: dict) -> None:
    st.markdown("### Full bracket")
    st.caption(
        "Follow the official knockout path from the Round of 32 to the final. "
        "Click any available match to open its live, result or upcoming-match details."
    )

    source = _confirmed_source(data)
    if source.empty:
        st.info("The official knockout bracket has not been published yet.")
        return

    render_bracket_tree(source)

    with st.expander("How to read the bracket", expanded=False):
        st.markdown(
            "**Click a match:** opens its detail inside Matches.\n\n"
            "**Green-highlighted country:** advanced from a finished match.\n\n"
            "**Red match border:** match is currently live.\n\n"
            "**Solid connector:** winner moves to the next round.\n\n"
            "**Dashed connector:** semi-final loser moves to the third-place match.\n\n"
            "The smaller Stage view remains the easier option on a phone."
        )
