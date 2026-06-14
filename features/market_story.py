from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from features.tournament_data import latest_update_matches, load_static_data

ROOT = Path(__file__).resolve().parents[1]


def inject_styles() -> None:
    for path in [ROOT / "assets" / "product.css", ROOT / "assets" / "pulse_v3.css"]:
        if path.exists():
            st.markdown(f"<style>{path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def _pct(value, digits: int = 1) -> str:
    number = pd.to_numeric(value, errors="coerce")
    return "—" if pd.isna(number) else f"{100 * float(number):.{digits}f}%"


def _pp_delta(current, previous) -> str | None:
    current_num = pd.to_numeric(current, errors="coerce")
    previous_num = pd.to_numeric(previous, errors="coerce")
    if pd.isna(current_num) or pd.isna(previous_num):
        return None
    return f"{100 * (float(current_num) - float(previous_num)):+.2f} pp"


def _previous_snapshot(history: pd.DataFrame, team: str, current_time: pd.Timestamp) -> pd.Series:
    if history.empty or pd.isna(current_time):
        return pd.Series(dtype=object)
    rows = history[(history["team"] == team) & (history["generated_at_utc"] < current_time)].sort_values("generated_at_utc")
    return rows.iloc[-1] if not rows.empty else pd.Series(dtype=object)


def _movement_sentence(change, percent) -> str:
    change_num = pd.to_numeric(change, errors="coerce")
    percent_num = pd.to_numeric(percent, errors="coerce")
    if pd.isna(change_num):
        return "Previous official value unavailable"
    direction = "rose" if float(change_num) > 0 else ("fell" if float(change_num) < 0 else "was unchanged")
    percentage = f" ({float(percent_num):+.2f}%)" if pd.notna(percent_num) else ""
    return f"{direction} {abs(float(change_num)):.2f} CM{percentage}"


def render_market_story() -> None:
    static = load_static_data()
    prices = static["prices"]
    history = static["history"]
    processed = static["processed_ledger"]

    st.markdown(
        '''
        <div class="cm-hero">
            <div class="cm-eyebrow">CupMarket 2026 · Market Story</div>
            <h1>What changed, from what, and when?</h1>
            <p>Follow one country's official price from the previous model value to the current one, then inspect the probability shifts and completed results included in that update.</p>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    if prices.empty:
        st.warning("No market-price data is available.")
        return

    teams = prices.sort_values("market_rank")["team"].astype(str).tolist()
    requested = st.session_state.pop("cupmarket_market_team", None)
    if requested in teams:
        st.session_state["market_story_team"] = requested
    elif st.session_state.get("market_story_team") not in teams:
        st.session_state["market_story_team"] = teams[0]

    team = st.selectbox("Country", teams, key="market_story_team")
    current = prices[prices["team"] == team].iloc[-1]
    current_time = pd.to_datetime(current.get("generated_at_utc"), errors="coerce", utc=True)
    previous = _previous_snapshot(history, team, current_time)

    current_price = pd.to_numeric(current.get("cupmarket_price"), errors="coerce")
    previous_price = pd.to_numeric(current.get("previous_price"), errors="coerce")
    if pd.isna(previous_price) and not previous.empty:
        previous_price = pd.to_numeric(previous.get("cupmarket_price"), errors="coerce")
    change = pd.to_numeric(current.get("price_change"), errors="coerce")
    if pd.isna(change) and pd.notna(current_price) and pd.notna(previous_price):
        change = float(current_price) - float(previous_price)
    percent = pd.to_numeric(current.get("price_change_percent"), errors="coerce")
    if pd.isna(percent) and pd.notna(change) and pd.notna(previous_price) and float(previous_price) != 0:
        percent = 100 * float(change) / float(previous_price)

    time_text = "Update time unavailable" if pd.isna(current_time) else current_time.strftime("%d %B %Y · %H:%M UTC")
    st.markdown(f"### {team}")
    summary = st.columns(4)
    summary[0].metric("Current price", f"{float(current_price):.2f} CM" if pd.notna(current_price) else "—")
    summary[1].metric("Previous price", f"{float(previous_price):.2f} CM" if pd.notna(previous_price) else "—")
    delta_text = None
    if pd.notna(change):
        delta_text = f"{float(change):+.2f} CM"
        if pd.notna(percent):
            delta_text += f" · {float(percent):+.2f}%"
    summary[2].metric("Since last model update", _movement_sentence(change, percent), delta=delta_text, delta_color="off")
    summary[3].metric("Market rank", f"#{int(current['market_rank'])}" if pd.notna(current.get("market_rank")) else "—")
    st.caption(f"Published {time_text}. This comparison is against the previous model run, not necessarily yesterday.")

    st.markdown("#### Probability drivers")
    probability_fields = [
        ("Reach Round of 32", "prob_reach_round_32"),
        ("Reach quarter-final", "prob_reach_quarter_final"),
        ("Reach final", "prob_reach_final"),
        ("Become champion", "prob_champion"),
    ]
    driver_columns = st.columns(4)
    for column, (label, field) in zip(driver_columns, probability_fields):
        old_value = previous.get(field) if not previous.empty else None
        column.metric(label, _pct(current.get(field)), delta=_pp_delta(current.get(field), old_value))

    if previous.empty:
        st.info("The previous probability snapshot is unavailable, so only the current probabilities can be shown.")
    else:
        changes = []
        for label, field in probability_fields:
            current_value = pd.to_numeric(current.get(field), errors="coerce")
            old_value = pd.to_numeric(previous.get(field), errors="coerce")
            if pd.notna(current_value) and pd.notna(old_value):
                changes.append((label, 100 * (float(current_value) - float(old_value))))
        changes.sort(key=lambda item: abs(item[1]), reverse=True)
        if changes:
            strongest = changes[0]
            direction = "improved" if strongest[1] > 0 else ("weakened" if strongest[1] < 0 else "was unchanged")
            st.write(
                f"The largest visible probability change was **{strongest[0]}**, which {direction} by **{abs(strongest[1]):.2f} percentage points**."
            )

    update_matches = latest_update_matches(processed, current_time)
    st.markdown("#### Results included in this market update")
    if update_matches.empty:
        st.info("The processed-match batch for this update is unavailable.")
    else:
        team_played = False
        for row in update_matches.sort_values("utc_date").itertuples(index=False):
            team_played = team_played or team in {str(row.home_team), str(row.away_team)}
            st.write(f"• {row.home_team} {int(row.home_score)}–{int(row.away_score)} {row.away_team}")
        if team_played:
            st.caption(
                f"{team} played in this batch. The published movement still reflects the full tournament recalculation, including every result above."
            )
        else:
            st.caption(
                f"{team} did not play in this batch. Its price moved because other results changed ratings, qualification paths and likely knockout opponents across the simulated tournament."
            )

    team_history = history[history["team"] == team].sort_values("generated_at_utc")
    if len(team_history) >= 2:
        figure = px.line(
            team_history,
            x="generated_at_utc",
            y="cupmarket_price",
            markers=True,
            title=f"{team} CupMarket price history",
        )
        figure.update_layout(
            template="plotly_white",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="#ffffff",
            margin=dict(l=16, r=16, t=52, b=16),
            height=360,
        )
        figure.update_xaxes(title=None, gridcolor="#edf0f5")
        figure.update_yaxes(title="CupMarket price", gridcolor="#edf0f5")
        st.plotly_chart(figure, use_container_width=True)
    else:
        st.info("A price-history chart will appear after at least two snapshots are available.")

    st.caption(
        "CupMarket prices are model fair values, not user-traded market prices. They update after completed results are processed and the full tournament is simulated again."
    )
