from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from features.market_movement import add_rank_movement, rank_movement_text
from features.match_ui import match_stage_label
from features.official_data import load_latest_csv
from features.product_guidance import (
    render_country_snapshot,
    render_so_what,
    render_start_here_panel,
    render_todays_story,
)
from features.product_ui import render_official_data_caption
from features.tournament_data import load_static_data

ROOT = Path(__file__).resolve().parents[1]
KNOCKOUT_PROGRESS_PATH = ROOT / "data" / "knockout_progress_latest.csv"
LIVE_STATUSES = {"IN_PLAY", "LIVE", "PAUSED", "SUSPENDED"}
UPCOMING_STATUSES = {"TIMED", "SCHEDULED"}
FINISHED_STATUSES = {"FINISHED", "AWARDED"}
EXIT_STAGE_COLUMNS = [
    ("prob_group_exit", "Group stage"),
    ("prob_round_32_exit", "Round of 32"),
    ("prob_round_16_exit", "Round of 16"),
    ("prob_quarter_final_exit", "Quarter-final"),
    ("prob_semi_final_exit", "Semi-final"),
    ("prob_runner_up", "Final"),
]


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


def _numeric(value, default: float = 0.0) -> float:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return default
    return float(number)


def _stage_text(row: pd.Series) -> str:
    label = match_stage_label(row)
    return label if label else str(row.get("stage", "Tournament")).replace("_", " ").title()


def _exit_stage(row: pd.Series) -> str:
    for column, label in EXIT_STAGE_COLUMNS:
        if _numeric(row.get(column)) >= 0.999:
            return label
    if _numeric(row.get("prob_champion")) <= 0.0:
        values = [
            (_numeric(row.get(column)), label)
            for column, label in EXIT_STAGE_COLUMNS
            if column in row.index
        ]
        if values:
            return max(values, key=lambda item: item[0])[1]
        return "Eliminated"
    return "Still alive"


def _eliminated_teams(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty or "team" not in prices.columns:
        return pd.DataFrame()
    rows = []
    for _, row in prices.iterrows():
        exit_stage = _exit_stage(row)
        champion = _numeric(row.get("prob_champion"))
        still_alive = exit_stage == "Still alive" or champion > 0.0
        if still_alive:
            continue
        rows.append(
            {
                "Country": row.get("team"),
                "Exit": exit_stage,
                "Price": f"{_numeric(row.get('cupmarket_price')):.2f} CM",
                "Champion": "0.0%",
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["Exit", "Country"]).reset_index(drop=True)


def _alive_teams(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty or "team" not in prices.columns:
        return pd.DataFrame()
    rows = prices.copy()
    rows["exit_stage"] = rows.apply(_exit_stage, axis=1)
    rows = rows.loc[rows["exit_stage"].eq("Still alive")].copy()
    if rows.empty:
        return rows
    rows["cupmarket_price"] = pd.to_numeric(rows["cupmarket_price"], errors="coerce")
    return rows.sort_values("cupmarket_price", ascending=False).reset_index(drop=True)


def _load_knockout_progress() -> pd.DataFrame:
    return load_latest_csv(KNOCKOUT_PROGRESS_PATH)


def _knockout_results(matches: pd.DataFrame, progress: pd.DataFrame) -> pd.DataFrame:
    source = progress.copy() if isinstance(progress, pd.DataFrame) else pd.DataFrame()
    if source.empty and not matches.empty:
        source = matches.copy()
        if "stage" in source.columns:
            source = source.loc[source["stage"].astype(str).ne("GROUP_STAGE")].copy()
    if source.empty or "status" not in source.columns:
        return pd.DataFrame()
    source = source.loc[source["status"].astype(str).isin(FINISHED_STATUSES)].copy()
    if source.empty:
        return source
    if "utc_date" in source.columns:
        source["utc_date"] = pd.to_datetime(source["utc_date"], errors="coerce", utc=True)
        source = source.sort_values("utc_date", ascending=False, na_position="last")
    rows = []
    for _, row in source.iterrows():
        home = row.get("home_team")
        away = row.get("away_team")
        home_score = row.get("home_score", row.get("home_score_full_time"))
        away_score = row.get("away_score", row.get("away_score_full_time"))
        home_goals = pd.to_numeric(home_score, errors="coerce")
        away_goals = pd.to_numeric(away_score, errors="coerce")
        score = "vs" if pd.isna(home_goals) or pd.isna(away_goals) else f"{int(home_goals)}-{int(away_goals)}"
        advancing = row.get("advancing_team")
        if not advancing or str(advancing).lower() == "nan":
            winner = str(row.get("winner", "") or "").upper()
            if winner == "HOME_TEAM":
                advancing = home
            elif winner == "AWAY_TEAM":
                advancing = away
            elif pd.notna(home_goals) and pd.notna(away_goals):
                advancing = home if home_goals > away_goals else away if away_goals > home_goals else ""
        eliminated = ""
        if advancing == home:
            eliminated = away
        elif advancing == away:
            eliminated = home
        rows.append(
            {
                "Stage": _stage_text(row),
                "Result": f"{home} {score} {away}",
                "Advanced": advancing or "Pending",
                "Eliminated": eliminated or "Pending",
                "Kickoff": _kickoff(row.get("utc_date")),
                "match_id": row.get("api_match_id", row.get("match_id")),
            }
        )
    return pd.DataFrame(rows)


def _next_match_summary(matches: pd.DataFrame) -> pd.Series:
    if matches.empty or "status" not in matches.columns:
        return pd.Series(dtype=object)
    active_or_next = matches.loc[
        matches["status"].astype(str).isin(LIVE_STATUSES | UPCOMING_STATUSES)
    ].copy()
    if active_or_next.empty:
        return pd.Series(dtype=object)
    active_or_next["utc_date"] = pd.to_datetime(
        active_or_next.get("utc_date"), errors="coerce", utc=True
    )
    live = active_or_next.loc[active_or_next["status"].astype(str).isin(LIVE_STATUSES)]
    if not live.empty:
        return live.sort_values("utc_date").iloc[0]
    return active_or_next.sort_values("utc_date").iloc[0]


def render_tournament_state(matches: pd.DataFrame, prices: pd.DataFrame) -> None:
    progress = _load_knockout_progress()
    results = _knockout_results(matches, progress)
    eliminated = _eliminated_teams(prices)
    alive = _alive_teams(prices)
    next_match = _next_match_summary(matches)

    st.markdown("### Tournament state")
    metrics = st.columns(4)
    metrics[0].metric("Still alive", len(alive) if not alive.empty else 0)
    metrics[1].metric("Eliminated", len(eliminated) if not eliminated.empty else 0)
    metrics[2].metric("Knockout results", len(results) if not results.empty else 0)
    if next_match.empty:
        metrics[3].metric("Next match", "None")
    else:
        metrics[3].metric("Next match", str(next_match.get("status", "Scheduled")).title())

    if not results.empty:
        latest = results.iloc[0]
        st.success(
            f"Latest knockout decision: {latest['Result']}. "
            f"{latest['Advanced']} advanced; {latest['Eliminated']} is out."
        )
        action_cols = st.columns(3)
        with action_cols[0]:
            if st.button("Open match details", key="pulse_latest_match_detail", use_container_width=True):
                match_id = pd.to_numeric(latest.get("match_id"), errors="coerce")
                _go_to_matches("Results", int(match_id) if pd.notna(match_id) else None)
        with action_cols[1]:
            if st.button("Open advancing team", key="pulse_latest_advanced", use_container_width=True):
                _go_to_path(str(latest["Advanced"]))
        with action_cols[2]:
            if st.button("Open eliminated team", key="pulse_latest_eliminated", use_container_width=True):
                _go_to_path(str(latest["Eliminated"]))

    table_cols = st.columns(2)
    with table_cols[0]:
        st.markdown("#### Latest knockout decisions")
        if results.empty:
            st.caption("No knockout result has been published yet.")
        else:
            st.dataframe(
                results[["Stage", "Result", "Advanced", "Eliminated"]].head(6),
                hide_index=True,
                use_container_width=True,
            )
    with table_cols[1]:
        st.markdown("#### Eliminated teams")
        if eliminated.empty:
            st.caption("No team has a locked elimination row yet.")
        else:
            st.dataframe(
                eliminated.head(10),
                hide_index=True,
                use_container_width=True,
            )

    if not alive.empty:
        st.markdown("#### Still alive, ranked by CupMarket")
        display = alive.head(10).copy()
        columns = [
            column
            for column in [
                "market_rank",
                "team",
                "cupmarket_price",
                "prob_reach_round_16",
                "prob_reach_quarter_final",
                "prob_reach_final",
                "prob_champion",
            ]
            if column in display.columns
        ]
        display = display[columns].rename(
            columns={
                "market_rank": "Rank",
                "team": "Country",
                "cupmarket_price": "Price",
                "prob_reach_round_16": "Reach R16",
                "prob_reach_quarter_final": "Reach QF",
                "prob_reach_final": "Reach final",
                "prob_champion": "Champion",
            }
        )
        for column in ["Reach R16", "Reach QF", "Reach final", "Champion"]:
            if column in display.columns:
                display[column] = display[column].map(lambda value: f"{100 * _numeric(value):.1f}%")
        if "Price" in display.columns:
            display["Price"] = display["Price"].map(lambda value: f"{_numeric(value):.2f} CM")
        st.dataframe(display, hide_index=True, use_container_width=True)


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
    render_tournament_state(matches, prices)

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
            context = match_stage_label(series)
            caption = " · ".join(
                part for part in [context, _kickoff(series.get("utc_date"))] if part
            )
            st.caption(caption)
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
