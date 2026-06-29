import streamlit as st

from features.bracket_stage_view import render_stage_bracket_view
from features.bracket_view import render_dynamic_bracket_view
from features.product_ui import inject_styles, render_project_footer, render_specialist_sidebar
from features.tournament_data import DATA_DIR
from features.tournament_path_data import load_tournament_path_data, tournament_summary

st.set_page_config(
    page_title="CupMarket Bracket View",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="auto",
)

inject_styles(DATA_DIR.parent)
render_specialist_sidebar("bracket")

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026 - Bracket</div>
        <h1>See the bracket as it stands now.</h1>
        <p>Confirmed fixtures appear when the official bracket locks. Projected fixtures show the latest model view until both teams are known.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)

data = load_tournament_path_data()
summary = tournament_summary(data)

metrics = st.columns(4)
metrics[0].metric("Tournament stage", summary["current_stage"])
metrics[1].metric("Bracket", summary["bracket_status"])
metrics[2].metric("Knockout matches finished", summary["completed_knockout_matches"])
metrics[3].metric("Knockout matches live", summary["live_knockout_matches"])

st.info(
    "Use Stage view on mobile. Use Full bracket on wider screens. Confirmed fixtures come from the official feed. Projected fixtures come from the latest model run."
)

stage_tab, full_tab = st.tabs(["Stage view", "Full bracket"])
with stage_tab:
    render_stage_bracket_view(data)
with full_tab:
    render_dynamic_bracket_view(data)

render_project_footer()
