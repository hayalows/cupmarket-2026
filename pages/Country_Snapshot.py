import streamlit as st

from features.live_match_data import load_matches
from features.product_guidance import render_country_snapshot
from features.product_ui import inject_styles, render_project_footer, render_specialist_sidebar
from features.tournament_data_v2 import DATA_DIR, load_static_data

st.set_page_config(page_title="CupMarket Country Snapshot", page_icon="🔎", layout="wide")

inject_styles(DATA_DIR.parent)
render_specialist_sidebar("country")

matches, metadata = load_matches(DATA_DIR / "world_cup_2026_matches_latest.csv")
static = load_static_data()

st.title("Country Snapshot")
st.write("One place for a country's price, next match, qualification path and key links.")

render_country_snapshot(matches, static["prices"], default_team="Ghana")
st.caption(f"Score source: {metadata.get('source', 'Unknown')}")
render_project_footer()
