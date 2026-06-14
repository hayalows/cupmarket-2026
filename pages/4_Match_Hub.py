import streamlit as st

from features.match_hub_v2 import inject_styles, render_match_hub
from features.product_ui import render_project_footer, render_specialist_sidebar

st.set_page_config(
    page_title="CupMarket Match Hub",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="auto",
)

inject_styles()
render_specialist_sidebar("match_hub")
render_match_hub()
render_project_footer()
