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

st.set_page_config(page_title="CupMarket Analysis Lab", page_icon="💡", layout="wide")
inject_styles(DATA_DIR.parent)
render_specialist_sidebar("insights")

st.markdown('''<div class="cm-hero"><div class="cm-eyebrow">CupMarket 2026 · Analysis Lab</div><h1>The tournament story, model audit and archive.</h1><p>Review what changed, what the model learned, how prices moved, and what evidence will remain after the final.</p></div>''', unsafe_allow_html=True)
st.info("Trust guide: official results are fixed, projected paths can still change, and adaptive ratings are an audit layer only for now.")

st.markdown("### Specialist tools")
st.caption("Use these when you want a deeper drawer. The main journey stays in Tournament, Country, Matches and Bracket.")
tool_cols = st.columns(5)
with tool_cols[0]:
    st.page_link("pages/1_Match_Intelligence.py", label="Live Match Room")
with tool_cols[1]:
    st.page_link("pages/5_Market_Story.py", label="Market Story")
with tool_cols[2]:
    st.page_link("pages/2_Qualification_Lab.py", label="Group Archive")
with tool_cols[3]:
    st.page_link("pages/3_Live_Group_Centre.py", label="Group Centre")
with tool_cols[4]:
    st.page_link("pages/10_Glossary.py", label="Guide")

static = load_static_data()
path_data = load_tournament_path_data()
prices = static.get("prices", pd.DataFrame())
predictions = static.get("latest_predictions", pd.DataFrame())
tables = pd.read_csv(DATA_DIR / "current_group_tables.csv")
movements_path = DATA_DIR / "market_movements_latest.csv"
movements = pd.read_csv(movements_path) if movements_path.exists() else pd.DataFrame()
movement_history_path = DATA_DIR / "history" / "market_movements.csv"
movement_history = (
    pd.read_csv(movement_history_path)
    if movement_history_path.exists()
    else movements
)
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
    render_match_story(prediction_ledger, movement_history, processed_ledger)
with tabs[2]:
    render_tournament_timeline(processed_ledger, movement_history)
with tabs[3]:
    render_model_performance()
with tabs[4]:
    render_adaptive_ratings_insights(adaptive_ratings)
with tabs[5]:
    render_knockout_readiness(prices, predictions, path_status)

render_project_footer()
