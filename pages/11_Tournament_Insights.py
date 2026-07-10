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


def _knockout_counts(progress: pd.DataFrame) -> tuple[int, int, int]:
    if not isinstance(progress, pd.DataFrame) or progress.empty or "status" not in progress.columns:
        return 0, 0, 0
    statuses = progress["status"].astype(str)
    finished = int(statuses.isin(["FINISHED", "AWARDED"]).sum())
    live = int(statuses.isin(["IN_PLAY", "LIVE", "PAUSED", "SUSPENDED"]).sum())
    upcoming = int(statuses.isin(["TIMED", "SCHEDULED"]).sum())
    return finished, live, upcoming


st.set_page_config(page_title="CupMarket Analysis", page_icon="💡", layout="wide")
inject_styles(DATA_DIR.parent)
render_specialist_sidebar("insights")

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026</div>
        <h1>Model analysis</h1>
        <p>Review forecast performance, match evidence, adaptive research and knockout-model checks. Open Archive for the permanent tournament story and market replay.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)
st.info(
    "Official results are fixed. Forecasts and projected paths can change. "
    "Adaptive ratings remain a research layer until their guardrail is satisfied."
)

static = load_static_data()
path_data = load_tournament_path_data()
prices = static.get("prices", pd.DataFrame())
predictions = static.get("latest_predictions", pd.DataFrame())
tables = path_data.get("group_tables", pd.DataFrame())
movements = path_data.get("movements", pd.DataFrame())
movement_history = path_data.get("movement_history", pd.DataFrame())
if movement_history.empty:
    movement_history = movements
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

finished_knockouts, live_knockouts, upcoming_knockouts = _knockout_counts(progress)
st.caption(
    f"Tournament context: {_alive_count(prices)} still alive - "
    f"{finished_knockouts} knockout results - {live_knockouts} live - "
    f"{upcoming_knockouts} fixtures ahead."
)
st.markdown("### Choose an analysis")
st.caption(
    "Open one evidence view at a time. Permanent tournament history and market replay stay in Archive."
)
analysis_view = st.selectbox(
    "Analysis view",
    [
        "Research summary",
        "Match review",
        "Evidence timeline",
        "Model evaluation",
        "Adaptive research",
        "Knockout checks",
    ],
    key="cupmarket_analysis_view",
)

if analysis_view == "Research summary":
    render_tournament_insights(
        prices,
        tables,
        movements,
        path_status,
        snapshots=snapshots,
        prediction_ledger=prediction_ledger,
        progress=progress,
    )
elif analysis_view == "Match review":
    render_match_story(prediction_ledger, movement_history, processed_ledger)
elif analysis_view == "Evidence timeline":
    render_tournament_timeline(processed_ledger, movement_history)
elif analysis_view == "Model evaluation":
    render_model_performance()
elif analysis_view == "Adaptive research":
    render_adaptive_ratings_insights(adaptive_ratings)
else:
    render_knockout_readiness(prices, predictions, path_status)
render_project_footer()
