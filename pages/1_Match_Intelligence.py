from pathlib import Path
import json

import pandas as pd
import streamlit as st

from features.live_match_data import (
    format_source_time,
    group_freshness,
    load_matches,
)
from features.match_ui import combine_prediction_sources, render_match_centre
from features.product_ui import (
    inject_styles,
    render_live_vs_official_note,
    render_page_guide,
    render_project_footer,
    render_specialist_sidebar,
)

st.set_page_config(
    page_title="CupMarket Match Intelligence",
    page_icon="⚽",
    layout="wide",
)

root = Path(__file__).resolve().parents[1]
data_dir = root / "data"

inject_styles(root)
render_specialist_sidebar("match")


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    for column in ["utc_date", "generated_at_utc", "last_updated"]:
        if column in frame.columns:
            frame[column] = pd.to_datetime(
                frame[column], errors="coerce", utc=True
            )
    return frame


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


matches, score_metadata = load_matches(
    data_dir / "world_cup_2026_matches_latest.csv"
)
latest_predictions = read_csv(
    data_dir / "world_cup_live_predictions_latest.csv"
)
prediction_ledger = read_csv(
    root / "backend" / "state" / "world_cup_prediction_ledger.csv"
)
prices = read_csv(data_dir / "cupmarket_prices_latest.csv")
model_metadata = read_json(data_dir / "phase5_simulation_metadata.json")
predictions = combine_prediction_sources(
    latest_predictions,
    prediction_ledger,
)
freshness = group_freshness(matches, model_metadata)

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026 · Match intelligence</div>
        <h1>Every matchup, opened up.</h1>
        <p>Live score states are combined with the latest published CupMarket model probabilities.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)

render_page_guide(
    "Open one match and read it in layers",
    "Start with the score and timing, then compare the current live state with the saved pre-match forecast.",
    [
        ("Refresh", "Request the latest score state."),
        ("Choose", "Select the fixture you want to inspect."),
        ("Compare", "Read live probabilities against the original forecast."),
    ],
)
render_live_vs_official_note()

source_columns = st.columns(4)
source_columns[0].metric("Score source", score_metadata.get("source", "Unknown"))
source_columns[1].metric(
    "Score feed refreshed",
    format_source_time(score_metadata.get("fetched_at_utc")),
)
source_columns[2].metric(
    "Model generated",
    format_source_time(model_metadata.get("generated_at_utc")),
)
source_columns[3].metric(
    "Results awaiting model",
    freshness["pending_model_updates"],
)

if score_metadata.get("warning"):
    st.warning(
        score_metadata["warning"]
        + " The page has safely fallen back to the latest GitHub snapshot."
    )

if freshness["pending_model_updates"]:
    pending = freshness["pending_model_updates"]
    st.warning(
        f"{pending} completed group match"
        + ("es are" if pending != 1 else " is")
        + " already visible in the score feed but not yet reflected in the "
        "published model probabilities. Scores are current; forecasts will catch "
        "up after the next successful model workflow."
    )
else:
    st.success(
        "The live score feed and published group-stage model are currently aligned."
    )

render_match_centre(matches, predictions, prices)
render_project_footer()
