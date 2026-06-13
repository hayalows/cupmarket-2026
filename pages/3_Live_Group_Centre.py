from __future__ import annotations

from pathlib import Path
import json

import pandas as pd
import plotly.express as px
import streamlit as st

from features.live_context import team_context
from features.live_match_data import format_source_time, load_matches
from features.match_ui import combine_prediction_sources
from features.team_projection import project_team

st.set_page_config(
    page_title="CupMarket Live Group Centre",
    page_icon="◉",
    layout="wide",
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

for stylesheet in [ROOT / "assets" / "product.css", ROOT / "assets" / "group_tools.css"]:
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


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def percent(value: float) -> str:
    return f"{100 * float(value):.1f}%"
