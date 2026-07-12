from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from features.bracket_view import (
    STAGE_ALIASES,
    _confirmed_source,
    _projected_round32,
    _render_projected_r32,
    _render_stage_forecast,
)
from features.tournament_path_data import round_of_16_build

ACTIVE_STATUSES = {"IN_PLAY", "LIVE", "PAUSED", "SUSPENDED"}
FINISHED_STATUSES = {"FINISHED", "AWARDED"}
UPCOMING_STATUSES = {"TIMED", "SCHEDULED"}


def _clean_team(value: Any) -> str:
    try:
        if pd.isna(value):
            return "TBD"
    except (TypeError, ValueError):
        pass
    text = str(value or "").strip()
    return "TBD" if not text or text.lower() in {"nan", "none", "null", "tbd"} else text


def _number(value: Any) -> int | None:
    parsed = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(parsed) else int(parsed)


def _first_number(row: pd.Series, fields: tuple[str, ...]) -> int | None:
    for field in fields:
        value = _number(row.get(field))
        if value is not None:
            return value
    return None


def _logical_match_number(row: pd.Series, fallback: Any = None) -> int | None:
    return _first_number(
        row,
        ("logical_match_number", "bracket_match_number", "match_number"),
    ) or _number(fallback)


def _api_match_id(row: pd.Series) -> int | None:
    return _first_number(row, ("api_match_id", "match_id"))


def _decision_method(row: pd.Series) -> str:
    raw = str(row.get("decision_method") or row.get("duration") or "").upper()
    home_penalties = _first_number(row, ("home_penalties", "home_score_penalties"))
    away_penalties = _first_number(row, ("away_penalties", "away_score_penalties"))
    if "PENALT" in raw or (home_penalties is not None and away_penalties is not None):
        return "penalties"
    if "EXTRA" in raw:
        return "extra_time"
    return "regular_time"


def _playing_score(row: pd.Series) -> tuple[int | None, int | None]:
    home = _first_number(row, ("home_score", "home_score_full_time"))
    away = _first_number(row, ("away_score", "away_score_full_time"))
    method = _decision_method(row)
    if method != "penalties":
        return home, away

    regular_home = _first_number(row, ("home_score_regular_time",))
    regular_away = _first_number(row, ("away_score_regular_time",))
    extra_home = _first_number(row, ("home_score_extra_time",))
    extra_away = _first_number(row, ("away_score_extra_time",))
    if regular_home is not None and regular_away is not None:
        return regular_home + (extra_home or 0), regular_away + (extra_away or 0)

    home_penalties = _first_number(row, ("home_penalties", "home_score_penalties"))
    away_penalties = _first_number(row, ("away_penalties", "away_score_penalties"))
    if None not in (home, away, home_penalties, away_penalties):
        candidate_home = int(home) - int(home_penalties)
        candidate_away = int(away) - int(away_penalties)
        if candidate_home >= 0 and candidate_away >= 0 and candidate_home == candidate_away:
            return candidate_home, candidate_away
    return home, away


def _score_text(row: pd.Series) -> str:
    home, away = _playing_score(row)
    return "vs" if home is None or away is None else f"{home}–{away}"


def _status_key(row: pd.Series) -> str:
    raw = str(row.get("status") or "").strip().upper()
    if raw in ACTIVE_STATUSES | FINISHED_STATUSES | UPCOMING_STATUSES:
        return raw
    advancing = _clean_team(row.get("advancing_team"))
    home, away = _playing_score(row)
    if advancing != "TBD" or (home is not None and away is not None):
        return "FINISHED"
    return "SCHEDULED"


def _target_view(row: pd.Series) -> str:
    status = _status_key(row)
    if status in ACTIVE_STATUSES:
        return "Live"
    if status in FINISHED_STATUSES:
        return "Results"
    return "Upcoming"


def _timestamp(value: Any) -> str:
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(timestamp):
        return "Time pending"
    return timestamp.strftime("%d %b %Y · %H:%M UTC")


def _decision_text(row: pd.Series) -> str:
    status = _status_key(row)
    if status in ACTIVE_STATUSES:
        return "Live now"
    if status not in FINISHED_STATUSES:
        return _timestamp(row.get("utc_date", row.get("kickoff_utc")))

    advancing = _clean_team(row.get("advancing_team"))
    method = _decision_method(row)
    if method == "penalties":
        home_penalties = _first_number(row, ("home_penalties", "home_score_penalties"))
        away_penalties = _first_number(row, ("away_penalties", "away_score_penalties"))
        shootout = (
            f" {home_penalties}–{away_penalties}"
            if home_penalties is not None and away_penalties is not None
            else ""
        )
        return (
            f"{advancing} won{shootout} on penalties"
            if advancing != "TBD"
            else f"Decided{shootout} on penalties"
        )
    if method == "extra_time":
        return (
            f"{advancing} won after extra time"
            if advancing != "TBD"
            else "Finished after extra time"
        )
    return (
        f"{advancing} won in regular time"
        if advancing != "TBD"
        else "Finished in regular time"
    )


def _open_match(match_id: int, view: str) -> None:
    st.session_state["cupmarket_match_hub_view"] = view
    st.session_state["cupmarket_match_hub_match_id"] = int(match_id)
    st.switch_page("pages/4_Match_Hub.py")


def _button_label(view: str) -> str:
    return {
        "Live": "Open live match",
        "Results": "Open result details",
        "Upcoming": "Open fixture",
    }.get(view, "Open match")


def _render_official_match(row: pd.Series, stage_name: str, fallback: Any) -> None:
    home = _clean_team(row.get("home_team"))
    away = _clean_team(row.get("away_team"))
    number = _logical_match_number(row, fallback)
    api_match_id = _api_match_id(row)
    view = _target_view(row)
    advancing = _clean_team(row.get("advancing_team"))

    with st.container(border=True):
        st.caption(f"{stage_name} · Match {number if number is not None else '—'}")
        st.markdown(f"### {home} {_score_text(row)} {away}")
        decision = _decision_text(row)
        if _decision_method(row) == "penalties" and _status_key(row) in FINISHED_STATUSES:
            st.info(decision)
        elif _decision_method(row) == "extra_time" and _status_key(row) in FINISHED_STATUSES:
            st.warning(decision)
        else:
            st.write(decision)
        if advancing != "TBD" and _status_key(row) in FINISHED_STATUSES:
            st.caption(f"Advanced: {advancing}")
        if api_match_id is not None:
            if st.button(
                _button_label(view),
                key=f"mobile_bracket_open_{number}_{api_match_id}",
                use_container_width=True,
                type="primary" if view == "Live" else "secondary",
            ):
                _open_match(api_match_id, view)
        else:
            st.caption("Match details will become available when the official fixture ID is published.")


def _render_confirmed_matches(source: pd.DataFrame, stage_name: str, limit: int = 16) -> bool:
    if source.empty or "stage" not in source.columns:
        return False
    aliases = STAGE_ALIASES.get(stage_name, [])
    rows = source.loc[source["stage"].astype(str).isin(aliases)].copy()
    if not rows.empty:
        if "utc_date" in rows.columns:
            rows["utc_date"] = pd.to_datetime(rows["utc_date"], errors="coerce", utc=True)
            rows = rows.sort_values("utc_date", na_position="last")
        for index, row in rows.head(limit).iterrows():
            _render_official_match(row, stage_name, index + 1)
        return True

    if stage_name == "Round of 16":
        slots = round_of_16_build(source)
        if not slots.empty:
            for _, row in slots.head(limit).iterrows():
                with st.container(border=True):
                    st.caption(f"Round of 16 · Match {int(row['match_number'])}")
                    st.markdown(f"### {row['fixture']}")
                    st.write(f"{row['state']} · {_timestamp(row.get('kickoff_utc'))}")
                    st.caption("Built from Round-of-32 winners")
            return True
    return False


def render_stage_bracket_view(data: dict) -> None:
    st.markdown("### Stage view")
    st.caption(
        "Mobile-friendly view. Every official match has a full-width button, and finished matches state whether the win came in regular time, extra time or a penalty shootout."
    )

    mode = st.radio(
        "Data shown",
        ["Confirmed + projected", "Confirmed only", "Projected only"],
        horizontal=True,
        key="cupmarket_stage_bracket_mode",
    )
    stage = st.selectbox(
        "Stage",
        list(STAGE_ALIASES.keys()),
        key="cupmarket_stage_bracket_stage",
    )

    source = _confirmed_source(data)
    projected = _projected_round32(data)
    prices = data.get("prices", pd.DataFrame())
    if not isinstance(prices, pd.DataFrame):
        prices = pd.DataFrame()

    rendered = False
    if mode != "Projected only":
        rendered = _render_confirmed_matches(source, stage, limit=16)
    if not rendered and mode != "Confirmed only":
        if stage == "Round of 32":
            rendered = _render_projected_r32(projected, limit=16)
        else:
            rendered = _render_stage_forecast(prices, stage, limit=10)
    if not rendered:
        st.info("Waiting for bracket data for this stage.")

    with st.expander("How result labels work", expanded=False):
        st.markdown(
            "**Won in regular time:** the match was decided during normal play.\n\n"
            "**Won after extra time:** the displayed score includes extra-time goals.\n\n"
            "**Won on penalties:** the main score shows goals from play, while the shootout score is shown separately."
        )
