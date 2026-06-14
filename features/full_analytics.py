from __future__ import annotations

from pathlib import Path
import json

import pandas as pd
import plotly.express as px
import streamlit as st

from features.tournament_data import DATA_DIR, load_csv, load_market_history

ROOT = Path(__file__).resolve().parents[1]


def inject_styles() -> None:
    for path in [ROOT / "assets" / "product.css", ROOT / "assets" / "pulse_v3.css"]:
        if path.exists():
            st.markdown(f"<style>{path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def _pct(value) -> str:
    number = pd.to_numeric(value, errors="coerce")
    return "—" if pd.isna(number) else f"{100 * float(number):.1f}%"


def _metadata() -> dict:
    path = DATA_DIR / "phase5_simulation_metadata.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _market(prices: pd.DataFrame) -> None:
    st.markdown("### Country Market")
    if prices.empty:
        st.info("No market data is available.")
        return
    columns = [
        "market_rank", "team", "group", "cupmarket_price", "previous_price",
        "price_change", "price_change_percent", "prob_reach_round_32",
        "prob_reach_quarter_final", "prob_reach_final", "prob_champion",
    ]
    display = prices[[column for column in columns if column in prices.columns]].copy()
    for column in ["prob_reach_round_32", "prob_reach_quarter_final", "prob_reach_final", "prob_champion"]:
        if column in display.columns:
            display[column] = display[column].map(_pct)
    display = display.rename(columns={
        "market_rank": "Rank", "team": "Country", "group": "Group",
        "cupmarket_price": "Price", "previous_price": "Previous",
        "price_change": "Change", "price_change_percent": "Change %",
        "prob_reach_round_32": "Reach R32", "prob_reach_quarter_final": "Reach QF",
        "prob_reach_final": "Reach final", "prob_champion": "Champion",
    })
    st.dataframe(display, hide_index=True, use_container_width=True)
    chart = prices.head(20).sort_values("cupmarket_price")
    figure = px.bar(chart, x="cupmarket_price", y="team", orientation="h", title="Top 20 country values")
    figure.update_layout(template="plotly_white", height=520, margin=dict(l=16, r=16, t=52, b=16))
    st.plotly_chart(figure, use_container_width=True)


def _team(prices: pd.DataFrame, history: pd.DataFrame) -> None:
    st.markdown("### Team Explorer")
    if prices.empty:
        st.info("No team data is available.")
        return
    teams = prices.sort_values("market_rank")["team"].astype(str).tolist()
    team = st.selectbox("Country", teams, key="analytics_team")
    row = prices[prices["team"] == team].iloc[0]
    metrics = st.columns(4)
    metrics[0].metric("Price", f"{float(row['cupmarket_price']):.2f} CM")
    metrics[1].metric("Market rank", f"#{int(row['market_rank'])}")
    metrics[2].metric("Reach quarter-final", _pct(row.get("prob_reach_quarter_final")))
    metrics[3].metric("Champion", _pct(row.get("prob_champion")))
    path = st.columns(4)
    path[0].metric("Reach R32", _pct(row.get("prob_reach_round_32")))
    path[1].metric("Reach R16", _pct(row.get("prob_reach_round_16")))
    path[2].metric("Reach semi-final", _pct(row.get("prob_reach_semi_final")))
    path[3].metric("Reach final", _pct(row.get("prob_reach_final")))
    team_history = history[history["team"] == team].sort_values("generated_at_utc")
    if len(team_history) >= 2:
        figure = px.line(team_history, x="generated_at_utc", y="cupmarket_price", markers=True, title=f"{team} price history")
        figure.update_layout(template="plotly_white", height=360, margin=dict(l=16, r=16, t=52, b=16))
        st.plotly_chart(figure, use_container_width=True)


def _groups(groups: pd.DataFrame) -> None:
    st.markdown("### Group Tables")
    if groups.empty:
        st.info("No group table is available.")
        return
    group_values = sorted(groups["group"].astype(str).unique())
    selected = st.selectbox("Group", group_values, key="analytics_group")
    table = groups[groups["group"].astype(str) == selected].sort_values("position")
    columns = ["position", "team", "played", "wins", "draws", "losses", "goals_for", "goals_against", "goal_difference", "points"]
    st.dataframe(table[[column for column in columns if column in table.columns]], hide_index=True, use_container_width=True)


def _health(metadata: dict) -> None:
    st.markdown("### Model & Data Health")
    generated = pd.to_datetime(metadata.get("generated_at_utc"), errors="coerce", utc=True)
    metrics = st.columns(4)
    metrics[0].metric("Model version", metadata.get("model_version", "—"))
    metrics[1].metric("Simulations", f"{int(metadata.get('number_of_simulations', 0)):,}")
    metrics[2].metric("Finished matches processed", int(metadata.get("finished_group_matches", 0)))
    metrics[3].metric("Generated", generated.strftime("%d %b · %H:%M UTC") if pd.notna(generated) else "—")
    limitations = metadata.get("limitations", [])
    if limitations:
        with st.expander("Known limitations", expanded=False):
            for item in limitations:
                st.write(f"• {item}")


def render_full_analytics() -> None:
    prices = load_csv(DATA_DIR / "cupmarket_prices_latest.csv")
    groups = load_csv(DATA_DIR / "current_group_tables.csv")
    history = load_market_history()
    metadata = _metadata()

    st.markdown(
        '''
        <div class="cm-hero">
            <div class="cm-eyebrow">CupMarket 2026 · Full analytics</div>
            <h1>Go deeper when the headline is not enough.</h1>
            <p>Country rankings, team paths, group tables and model health remain available in one analytical workspace.</p>
        </div>
        ''',
        unsafe_allow_html=True,
    )
    market_tab, team_tab, groups_tab, health_tab = st.tabs(["Country Market", "Team Explorer", "Group Tables", "Model Health"])
    with market_tab:
        _market(prices)
    with team_tab:
        _team(prices, history)
    with groups_tab:
        _groups(groups)
    with health_tab:
        _health(metadata)
