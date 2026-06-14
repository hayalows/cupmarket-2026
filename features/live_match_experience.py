from __future__ import annotations

import pandas as pd
import streamlit as st

from backend.live_qualification import LIVE_STATUSES
from features.compact_match_room import render_compact_match_room
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


def _set_selected_match(match_id: int, notice: str) -> None:
    """Set the downstream selector without forcing a second Streamlit rerun."""
    st.session_state["cupmarket_selected_match_id"] = int(match_id)
    st.session_state["cupmarket_reset_status_filter"] = True
    st.session_state["cupmarket_match_notice"] = notice


def _render_quick_summary(row: pd.Series, label: str, detail: str) -> None:
    st.markdown(
        f"**{label}:** {row.get('home_team', 'TBD')} {score_text(row)} "
        f"{row.get('away_team', 'TBD')}  \n"
        f"{_group_text(row.get('group'))} · {detail}"
    )


def _render_no_live_state(matches: pd.DataFrame) -> None:
    upcoming = matches[matches["status"].isin(UPCOMING_STATUSES)].copy()
    upcoming = upcoming.sort_values(["utc_date", "match_id"])
    finished = matches[matches["status"].isin(FINISHED_STATUSES)].copy()
    finished = finished.sort_values(["utc_date", "match_id"], ascending=False)

    st.info(
        "No match is live. Forecast mode is active, and the next fixture is selected "
        "automatically below. Switch to the latest result in one tap."
    )

    options: list[str] = []
    rows: dict[str, pd.Series] = {}
    if not upcoming.empty:
        options.append("Next fixture")
        rows["Next fixture"] = upcoming.iloc[0]
    if not finished.empty:
        options.append("Latest result")
        rows["Latest result"] = finished.iloc[0]

    if not options:
        return

    default = options[0]
    if st.session_state.get("cupmarket_quick_view") not in options:
        st.session_state.pop("cupmarket_quick_view", None)

    choice = st.segmented_control(
        "Quick view",
        options,
        default=default,
        selection_mode="single",
        key="cupmarket_quick_view",
        help="Changes the selected match immediately; no extra open button is required.",
    )
    if choice is None:
        choice = default

    row = rows[choice]
    applied_token = f"{choice}:{int(row['match_id'])}"
    if st.session_state.get("cupmarket_quick_view_applied") != applied_token:
        st.session_state["cupmarket_quick_view_applied"] = applied_token
        _set_selected_match(
            int(row["match_id"]),
            f"Opened {row.get('home_team')} vs {row.get('away_team')}",
        )

    if choice == "Next fixture":
        _render_quick_summary(
            row,
            "Up next",
            f"{_kickoff_text(row.get('utc_date'))} · {_time_until(row.get('utc_date'))}",
        )
    else:
        _render_quick_summary(
            row,
            "Latest full time",
            _kickoff_text(row.get("utc_date")),
        )


def _render_live_state(matches: pd.DataFrame) -> None:
    live = matches[matches["status"].isin(LIVE_STATUSES)].copy()
    if live.empty:
        return
    live = live.sort_values(["utc_date", "match_id"])
    first_live = live.iloc[0]
    live_token = ",".join(str(int(value)) for value in live["match_id"].tolist())
    if st.session_state.get("cupmarket_live_session_token") != live_token:
        st.session_state["cupmarket_live_session_token"] = live_token
        _set_selected_match(
            int(first_live["match_id"]),
            f"Live now: {first_live.get('home_team')} vs {first_live.get('away_team')}",
        )

    count = len(live)
    groups = sorted({_group_text(value) for value in live["group"].dropna()})
    group_text = ", ".join(groups) if groups else "the tournament"
    st.success(
        f"{count} match{'es are' if count != 1 else ' is'} live in {group_text}. "
        "The first live fixture has been brought into focus."
    )


def render_match_experience(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    prices: pd.DataFrame,
) -> None:
    if matches.empty or "status" not in matches.columns:
        render_compact_match_room(matches, predictions, prices)
        return

    live_count = int(matches["status"].isin(LIVE_STATUSES).sum())
    if live_count:
        _render_live_state(matches)
    else:
        st.session_state.pop("cupmarket_live_session_token", None)
        _render_no_live_state(matches)

    notice = st.session_state.pop("cupmarket_match_notice", None)
    if notice:
        st.toast(notice, icon="⚽")

    render_compact_match_room(matches, predictions, prices)
