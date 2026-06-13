from pathlib import Path

import pandas as pd
import streamlit as st

from features.match_ui import combine_prediction_sources
from features.qualification_ui import render_qualification_lab

st.set_page_config(
    page_title="CupMarket Qualification Lab",
    page_icon="◇",
    layout="wide",
)

root = Path(__file__).resolve().parents[1]
data_dir = root / "data"

for stylesheet in [
    root / "assets" / "product.css",
    root / "assets" / "group_tools.css",
]:
    if stylesheet.exists():
        st.markdown(
            f"<style>{stylesheet.read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True,
        )


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


matches = read_csv(data_dir / "world_cup_2026_matches_latest.csv")
latest_predictions = read_csv(
    data_dir / "world_cup_live_predictions_latest.csv"
)
prediction_ledger = read_csv(
    root / "backend" / "state" / "world_cup_prediction_ledger.csv"
)
prices = read_csv(data_dir / "cupmarket_prices_latest.csv")
group_tables = read_csv(data_dir / "current_group_tables.csv")
predictions = combine_prediction_sources(
    latest_predictions,
    prediction_ledger,
)

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026 · Qualification scenarios</div>
        <h1>What does the next result change?</h1>
        <p>Choose a country and compare its Round-of-32 chances after a win, draw or loss.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)

render_qualification_lab(
    matches,
    predictions,
    prices,
    group_tables,
    {"pending_finished_matches": 0},
)
