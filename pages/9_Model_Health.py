import streamlit as st

from features.model_health import render_model_health
from features.product_ui import inject_styles, render_project_footer, render_specialist_sidebar
from features.tournament_data_v2 import DATA_DIR


st.set_page_config(page_title="CupMarket Model Health", page_icon="📡", layout="wide")
inject_styles(DATA_DIR.parent)
render_specialist_sidebar("model_health")
render_model_health()
render_project_footer()
