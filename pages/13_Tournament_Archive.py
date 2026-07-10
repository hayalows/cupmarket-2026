import streamlit as st

from features.product_ui import inject_styles, render_project_footer, render_specialist_sidebar
from features.tournament_archive import render_tournament_archive
from features.tournament_data_v2 import DATA_DIR

st.set_page_config(page_title="CupMarket Archive", page_icon="🗂️", layout="wide")
inject_styles(DATA_DIR.parent)
render_specialist_sidebar("archive")

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026</div>
        <h1>Tournament archive</h1>
        <p>Review the permanent tournament record, market replay, saved forecasts and final model verdict.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)
render_tournament_archive()
render_project_footer()
