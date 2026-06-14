import streamlit as st

from features.market_story import inject_styles, render_market_story
from features.product_ui import render_project_footer, render_specialist_sidebar

st.set_page_config(
    page_title="CupMarket Market Story",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="auto",
)

inject_styles()
render_specialist_sidebar("market_story")
render_market_story()
render_project_footer()
