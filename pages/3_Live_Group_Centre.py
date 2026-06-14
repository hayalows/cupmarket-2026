from pathlib import Path

import streamlit as st

from features.group_centre_page import render_page
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


@st.fragment(run_every="45s")
def render_live_group_centre() -> None:
    render_page(ROOT)
    st.caption("Automatic score refresh runs every 45 seconds while this page is open.")


render_live_group_centre()
render_project_footer()
