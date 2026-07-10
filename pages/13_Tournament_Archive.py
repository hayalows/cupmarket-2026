import streamlit as st

from features.product_ui import inject_styles, render_project_footer, render_specialist_sidebar
from features.tournament_archive import render_tournament_archive
from features.tournament_data_v2 import DATA_DIR


st.set_page_config(page_title="CupMarket Tournament Archive", page_icon="🗂️", layout="wide")
inject_styles(DATA_DIR.parent)
render_specialist_sidebar("archive")
render_tournament_archive()
render_project_footer()
