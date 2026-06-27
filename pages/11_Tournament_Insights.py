import pandas as pd
import streamlit as st

from features.match_story import render_match_story
from features.product_ui import inject_styles, render_project_footer, render_specialist_sidebar
from features.tournament_data_v2 import DATA_DIR, STATE_DIR, load_static_data
from features.tournament_insights import render_tournament_insights
from features.tournament_path_data import load_tournament_path_data
from features.tournament_timeline import render_tournament_timeline

st.set_page_config(page_title="CupMarket Insights", page_icon="💡", layout="wide")

inject_styles(DATA_DIR.parent)
render_specialist_sidebar("insights")

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026 · Insights</div>
        <h1>The tournament story, not just the tables.</h1>
        <p>See who improved, who collapsed, what the model got right, and how the tournament has moved over time.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)

st.info(
    "Trust guide: official results are fixed, published market values update after model runs, and projected paths can still change."
)

static = load_static_data()
path_data = load_tournament_path_data()

prices = static.get("prices", pd.DataFrame())
tables = pd.read_csv(DATA_DIR / "current_group_tables.csv")
movements_path = DATA_DIR / "market_movements_latest.csv"
movements = pd.read_csv(movements_path) if movements_path.exists() else pd.DataFrame()
path_status = path_data.get("path_status", pd.DataFrame())
snapshots = path_data.get("snapshots", pd.DataFrame())
processed_ledger = static.get("processed_ledger", pd.DataFrame())
prediction_ledger = static.get("prediction_ledger", pd.DataFrame())
if prediction_ledger.empty:
    ledger_path = STATE_DIR / "world_cup_prediction_ledger.csv"
    prediction_ledger = pd.read_csv(ledger_path) if ledger_path.exists() else pd.DataFrame()

main_tab, match_tab, timeline_tab = st.tabs(["Tournament insights", "Match story", "Timeline"])
with main_tab:
    render_tournament_insights(
        prices,
        tables,
        movements,
        path_status,
        snapshots=snapshots,
        prediction_ledger=prediction_ledger,
    )
with match_tab:
    render_match_story(prediction_ledger, movements, processed_ledger)
with timeline_tab:
    render_tournament_timeline(processed_ledger, movements)

render_project_footer()
