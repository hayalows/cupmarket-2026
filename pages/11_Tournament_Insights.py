import pandas as pd
import streamlit as st

from features.adaptive_ratings import build_adaptive_ratings, render_adaptive_ratings_insights
from features.knockout_readiness import render_knockout_readiness
from features.match_story import render_match_story
from features.model_performance import render_model_performance
from features.product_ui import inject_styles, render_project_footer, render_specialist_sidebar
from features.tournament_data_v2 import DATA_DIR, STATE_DIR, load_static_data
from features.tournament_insights import render_tournament_insights
from features.tournament_path_data import load_tournament_path_data
from features.tournament_timeline import render_tournament_timeline

st.set_page_config(page_title="CupMarket Insights", page_icon="💡", layout="wide")
inject_styles(DATA_DIR.parent)
render_specialist_sidebar("insights")

st.markdown('''<div class="cm-hero"><div class="cm-eyebrow">CupMarket 2026 · Insights</div><h1>The tournament story, not just the tables.</h1><p>See what changed, how the model is performing, and what CupMarket has learned so far.</p></div>''', unsafe_allow_html=True)
st.info("Trust guide: official results are fixed, projected paths can still change, and adaptive ratings are an audit layer only for now.")

static = load_static_data()
path_data = load_tournament_path_data()
prices = static.get("prices", pd.DataFrame())
predictions = static.get("latest_predictions", pd.DataFrame())
tables = pd.read_csv(DATA_DIR / "current_group_tables.csv")
movements_path = DATA_DIR / "market_movements_latest.csv"
movements = pd.read_csv(movements_path) if movements_path.exists() else pd.DataFrame()
path_status = path_data.get("path_status", pd.DataFrame())
snapshots = path_data.get("snapshots", pd.DataFrame())
history = static.get("history", pd.DataFrame())
processed_ledger = static.get("processed_ledger", pd.DataFrame())
prediction_ledger = static.get("prediction_ledger", pd.DataFrame())
adaptive_ratings = build_adaptive_ratings(prices, history, processed_ledger)
if prediction_ledger.empty:
    ledger_path = STATE_DIR / "world_cup_prediction_ledger.csv"
    prediction_ledger = pd.read_csv(ledger_path) if ledger_path.exists() else pd.DataFrame()

tabs = st.tabs(["Tournament insights", "Match story", "Timeline", "Model performance", "Adaptive ratings", "Knockout readiness"])
with tabs[0]:
    render_tournament_insights(prices, tables, movements, path_status, snapshots=snapshots, prediction_ledger=prediction_ledger)
with tabs[1]:
    render_match_story(prediction_ledger, movements, processed_ledger)
with tabs[2]:
    render_tournament_timeline(processed_ledger, movements)
with tabs[3]:
    render_model_performance()
with tabs[4]:
    render_adaptive_ratings_insights(adaptive_ratings)
with tabs[5]:
    render_knockout_readiness(prices, predictions, path_status)

render_project_footer()
