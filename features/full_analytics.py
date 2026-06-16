from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from features.market_movement import add_rank_movement, rank_movement_text
from features.model_performance_v2 import render_model_performance
from features.official_data import load_latest_json
from features.product_ui import render_official_data_caption
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
    return load_latest_json(DATA_DIR / "phase5_simulation_metadata.json")


def _market(prices: pd.DataFrame) -> None:
    st.markdown("### Country Market")
    if prices.empty:
        st.info("No market data is available.")
        return
    prices = add_rank_movement(prices)
    columns = [
        "market_rank", "previous_market_rank", "rank_change", "team", "group",
        "cupmarket_price", "previous_price", "price_change", "price_change_percent",
        "prob_reach_round_32", "prob_reach_quarter_final", "prob_reach_final",
        "prob_champion",
    ]
    display = prices[[column for column in columns if column in prices.columns]].copy()
    if {"market_rank", "previous_market_rank"}.issubset(display.columns):
        display["rank_change"] = display.apply(
            lambda row: rank_movement_text(
                row["market_rank"], row["previous_market_rank"]
            ),
            axis=1,
        )
    for column in ["prob_reach_round_32", "prob_reach_quarter_final", "prob_reach_final", "prob_champion"]:
        if column in display.columns:
            display[column] = display[column].map(_pct)
    for column in ["market_rank", "previous_market_rank"]:
        if column in display.columns:
            display[column] = display[column].map(
                lambda value: f"#{int(value)}" if pd.notna(value) else "—"
            )
    display = display.rename(columns={
        "market_rank": "Rank", "previous_market_rank": "Previous rank",
        "rank_change": "Rank move", "team": "Country", "group": "Group",
        "cupmarket_price": "Price", "previous_price": "Previous price",
        "price_change": "Change", "price_change_percent": "Change %",
        "prob_reach_round_32": "Reach R32", "prob_reach_quarter_final": "Reach QF",
        "prob_reach_final": "Reach final", "prob_champion": "Champion",
    })
    st.dataframe(display, hide_index=True, use_container_width=True)
    chart = prices.head(20).sort_values("cupmarket_price")
    figure = px.bar(chart, x="cupmarket_price", y="team", orientation="h", title="Top 20 country values")
    figure.update_layout(template="plotly_white", height=520, margin=dict(l=16, r=16, t=52, b=16))
    st.plotly_chart(figure, use_container_width=True)
    render_official_data_caption(prices)


def _team(prices: pd.DataFrame, history: pd.DataFrame) -> None:
    st.markdown("### Team Explorer")
    if prices.empty:
        st.info("No team data is available.")
        return
    prices = add_rank_movement(prices)
    teams = prices.sort_values("market_rank")["team"].astype(str).tolist()
    team = st.selectbox("Country", teams, key="analytics_team")
    row = prices[prices["team"] == team].iloc[0]
    metrics = st.columns(4)
    metrics[0].metric("Price", f"{float(row['cupmarket_price']):.2f} CM")
    metrics[1].metric(
        "Market rank",
        f"#{int(row['market_rank'])}",
        delta=rank_movement_text(
            row.get("market_rank"),
            row.get("previous_market_rank"),
            include_previous=True,
        ),
        delta_color="off",
    )
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
    render_official_data_caption(prices)


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
    render_official_data_caption(groups, label="Official group table")


def _health(metadata: dict) -> None:
    st.markdown("### Model & Data Health")
    generated = pd.to_datetime(metadata.get("generated_at_utc"), errors="coerce", utc=True)
    metrics = st.columns(4)
    metrics[0].metric("Model version", metadata.get("model_version", "—"))
    metrics[1].metric("Simulations", f"{int(metadata.get('number_of_simulations', 0)):,}")
    metrics[2].metric("Finished matches processed", int(metadata.get("finished_group_matches", 0)))
    metrics[3].metric("Generated", generated.strftime("%d %b · %H:%M UTC") if pd.notna(generated) else "—")
    source = metadata.get("_cupmarket_source")
    commit_sha = metadata.get("_cupmarket_commit")
    if source:
        commit_text = f" · snapshot {str(commit_sha)[:7]}" if commit_sha else ""
        st.caption(f"Official model metadata source: {source}{commit_text}")
    limitations = metadata.get("limitations", [])
    if limitations:
        with st.expander("Known limitations", expanded=False):
            for item in limitations:
                st.write(f"• {item}")


def render_full_analytics() -> None:
    st.markdown(
        '''
        <div class="cm-hero">
            <div class="cm-eyebrow">CupMarket 2026 · Full analytics</div>
            <h1>Go deeper when the headline is not enough.</h1>
            <p>Choose one analytical view at a time: market, team, group, model performance or system health.</p>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    options = ["Market", "Team", "Groups", "Performance", "Health"]
    requested = st.session_state.pop("cupmarket_analytics_view", None)
    if requested in options:
        st.session_state["full_analytics_view"] = requested
    elif st.session_state.get("full_analytics_view") not in options:
        st.session_state["full_analytics_view"] = "Market"

    view = st.segmented_control(
        "Analytics view",
        options,
        key="full_analytics_view",
        selection_mode="single",
    ) or "Market"

    if view == "Market":
        _market(load_csv(DATA_DIR / "cupmarket_prices_latest.csv"))
    elif view == "Team":
        _team(
            load_csv(DATA_DIR / "cupmarket_prices_latest.csv"),
            load_market_history(),
        )
    elif view == "Groups":
        _groups(load_csv(DATA_DIR / "current_group_tables.csv"))
    elif view == "Performance":
        render_model_performance()
    else:
        _health(_metadata())
