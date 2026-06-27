from __future__ import annotations

import pandas as pd
import streamlit as st

LIVE_STATUSES = {"IN_PLAY", "PAUSED"}
UPCOMING_STATUSES = {"TIMED", "SCHEDULED"}
FINISHED_STATUSES = {"FINISHED", "AWARDED"}


def _percent(value, digits: int = 1) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "—"
    return f"{100 * float(number):.{digits}f}%"


def _number(value, digits: int = 2, suffix: str = "") -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "—"
    return f"{float(number):.{digits}f}{suffix}"


def _score(row: pd.Series) -> str:
    home = pd.to_numeric(row.get("home_score_full_time"), errors="coerce")
    away = pd.to_numeric(row.get("away_score_full_time"), errors="coerce")
    if pd.isna(home) or pd.isna(away):
        return "vs"
    return f"{int(home)}–{int(away)}"


def _kickoff(value) -> str:
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(timestamp):
        return "Time pending"
    return timestamp.strftime("%d %b · %H:%M UTC")


def _team_matches(matches: pd.DataFrame, team: str) -> pd.DataFrame:
    if matches.empty or not {"home_team", "away_team"}.issubset(matches.columns):
        return pd.DataFrame()
    return matches.loc[
        matches["home_team"].astype(str).eq(team)
        | matches["away_team"].astype(str).eq(team)
    ].copy()


def _price_row(prices: pd.DataFrame, team: str) -> pd.Series:
    if prices.empty or "team" not in prices.columns:
        return pd.Series(dtype=object)
    rows = prices.loc[prices["team"].astype(str) == team]
    if rows.empty:
        return pd.Series(dtype=object)
    return rows.iloc[0]


def go_to(page: str, team: str | None = None) -> None:
    if team:
        st.session_state["cupmarket_snapshot_team"] = team
        st.session_state["cupmarket_path_requested_team"] = team
        st.session_state["cupmarket_market_team"] = team
    st.switch_page(page)


def render_start_here_panel(default_team: str | None = None) -> None:
    st.markdown("### Start here")
    st.caption("Pick the question you want answered. Each card opens the clearest page for that job.")
    rows = [
        ("What changed?", "Latest results, movers and tournament story", "pages/11_Tournament_Insights.py"),
        ("Check one country", "Price, next match, likely path and journey", "pages/Country_Snapshot.py"),
        ("See the bracket", "Confirmed and projected knockout view", "pages/8_Bracket_View.py"),
        ("Which match matters?", "Live and upcoming match context", "pages/4_Match_Hub.py"),
        ("Who is in danger?", "Qualification pressure and group outlook", "pages/2_Qualification_Lab.py"),
        ("Why did price move?", "Market story and rank movement", "pages/5_Market_Story.py"),
    ]
    for start in range(0, len(rows), 3):
        cols = st.columns(3)
        for col, (title, body, page) in zip(cols, rows[start : start + 3]):
            with col:
                with st.container(border=True):
                    st.markdown(f"**{title}**")
                    st.caption(body)
                    if st.button("Open", key=f"start_here_{page}_{title}", use_container_width=True):
                        go_to(page, default_team)


def render_todays_story(matches: pd.DataFrame, prices: pd.DataFrame) -> None:
    st.markdown("### Today's story")
    finished = pd.DataFrame()
    live = pd.DataFrame()
    upcoming = pd.DataFrame()
    if not matches.empty and "status" in matches.columns:
        finished = matches[matches["status"].isin(FINISHED_STATUSES)].sort_values("utc_date", ascending=False)
        live = matches[matches["status"].isin(LIVE_STATUSES)].sort_values("utc_date")
        upcoming = matches[matches["status"].isin(UPCOMING_STATUSES)].sort_values("utc_date")

    leader = prices.sort_values("cupmarket_price", ascending=False).iloc[0] if not prices.empty and "cupmarket_price" in prices.columns else pd.Series(dtype=object)
    latest = finished.iloc[0] if not finished.empty else pd.Series(dtype=object)
    next_match = live.iloc[0] if not live.empty else (upcoming.iloc[0] if not upcoming.empty else pd.Series(dtype=object))

    parts = []
    if not latest.empty:
        parts.append(f"Latest result: **{latest.get('home_team')} {_score(latest)} {latest.get('away_team')}**.")
    if not next_match.empty:
        status = "live now" if str(next_match.get("status")) in LIVE_STATUSES else "next"
        parts.append(f"The {status} match is **{next_match.get('home_team')} vs {next_match.get('away_team')}** at {_kickoff(next_match.get('utc_date'))}.")
    if not leader.empty:
        price = _number(leader.get("cupmarket_price"), suffix=" CM")
        champion = _percent(leader.get("prob_champion"))
        parts.append(f"Market leader: **{leader.get('team')}** at **{price}**, title chance **{champion}**.")

    if not parts:
        st.info("CupMarket is waiting for match and market data to publish the current story.")
    else:
        st.info(" ".join(parts))


def render_so_what(label: str, text: str) -> None:
    st.caption(f"So what: {text}")


def render_country_snapshot(matches: pd.DataFrame, prices: pd.DataFrame, default_team: str | None = None) -> None:
    st.markdown("### Country snapshot")
    st.caption("Fast answer first. Detailed journey and path context appear below.")
    if prices.empty or "team" not in prices.columns:
        st.warning("Country market data is not available yet.")
        return

    teams = sorted(prices["team"].dropna().astype(str).unique())
    requested = st.session_state.pop("cupmarket_snapshot_team", None)
    default = requested if requested in teams else (default_team if default_team in teams else ("Ghana" if "Ghana" in teams else teams[0]))
    team = st.selectbox("Country", teams, index=teams.index(default), key="country_snapshot_team")
    row = _price_row(prices, team)
    team_matches = _team_matches(matches, team)
    next_matches = pd.DataFrame()
    latest_result = pd.Series(dtype=object)
    if not team_matches.empty and "status" in team_matches.columns:
        latest_finished = team_matches[team_matches["status"].isin(FINISHED_STATUSES)].sort_values("utc_date", ascending=False)
        next_matches = team_matches[team_matches["status"].isin(LIVE_STATUSES | UPCOMING_STATUSES)].sort_values("utc_date")
        if not latest_finished.empty:
            latest_result = latest_finished.iloc[0]

    cols = st.columns(4)
    cols[0].metric("Price", _number(row.get("cupmarket_price"), suffix=" CM") if not row.empty else "—")
    cols[1].metric("Reach R32", _percent(row.get("prob_reach_round_32")) if not row.empty else "—")
    cols[2].metric("Reach final", _percent(row.get("prob_reach_final")) if not row.empty else "—")
    cols[3].metric("Win title", _percent(row.get("prob_champion")) if not row.empty else "—")

    if not latest_result.empty:
        st.write(f"Latest result: **{latest_result.get('home_team')} {_score(latest_result)} {latest_result.get('away_team')}**")
    if not next_matches.empty:
        focus = next_matches.iloc[0]
        st.write(f"Next match: **{focus.get('home_team')} vs {focus.get('away_team')}** · {_kickoff(focus.get('utc_date'))}")
    if not row.empty:
        movement = pd.to_numeric(row.get("price_change_percent"), errors="coerce")
        if pd.notna(movement):
            direction = "up" if movement > 0 else "down" if movement < 0 else "flat"
            render_so_what("price", f"{team} is {direction} {float(movement):+.2f}% since the previous model update.")
        else:
            render_so_what("price", "Price movement appears after at least two model publications.")

    action_cols = st.columns(3)
    with action_cols[0]:
        if st.button("Country path", use_container_width=True):
            go_to("pages/7_Tournament_Path.py", team)
    with action_cols[1]:
        if st.button("Market story", use_container_width=True):
            go_to("pages/5_Market_Story.py", team)
    with action_cols[2]:
        if st.button("Bracket", use_container_width=True):
            go_to("pages/8_Bracket_View.py", team)
