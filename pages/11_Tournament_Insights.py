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


def _alive_count(prices: pd.DataFrame) -> int:
    if prices.empty:
        return 0
    exit_columns = [
        "prob_group_exit",
        "prob_round_32_exit",
        "prob_round_16_exit",
        "prob_quarter_final_exit",
        "prob_semi_final_exit",
        "prob_runner_up",
    ]
    locked_out = pd.Series(False, index=prices.index)
    for column in exit_columns:
        if column in prices.columns:
            locked_out = locked_out | (
                pd.to_numeric(prices[column], errors="coerce").fillna(0.0) >= 0.999
            )
    champion = pd.to_numeric(prices.get("prob_champion"), errors="coerce").fillna(0.0)
    return int((~locked_out | (champion > 0.0)).sum())


def _knockout_counts(progress: pd.DataFrame) -> tuple[int, int]:
    if not isinstance(progress, pd.DataFrame) or progress.empty or "status" not in progress.columns:
        return 0, 0
    statuses = progress["status"].astype(str)
    finished = int(statuses.isin(["FINISHED", "AWARDED"]).sum())
    upcoming = int(statuses.isin(["TIMED", "SCHEDULED"]).sum())
    return finished, upcoming


st.set_page_config(page_title="CupMarket Analysis Lab", page_icon="💡", layout="wide")
inject_styles(DATA_DIR.parent)
render_specialist_sidebar("insights")

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026 - Analysis Lab</div>
        <h1>The tournament story, model audit and archive.</h1>
        <p>Review what changed, what the model learned, how prices moved, and what evidence will remain after the final.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)
st.info(
    "Trust guide: official results are fixed, projected paths can still change, "
    "and adaptive ratings are an audit layer only for now."
)

with st.expander("Specialist tools", expanded=False):
    st.caption(
        "Use these for deeper drawers. The main journey stays in Tournament, "
        "Country, Matches and Bracket."
    )
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
progress = path_data.get("progress", pd.DataFrame())
history = static.get("history", pd.DataFrame())
processed_ledger = static.get("processed_ledger", pd.DataFrame())
prediction_ledger = static.get("prediction_ledger", pd.DataFrame())
adaptive_ratings = build_adaptive_ratings(prices, history, processed_ledger)
if prediction_ledger.empty:
    ledger_path = STATE_DIR / "world_cup_prediction_ledger.csv"
    prediction_ledger = pd.read_csv(ledger_path) if ledger_path.exists() else pd.DataFrame()

finished_knockouts, upcoming_knockouts = _knockout_counts(progress)
stage_cols = st.columns(4)
stage_cols[0].metric("Still alive", _alive_count(prices))
stage_cols[1].metric("Knockout results", finished_knockouts)
stage_cols[2].metric("Fixtures ahead", upcoming_knockouts)
stage_cols[3].metric(
    "Adaptive teams",
    len(adaptive_ratings) if isinstance(adaptive_ratings, pd.DataFrame) else 0,
)
st.caption(
    "Use the tabs below by question: tournament story, one match, timeline, "
    "model audit, adaptive learning or knockout readiness."
)

tabs = st.tabs(
    [
        "Tournament insights",
        "Match story",
        "Timeline",
        "Model performance",
        "Adaptive ratings",
        "Knockout readiness",
    ]
)
with tabs[0]:
    render_tournament_insights(
        prices,
        tables,
        movements,
        path_status,
        snapshots=snapshots,
        prediction_ledger=prediction_ledger,
    )
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
