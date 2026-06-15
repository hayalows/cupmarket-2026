import streamlit as st

from features.reliable_match_hub import inject_styles, render_match_hub
from features.product_ui import render_project_footer, render_specialist_sidebar

st.set_page_config(
    page_title="CupMarket Match Hub",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="auto",
)

inject_styles()
render_specialist_sidebar("match_hub")


@st.fragment(run_every="45s")
def render_live_match_hub() -> None:
    render_match_hub()
    st.caption("Automatic score refresh runs every 45 seconds while this page is open.")


render_live_match_hub()
render_project_footer()
