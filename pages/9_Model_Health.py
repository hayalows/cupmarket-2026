import streamlit as st

from features.model_health import render_model_health
from features.product_ui import inject_styles, render_project_footer, render_specialist_sidebar
from features.tournament_data_v2 import DATA_DIR

st.set_page_config(page_title="CupMarket System Health", page_icon="📡", layout="wide")
inject_styles(DATA_DIR.parent)
render_specialist_sidebar("model_health")

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026</div>
        <h1>System health</h1>
        <p>Check data freshness, publication status, workflow state and model safety controls.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)
render_model_health()
render_project_footer()
