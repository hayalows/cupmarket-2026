from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from features.market_movement import add_rank_movement, rank_movement_text
from features.product_guidance import (
    render_country_snapshot,
    render_so_what,
    render_start_here_panel,
    render_todays_story,
)
from features.product_ui import render_official_data_caption
from features.tournament_data import load_static_data

ROOT = Path(__file__).resolve().parents[1]


def _inject_styles() -> None:
    path = ROOT / "assets" / "pulse_v3.css"
    if path.exists():
        st.markdown(f"<style>{path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def _score(row: pd.Series) -> str:
    home = pd.to_numeric(row.get("home_score_full_time"), errors="coerce")
    away = pd.to_numeric(row.get("away_score_full_time"), errors="coerce")
    return "vs" if pd.isna(home) or pd.isna(away) else f"{int(home)}–{int(away)}"


def _kickoff(value) -> str:
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    return "Time pending" if pd.isna(timestamp) else timestamp.strftime("%d %b · %H:%M UTC")


def _go_to_matches(view: str, match_id: int | None = None) -> None:
    st.session_state["cupmarket_match_hub_view"] = view
    if match_id is not None:
        st.session_state["cupmarket_match_hub_match_id"] = int(match_id)
    st.switch_page("pages/4_Match_Hub.py")


def _go_to_market(team: str) -> None:
    st.session_state["cupmarket_market_team"] = team
    st.switch_page("pages/5_Market_Story.py")


def _go_to_path(team: str | None = None) -> None:
    if team:
        st.session_state["cupmarket_path_requested_team"] = team
    st.switch_page("pages/7_Tournament_Path.py")


def _go_to_bracket(team: str | None = None) -> None:
    if team:
        st.session_state["cupmarket_path_requested_team"] = team
    st.switch_page("pages/8_Bracket_View.py")


def render_overview_v3(matches: pd.DataFrame, prices: pd.DataFrame, metadata: dict) -> None:
    _inject_styles()
    prices = add_rank_movement(prices)
    processed = load_static_data()["processed_ledger"]

    st.markdown(
        '<div class="cm-v3-banner"><div><strong>CupMarket Pulse</strong> · Start with a question, then open the page that explains it.</div><div class="cm-v3-badge">Clearer UX</div></div>',
        unsafe_allow_html=True,
    )

    if matches.empty:
        finished = live = upcoming = pd.DataFrame()
    else:
        finished = matches[matches["status"].isin(["FINISHED", "AWARDED"])].sort_values("utc_date", ascending=False)
        live = matches[matches["status"].isin(["IN_PLAY", "PAUSED"])].sort_values("utc_date")
        upcoming = matches[matches["status"].isin(["TIMED", "SCHEDULED"])].sort_values("utc_date")

    leader = prices.sort_values("cupmarket_price", ascending=False).iloc[0] if not prices.empty else pd.Series(dtype=object)
    latest_result = finished.iloc[0] if not finished.empty else pd.Series(dtype=object)
    next_match = upcoming.iloc[0] if not upcoming.empty else pd.Series(dtype=object)
    default_team = str(leader.get("team")) if not leader.empty else "Ghana"

    render_start_here_panel(default_team)
    render_todays_story(matches, prices)

    top = st.columns(2)
    with top[0]:
        with st.container(border=True):
            st.caption("RESULTS")
            st.metric("Completed", len(finished))
            if not latest_result.empty:
                st.write(f"Latest: **{latest_result.get('home_team')} {_score(latest_result)} {latest_result.get('away_team')}**")
            render_so_what("results", "Open results when you want to compare what the model expected with what actually happened.")
            if st.button("Review all results", key="pulse_finished", use_container_width=True):
                _go_to_matches("Results", int(latest_result["match_id"]) if not latest_result.empty else None)

    with top[1]:
        with st.container(border=True):
            st.caption("LIVE OR NEXT MATCH")
            st.metric("In play", len(live))
            if not live.empty:
                focus = live.iloc[0]
                st.write(f"**{focus.get('home_team')} {_score(focus)} {focus.get('away_team')}**")
                action = "Open live match"
                target_view = "Live"
                so_what = "This is where live score changes can affect group pressure and provisional outlook."
            elif not next_match.empty:
                focus = next_match
                st.write(f"No match live. Next: **{focus.get('home_team')} vs {focus.get('away_team')}**")
                action = "Open next match"
                target_view = "Upcoming"
                so_what = "Open this before kickoff to understand why the match matters."
            else:
                focus = pd.Series(dtype=object)
                st.write("No live or upcoming fixture available")
                action = "Open matches"
                target_view = "Live"
                so_what = "The match feed is current, but there is no active fixture to explain right now."
            st.caption(_kickoff(focus.get("utc_date")) if not focus.empty else "Feed is current")
            render_so_what("match", so_what)
            if st.button(action, key="pulse_live", use_container_width=True):
                _go_to_matches(target_view, int(focus["match_id"]) if not focus.empty else None)

    bottom = st.columns(2)
    with bottom[0]:
        with st.container(border=True):
            st.caption("UPCOMING")
            st.metric("Scheduled", len(upcoming))
            if not next_match.empty:
                st.write(f"Next: **{next_match.get('home_team')} vs {next_match.get('away_team')}**")
                st.caption(_kickoff(next_match.get("utc_date")))
            else:
                st.write("No upcoming fixture available")
            render_so_what("upcoming", "This helps users know what to watch next, not just what already happened.")
            if st.button("Explore upcoming fixtures", key="pulse_upcoming", use_container_width=True):
                _go_to_matches("Upcoming", int(next_match["match_id"]) if not next_match.empty else None)

    with bottom[1]:
        with st.container(border=True):
            st.caption("MARKET LEADER")
            if leader.empty:
                st.metric("Country", "—")
                st.write("Market data unavailable")
            else:
                price = float(leader["cupmarket_price"])
                change = pd.to_numeric(leader.get("price_change"), errors="coerce")
                percent = pd.to_numeric(leader.get("price_change_percent"), errors="coerce")
                previous = pd.to_numeric(leader.get("previous_price"), errors="coerce")
                delta = None if pd.isna(change) else f"{float(change):+.2f} CM" + (f" · {float(percent):+.2f}%" if pd.notna(percent) else "")
                st.metric(str(leader["team"]), f"{price:.2f} CM", delta=delta)
                rank = pd.to_numeric(leader.get("market_rank"), errors="coerce")
                rank_text = rank_movement_text(rank, leader.get("previous_market_rank"), include_previous=True)
                if pd.notna(rank):
                    st.write(f"Market rank: **#{int(rank)}** · {rank_text}")
                st.write(f"Previous price: **{float(previous):.2f} CM**" if pd.notna(previous) else "Previous price unavailable")
                generated = pd.to_datetime(leader.get("generated_at_utc"), errors="coerce", utc=True)
                st.caption("Since last model update · " + (generated.strftime("%d %b · %H:%M UTC") if pd.notna(generated) else "time unavailable"))
                render_so_what("market", "The leader is not only the most likely champion. The price includes value from reaching earlier rounds too.")
                if st.button("Understand the move", key="pulse_market", use_container_width=True):
                    _go_to_market(str(leader["team"]))

    path_cols = st.columns(2)
    with path_cols[0]:
        with st.container(border=True):
            st.caption("BRACKET")
            st.markdown("#### Confirmed and projected road")
            st.write("See official knockout fixtures where they exist, plus projected slots where the model is still waiting on results.")
            render_so_what("bracket", "This is the fastest way to understand who may meet who next.")
            if st.button("Open bracket", key="pulse_bracket", use_container_width=True):
                _go_to_bracket(default_team)
    with path_cols[1]:
        with st.container(border=True):
            st.caption("COUNTRY SNAPSHOT")
            st.markdown("#### One country, one clear view")
            st.write("Search a country and see its price, next match, qualification outlook and key links.")
            render_so_what("country", "This turns the app from a dashboard into a tool people can use quickly.")
            if st.button("Open country snapshot", key="pulse_country", use_container_width=True):
                st.session_state["cupmarket_snapshot_team"] = default_team
                st.switch_page("pages/Country_Snapshot.py")

    render_country_snapshot(matches, prices, default_team=default_team)

    st.markdown("### What changed recently")
    recent, movers_column = st.columns(2)
    with recent:
        st.markdown("#### Latest results")
        for row in finished.head(3).itertuples(index=False):
            series = pd.Series(row._asdict())
            st.write(f"**{series.get('home_team')} {_score(series)} {series.get('away_team')}**")
            st.caption(f"{str(series.get('group', '')).replace('GROUP_', 'Group ')} · {_kickoff(series.get('utc_date'))}")
        if not finished.empty and st.button("Open Results & Model Review", key="pulse_results_more", use_container_width=True):
            _go_to_matches("Results", int(finished.iloc[0]["match_id"]))

    with movers_column:
        st.markdown("#### Biggest market moves")
        if prices.empty or "price_change_percent" not in prices.columns:
            st.caption("Movement becomes available after multiple model updates.")
        else:
            movers = prices.assign(abs_move=pd.to_numeric(prices["price_change_percent"], errors="coerce").abs()).dropna(subset=["abs_move"]).sort_values("abs_move", ascending=False).head(5)
            display = movers[["market_rank", "team", "cupmarket_price", "price_change_percent", "previous_market_rank"]].copy()
            display["Rank move"] = display.apply(lambda row: rank_movement_text(row["market_rank"], row["previous_market_rank"]), axis=1)
            display = display.drop(columns=["previous_market_rank"])
            display.columns = ["Rank", "Country", "Price", "Change %", "Rank move"]
            display["Rank"] = display["Rank"].map(lambda value: f"#{int(value)}" if pd.notna(value) else "—")
            display["Price"] = display["Price"].map(lambda value: f"{float(value):.2f} CM")
            display["Change %"] = display["Change %"].map(lambda value: f"{float(value):+.2f}%")
            st.dataframe(display, hide_index=True, use_container_width=True)

    render_official_data_caption(prices)
    st.caption(
        f"Tournament feed: {len(finished)} finished · {len(live)} live · {len(upcoming)} upcoming. "
        f"Model ledger records {len(processed)} processed results."
    )
