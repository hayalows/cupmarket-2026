import streamlit as st

from features.product_ui import (
    inject_styles,
    render_project_footer,
    render_specialist_sidebar,
)
from features.tournament_data import DATA_DIR
from features.tournament_pulse_page import render_tournament_pulse_page

st.set_page_config(
    page_title="CupMarket Tournament Pulse",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="auto",
)

inject_styles(DATA_DIR.parent)
render_specialist_sidebar("overview")
render_tournament_pulse_page()
render_project_footer()
