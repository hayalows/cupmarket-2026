import streamlit as st

from features.bracket_stage_view import render_stage_bracket_view
from features.clickable_bracket_view import render_dynamic_bracket_view
from features.product_ui import inject_styles, render_project_footer, render_specialist_sidebar
from features.tournament_data import DATA_DIR
from features.tournament_path_data import load_tournament_path_data, tournament_summary

st.set_page_config(
    page_title="CupMarket Bracket",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="auto",
)

inject_styles(DATA_DIR.parent)
render_specialist_sidebar("bracket")

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026</div>
        <h1>Tournament bracket</h1>
        <p>Track every knockout result, see who advanced and follow each path towards the World Cup final.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)

data = load_tournament_path_data()
summary = tournament_summary(data)
metrics = st.columns(4)
metrics[0].metric("Tournament stage", summary["current_stage"])
metrics[1].metric("Bracket status", summary["bracket_status"])
metrics[2].metric("Finished", summary["completed_knockout_matches"])
metrics[3].metric("Live", summary["live_knockout_matches"])

st.info(
    "Use Stage view for a compact mobile list. Full bracket shows the connected tournament path "
    "with country flags, scores and clickable match cards."
)
stage_tab, full_tab = st.tabs(["Stage view", "Full bracket"])
with stage_tab:
    render_stage_bracket_view(data)
with full_tab:
    render_dynamic_bracket_view(data)
render_project_footer()
