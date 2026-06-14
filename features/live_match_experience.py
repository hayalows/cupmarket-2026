from __future__ import annotations

import pandas as pd
import streamlit as st

from backend.live_qualification import LIVE_STATUSES
from features.live_match_room import render_live_match_centre
from features.match_ui import score_text

UPCOMING_STATUSES = {"TIMED", "SCHEDULED"}
FINISHED_STATUSES = {"FINISHED", "AWARDED"}


def _group_text(value) -> str:
    text = str(value or "")
    return text.replace("GROUP_", "Group ").replace("_", " ").title()


def _kickoff_text(value) -> str:
    kickoff = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(kickoff):
        return "Kickoff time pending"
    return kickoff.strftime("%a, %d %b · %H:%M UTC")


def _time_until(value) -> str:
    kickoff = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(kickoff):
        return "Time pending"
    minutes = int((kickoff - pd.Timestamp.now(tz="UTC")).total_seconds() // 60)
    if minutes <= 0:
        return "Starting soon"
    days, remainder = divmod(minutes, 1440)
    hours, mins = divmod(remainder, 60)
    if days:
        return f"In {days}d {hours}h"
    if hours:
        return f"In {hours}h {mins}m"
    return f"In {mins}m"


def _select_match(match_id: int) -> None:
    st.session_state["cupmarket_selected_match_id"] = int(match_id)
    st.session_state["cupmarket_reset_status_filter"] = True
    st.rerun()


def _match_card(row: pd.Series, label: str, detail: str) -> None:
    st.markdown(
        f'''
        <div class="cm-match-card">
            <div class="cm-match-meta">{label} · {_group_text(row.get('group'))}</div>
            <div class="cm-match-teams">
                <strong>{row.get('home_team', 'TBD')}</strong>
                <span>{score_text(row)}</span>
                <strong>{row.get('away_team', 'TBD')}</strong>
            </div>
            <div class="cm-match-meta">{detail}</div>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def _render_mode_card(column, title: str, mode: str, explanation: str) -> None:
    with column:
        st.markdown(f"**{title}**")
        st.markdown(f"### {mode}")
        st.caption(explanation)


def _render_no_live_state(matches: pd.DataFrame) -> None:
    upcoming = matches[matches["status"].isin(UPCOMING_STATUSES)].copy()
    upcoming = upcoming.sort_values(["utc_date", "match_id"])
    finished = matches[matches["status"].isin(FINISHED_STATUSES)].copy()
    finished = finished.sort_values(["utc_date", "match_id"], ascending=False)

    st.markdown("### Match Room status")
    st.info(
        "No match is live right now. The room is still useful: open the next fixture "
        "for its pre-match forecast, or review the latest result while the published "
        "market catches up after full time."
    )

    state_columns = st.columns(3)
    _render_mode_card(
        state_columns[0],
        "Before kickoff",
        "Forecast mode",
        "Read probabilities, expected goals and qualification scenarios.",
    )
    _render_mode_card(
        state_columns[1],
        "During play",
        "Live mode",
        "Follow outlook, group effects and provisional market pressure.",
    )
    _render_mode_card(
        state_columns[2],
        "After full time",
        "Review mode",
        "See the final score immediately; official repricing follows the model run.",
    )

    card_columns = st.columns(2)
    with card_columns[0]:
        st.markdown("#### Next fixture")
        if upcoming.empty:
            st.caption("No upcoming fixture is available in the current feed.")
        else:
            row = upcoming.iloc[0]
            _match_card(
                row,
                "UP NEXT",
                f"{_kickoff_text(row.get('utc_date'))} · {_time_until(row.get('utc_date'))}",
            )
            if st.button(
                "Open next-match forecast",
                key="open_next_match_forecast",
                use_container_width=True,
            ):
                _select_match(int(row["match_id"]))

    with card_columns[1]:
        st.markdown("#### Latest completed match")
        if finished.empty:
            st.caption("No completed fixture is available in the current feed.")
        else:
            row = finished.iloc[0]
            _match_card(
                row,
                "FULL TIME",
                _kickoff_text(row.get("utc_date")),
            )
            if st.button(
                "Review latest result",
                key="review_latest_result",
                use_container_width=True,
            ):
                _select_match(int(row["match_id"]))

    with st.expander("How the Match Room changes during the tournament"):
        st.markdown(
            "**Before kickoff:** the saved model forecast, expected goals, likely "
            "score and win/draw/loss qualification scenarios are available.\n\n"
            "**During play:** live score and time are combined with the published "
            "expected-goal rates to estimate the remaining match, provisional group "
            "position, next-goal effects and likely market pressure.\n\n"
            "**After full time:** the final score is visible immediately. Official "
            "ratings, tournament probabilities and CupMarket prices update only after "
            "the automated model processes the completed result."
        )


def _render_live_state(matches: pd.DataFrame) -> None:
    live = matches[matches["status"].isin(LIVE_STATUSES)].copy()
    if live.empty:
        return
    live = live.sort_values(["utc_date", "match_id"])
    count = len(live)
    groups = sorted({_group_text(value) for value in live["group"].dropna()})
    group_text = ", ".join(groups) if groups else "the tournament"
    st.success(
        f"{count} match{'es are' if count != 1 else ' is'} live in {group_text}. "
        "Open a live card below for current outlook, qualification impact, connected "
        "group effects and published-market context."
    )


def render_match_experience(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    prices: pd.DataFrame,
) -> None:
    if matches.empty or "status" not in matches.columns:
        render_live_match_centre(matches, predictions, prices)
        return

    live_count = int(matches["status"].isin(LIVE_STATUSES).sum())
    if live_count:
        _render_live_state(matches)
    else:
        _render_no_live_state(matches)

    render_live_match_centre(matches, predictions, prices)
