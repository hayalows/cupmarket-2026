import streamlit as st

from features.product_ui import (
    inject_styles,
    render_project_footer,
    render_specialist_sidebar,
)
from features.tournament_data import DATA_DIR
from features.tournament_path_page import render_tournament_path_page

st.set_page_config(
    page_title="CupMarket Country",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="auto",
)

inject_styles(DATA_DIR.parent)
render_specialist_sidebar("tournament_path")
render_tournament_path_page()
render_project_footer()
