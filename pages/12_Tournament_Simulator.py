import pandas as pd
import streamlit as st

from features.live_match_data import load_matches
from features.product_ui import inject_styles, render_project_footer, render_specialist_sidebar
from features.tournament_data_v2 import DATA_DIR, load_static_data
from features.tournament_simulator import render_tournament_simulator

st.set_page_config(
    page_title="CupMarket Simulator",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="auto",
)
inject_styles(DATA_DIR.parent)
render_specialist_sidebar("simulator")

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026</div>
        <h1>Scenario simulator</h1>
        <p>Test possible knockout results and compare how they could change advancement chances and CM values. Official data is never changed.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)
matches, _ = load_matches(DATA_DIR / "world_cup_2026_matches_latest.csv")
static = load_static_data()
prices = static.get("prices", pd.DataFrame())
predictions = static.get("latest_predictions", pd.DataFrame())
render_tournament_simulator(matches, prices, predictions)
render_project_footer()
