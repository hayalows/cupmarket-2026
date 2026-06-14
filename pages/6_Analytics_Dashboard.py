import streamlit as st

from features.full_analytics import inject_styles, render_full_analytics
from features.product_ui import render_project_footer, render_specialist_sidebar

st.set_page_config(
    page_title="CupMarket Full Analytics",
    page_icon="▤",
    layout="wide",
    initial_sidebar_state="auto",
)

inject_styles()
render_specialist_sidebar("analytics")
render_full_analytics()
render_project_footer()
