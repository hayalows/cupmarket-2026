from pathlib import Path

import streamlit as st

from features.group_centre import load_page_data
from features.group_centre_page import render_page
from features.live_match_data import should_auto_refresh
from features.product_ui import (
    inject_styles,
    render_project_footer,
    render_specialist_sidebar,
)

st.set_page_config(
    page_title="CupMarket Live Group Centre",
    page_icon="📋",
    layout="wide",
)

ROOT = Path(__file__).resolve().parents[1]
inject_styles(ROOT)
render_specialist_sidebar("group")


def _render(data: dict, refresh_label: str) -> None:
    render_page(ROOT, data)
    st.caption(refresh_label)


@st.fragment(run_every="45s")
def render_active_group_centre() -> None:
    data = load_page_data(ROOT)
    if not should_auto_refresh(data["matches"]):
        st.rerun()
    _render(data, "Live checks run every 45 seconds while group matches may be active.")


@st.fragment(run_every="5m")
def render_idle_group_centre() -> None:
    data = load_page_data(ROOT)
    if should_auto_refresh(data["matches"]):
        st.rerun()
    _render(data, "No group match is active; CupMarket checks again every five minutes.")


initial_data = load_page_data(ROOT)
if should_auto_refresh(initial_data["matches"]):
    render_active_group_centre()
else:
    render_idle_group_centre()

render_project_footer()
