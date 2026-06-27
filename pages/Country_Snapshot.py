import pandas as pd
import plotly.express as px
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


def _number(value, suffix="") -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "—"
    return f"{float(number):.2f}{suffix}"


def _plot_history(history: pd.DataFrame, column: str, title: str, percent: bool = False) -> None:
    if history.empty or column not in history.columns or history[column].dropna().empty:
        st.caption(f"{title} needs more stored data.")
        return
    fig = px.line(history, x="generated_at_utc", y=column, markers=True, title=title)
    fig.update_layout(template="plotly_white", height=340, margin=dict(l=16, r=16, t=52, b=16))
    fig.update_xaxes(title=None)
    fig.update_yaxes(title=None, tickformat=".0%" if percent else None)
    st.plotly_chart(fig, use_container_width=True)


st.set_page_config(page_title="CupMarket Country Snapshot", page_icon="🔎", layout="wide")

inject_styles(DATA_DIR.parent)
render_specialist_sidebar("country")

matches, metadata = load_matches(DATA_DIR / "world_cup_2026_matches_latest.csv")
static = load_static_data()
path_data = load_tournament_path_data()

st.title("Country")
st.write("Price, next match, likely path and stored market journey in one place.")

render_country_snapshot(matches, static["prices"], default_team="Ghana")

team = st.session_state.get("country_snapshot_team") or st.session_state.get("country_snapshot_country")
path_status = path_data.get("path_status", pd.DataFrame())
opponents = path_data.get("opponents", pd.DataFrame())
snapshots = path_data.get("snapshots", pd.DataFrame())
prices = static.get("prices", pd.DataFrame())

if team and isinstance(path_status, pd.DataFrame) and not path_status.empty and "team" in path_status.columns:
    rows = path_status.loc[path_status["team"].astype(str) == str(team)]
    if not rows.empty:
        path = rows.iloc[-1]
        st.markdown("### Likely knockout path")
        cols = st.columns(3)
        cols[0].metric("Trust label", status_label(path.get("fixture_status")))
        cols[1].metric("Round of 32", _percent(path.get("prob_reach_round_32")))
        opponent = path.get("most_likely_opponent")
        if pd.isna(opponent) or not str(opponent).strip():
            opponent = "Waiting for model"
        cols[2].metric("Likely opponent", str(opponent))
        st.caption("Official means locked by the bracket. Projected means model-based and can still change after new results.")

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

st.markdown("### Country journey")
st.caption("This uses the earliest stored CupMarket snapshot as the baseline, then compares it with the latest model output.")

history_parts = []
for frame in [snapshots, prices]:
    if isinstance(frame, pd.DataFrame) and not frame.empty and "team" in frame.columns and team:
        part = frame.loc[frame["team"].astype(str) == str(team)].copy()
        if not part.empty:
            history_parts.append(part)

if history_parts:
    history = pd.concat(history_parts, ignore_index=True, sort=False)
    if "generated_at_utc" in history.columns:
        history["generated_at_utc"] = pd.to_datetime(history["generated_at_utc"], errors="coerce", utc=True)
        history = history.dropna(subset=["generated_at_utc"]).sort_values("generated_at_utc").drop_duplicates("generated_at_utc", keep="last")
        for column in ["cupmarket_price", "prob_reach_round_32"]:
            if column in history.columns:
                history[column] = pd.to_numeric(history[column], errors="coerce")
        if not history.empty:
            first = history.iloc[0]
            latest = history.iloc[-1]
            price_move = pd.to_numeric(latest.get("cupmarket_price"), errors="coerce") - pd.to_numeric(first.get("cupmarket_price"), errors="coerce")
            cols = st.columns(3)
            cols[0].metric("Opening price", _number(first.get("cupmarket_price"), " CM"))
            cols[1].metric("Current price", _number(latest.get("cupmarket_price"), " CM"))
            cols[2].metric("Price move", _number(price_move, " CM"))
            tab_price, tab_r32 = st.tabs(["Price", "Round of 32"])
            with tab_price:
                _plot_history(history, "cupmarket_price", f"{team} price over time")
            with tab_r32:
                _plot_history(history, "prob_reach_round_32", f"{team} Round-of-32 chance", percent=True)
        else:
            st.caption("Stored history is not ready for this country yet.")
    else:
        st.caption("Stored history is missing generated_at_utc, so the journey chart cannot be drawn yet.")
else:
    st.caption("No stored country history found yet.")

st.caption(f"Score source: {metadata.get('source', 'Unknown')}")
render_project_footer()
