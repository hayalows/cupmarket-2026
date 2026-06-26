import pandas as pd
import streamlit as st

from features.live_match_data import load_matches
from features.product_guidance import render_country_snapshot
from features.product_ui import inject_styles, render_project_footer, render_specialist_sidebar
from features.tournament_data_v2 import DATA_DIR, load_static_data
from features.tournament_path_data import load_tournament_path_data, status_label


def _percent(value) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "—"
    return f"{100 * float(number):.1f}%"


st.set_page_config(page_title="CupMarket Country Snapshot", page_icon="🔎", layout="wide")

inject_styles(DATA_DIR.parent)
render_specialist_sidebar("country")

matches, metadata = load_matches(DATA_DIR / "world_cup_2026_matches_latest.csv")
static = load_static_data()
path_data = load_tournament_path_data()

st.title("Country Snapshot")
st.write("One place for a country's price, next match, qualification path and key links.")

render_country_snapshot(matches, static["prices"], default_team="Ghana")

team = st.session_state.get("country_snapshot_team")
path_status = path_data.get("path_status", pd.DataFrame())
opponents = path_data.get("opponents", pd.DataFrame())

if team and isinstance(path_status, pd.DataFrame) and not path_status.empty and "team" in path_status.columns:
    rows = path_status.loc[path_status["team"].astype(str) == str(team)]
    if not rows.empty:
        path = rows.iloc[-1]
        st.markdown("### Likely knockout path")
        cols = st.columns(3)
        cols[0].metric("Path state", status_label(path.get("fixture_status")))
        cols[1].metric("Round of 32", _percent(path.get("prob_reach_round_32")))
        opponent = path.get("most_likely_opponent")
        if pd.isna(opponent) or not str(opponent).strip():
            opponent = "Waiting for model"
        cols[2].metric("Likely opponent", str(opponent))
        st.caption(
            "This can change when remaining group results alter table positions, third-place rankings, or the latest model run."
        )

        if isinstance(opponents, pd.DataFrame) and not opponents.empty and {"team", "opponent"}.issubset(opponents.columns):
            choices = opponents.loc[opponents["team"].astype(str) == str(team)].copy()
            probability_column = "probability_given_qualification" if "probability_given_qualification" in choices.columns else "probability_unconditional"
            if not choices.empty and probability_column in choices.columns:
                choices[probability_column] = pd.to_numeric(choices[probability_column], errors="coerce")
                choices = choices.sort_values(probability_column, ascending=False).head(5)
                display = choices[["opponent", probability_column]].copy()
                display.columns = ["Possible opponent", "Chance if qualified"]
                display["Chance if qualified"] = display["Chance if qualified"].map(_percent)
                st.dataframe(display, hide_index=True, use_container_width=True)
else:
    st.info("Projected knockout path data will appear here after the model publishes it.")

st.caption(f"Score source: {metadata.get('source', 'Unknown')}")
render_project_footer()
