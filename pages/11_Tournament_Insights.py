import pandas as pd
import streamlit as st

from features.product_ui import inject_styles, render_project_footer, render_specialist_sidebar
from features.tournament_data_v2 import DATA_DIR, load_static_data
from features.tournament_insights import render_tournament_insights
from features.tournament_path_data import load_tournament_path_data

st.set_page_config(page_title="CupMarket Tournament Insights", page_icon="💡", layout="wide")

inject_styles(DATA_DIR.parent)
render_specialist_sidebar("insights")

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026 · Tournament Insights</div>
        <h1>What changed, who benefited, and what still matters.</h1>
        <p>Automatic insights from the latest model run: movers, qualification pressure, continent picture, surprise teams and bracket stories.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)

static = load_static_data()
path_data = load_tournament_path_data()

prices = static.get("prices", pd.DataFrame())
tables = pd.read_csv(DATA_DIR / "current_group_tables.csv")
movements_path = DATA_DIR / "market_movements_latest.csv"
movements = pd.read_csv(movements_path) if movements_path.exists() else pd.DataFrame()
path_status = path_data.get("path_status", pd.DataFrame())

render_tournament_insights(prices, tables, movements, path_status)
render_project_footer()
