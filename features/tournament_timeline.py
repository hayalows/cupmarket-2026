from __future__ import annotations

import pandas as pd
import streamlit as st


def _time(value) -> str:
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return "Time unavailable"
    return ts.strftime("%d %b · %H:%M UTC")


def _score(row: pd.Series) -> str:
    home = pd.to_numeric(row.get("home_score"), errors="coerce")
    away = pd.to_numeric(row.get("away_score"), errors="coerce")
    if pd.isna(home) or pd.isna(away):
        return "vs"
    return f"{int(home)}-{int(away)}"


def _winner(row: pd.Series) -> str:
    home = pd.to_numeric(row.get("home_score"), errors="coerce")
    away = pd.to_numeric(row.get("away_score"), errors="coerce")
    if pd.isna(home) or pd.isna(away):
        return "No result"
    if home > away:
        return str(row.get("home_team"))
    if away > home:
        return str(row.get("away_team"))
    return "Draw"


def render_tournament_timeline(processed_ledger: pd.DataFrame, movements: pd.DataFrame) -> None:
    st.markdown("## Tournament Timeline")
    st.caption("A chronological memory of the tournament from the data CupMarket has already processed.")

    if not isinstance(processed_ledger, pd.DataFrame) or processed_ledger.empty:
        st.info("Processed match ledger is not available yet.")
        return
    if not {"home_team", "away_team", "home_score", "away_score"}.issubset(processed_ledger.columns):
        st.info("Processed match ledger needs score columns before the timeline can be shown.")
        return

    rows = processed_ledger.copy()
    time_column = "processed_at_utc" if "processed_at_utc" in rows.columns else "utc_date"
    rows[time_column] = pd.to_datetime(rows.get(time_column), errors="coerce", utc=True)
    rows = rows.sort_values(time_column, ascending=False, na_position="last")

    days = rows[time_column].dt.date.dropna().unique().tolist()
    if days:
        day = st.selectbox("Timeline date", ["All"] + [str(d) for d in days], key="timeline_day")
        if day != "All":
            rows = rows.loc[rows[time_column].dt.date.astype(str) == day]

    st.metric("Processed matches shown", len(rows))

    for _, row in rows.head(30).iterrows():
        title = f"{row.get('home_team')} {_score(row)} {row.get('away_team')}"
        stage = str(row.get("stage", "")).replace("_", " ").title()
        with st.container(border=True):
            st.markdown(f"**{title}**")
            st.caption(f"{_time(row.get(time_column))} · {stage}")
            st.write(f"Winner: **{_winner(row)}**")
            if isinstance(movements, pd.DataFrame) and not movements.empty and "trigger_matches" in movements.columns:
                trigger = movements["trigger_matches"].astype(str).str.contains(str(row.get("home_team")), regex=False, na=False) | movements["trigger_matches"].astype(str).str.contains(str(row.get("away_team")), regex=False, na=False)
                linked = movements.loc[trigger]
                if not linked.empty:
                    biggest = linked.copy()
                    if "price_change_percent" in biggest.columns:
                        biggest["price_change_percent"] = pd.to_numeric(biggest["price_change_percent"], errors="coerce")
                        biggest = biggest.sort_values("price_change_percent", key=lambda s: s.abs(), ascending=False)
                    focus = biggest.iloc[0]
                    st.caption(f"Market note: {focus.get('team')} moved {focus.get('price_change_percent', '—')}% in a related update.")
