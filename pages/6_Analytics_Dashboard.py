import streamlit as st

from features.product_ui import (
    inject_styles,
    render_project_footer,
    render_specialist_sidebar,
)
from features.tournament_data import DATA_DIR


st.set_page_config(
    page_title="CupMarket Analysis Lab",
    page_icon="💡",
    layout="wide",
    initial_sidebar_state="auto",
)

inject_styles(DATA_DIR.parent)
render_specialist_sidebar("analysis")

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026 · Analysis Lab</div>
        <h1>Analysis has one home now.</h1>
        <p>Model review, adaptive learning, timeline, market movement and tournament evidence now live together in Analysis Lab.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)

st.info("Open Analysis Lab for the merged analytics and insights workspace.")
if st.button("Open Analysis Lab", type="primary", use_container_width=True):
    st.switch_page("pages/11_Tournament_Insights.py")

render_project_footer()
