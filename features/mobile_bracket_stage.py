from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import urlencode

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

MOBILE_CARD_STYLES = """
<style>
a.cm-mobile-bracket-card,
div.cm-mobile-bracket-card {
  display: block;
  width: 100%;
  margin: 0 0 12px 0;
  padding: 15px 16px;
  border: 1px solid rgba(124, 131, 255, .35);
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(29, 37, 64, .98), rgba(23, 29, 51, .98));
  color: #f3f5fb !important;
  text-decoration: none !important;
  box-shadow: 0 10px 25px rgba(0, 0, 0, .16);
  touch-action: manipulation;
  -webkit-tap-highlight-color: rgba(124, 131, 255, .22);
  transition: transform 140ms ease, border-color 140ms ease, box-shadow 140ms ease;
}
a.cm-mobile-bracket-card:active,
a.cm-mobile-bracket-card:focus-visible,
a.cm-mobile-bracket-card:hover {
  transform: translateY(-2px);
  border-color: rgba(124, 131, 255, .95);
  box-shadow: 0 0 0 3px rgba(124, 131, 255, .12), 0 15px 30px rgba(0, 0, 0, .22);
  outline: none;
}
.cm-mobile-bracket-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 9px;
  color: #aeb7cc;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .05em;
  text-transform: uppercase;
}
.cm-mobile-bracket-badge {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(117, 223, 182, .12);
  color: #75dfb6;
  font-size: 10px;
  white-space: nowrap;
}
.cm-mobile-bracket-card.penalties .cm-mobile-bracket-badge {
  background: rgba(216, 180, 254, .12);
  color: #d8b4fe;
}
.cm-mobile-bracket-card.extra-time .cm-mobile-bracket-badge {
  background: rgba(250, 204, 107, .12);
  color: #facc6b;
}
.cm-mobile-bracket-card.live .cm-mobile-bracket-badge {
  background: rgba(255, 107, 125, .12);
  color: #ff9aa7;
}
.cm-mobile-bracket-fixture {
  margin-bottom: 8px;
  color: #ffffff;
  font-size: clamp(18px, 5vw, 23px);
  font-weight: 850;
  line-height: 1.22;
}
.cm-mobile-bracket-decision {
  color: #dfe5f2;
  font-size: 14px;
  line-height: 1.42;
}
.cm-mobile-bracket-advanced {
  margin-top: 6px;
  color: #9be5c8;
  font-size: 12px;
  font-weight: 750;
}
.cm-mobile-bracket-open {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid rgba(255, 255, 255, .08);
  color: #b9beff;
  font-size: 12px;
  font-weight: 800;
}
.cm-mobile-bracket-unavailable {
  margin-top: 10px;
  color: #aeb7cc;
  font-size: 11px;
}
</style>
"""


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


def _first_text(row: pd.Series, fields: tuple[str, ...]) -> str:
    for field in fields:
        value = row.get(field)
        try:
            if value is None or pd.isna(value):
                continue
        except (TypeError, ValueError):
            pass
        text = str(value).strip()
        if text and text.lower() not in {"nan", "none", "null"}:
            return text
    return ""


def _logical_match_number(row: pd.Series, fallback: Any = None) -> int | None:
    value = _first_number(
        row,
        ("logical_match_number", "bracket_match_number", "match_number"),
    )
    return value if value is not None else _number(fallback)


def _api_match_id(row: pd.Series) -> int | None:
    return _first_number(row, ("api_match_id", "match_id"))


def _decision_method(row: pd.Series) -> str:
    raw = _first_text(row, ("decision_method", "duration")).upper()
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
    raw = _first_text(row, ("status",)).upper()
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


def _badge_text(row: pd.Series) -> str:
    status = _status_key(row)
    if status in ACTIVE_STATUSES:
        return "Live"
    if status not in FINISHED_STATUSES:
        return "Upcoming"
    return {
        "penalties": "Penalties",
        "extra_time": "Extra time",
        "regular_time": "Regular time",
    }[_decision_method(row)]


def _card_class(row: pd.Series) -> str:
    if _status_key(row) in ACTIVE_STATUSES:
        return "live"
    return _decision_method(row).replace("_", "-")


def _render_official_match(row: pd.Series, stage_name: str, fallback: Any) -> None:
    home = _clean_team(row.get("home_team"))
    away = _clean_team(row.get("away_team"))
    number = _logical_match_number(row, fallback)
    api_match_id = _api_match_id(row)
    view = _target_view(row)
    advancing = _clean_team(row.get("advancing_team"))
    fixture = f"{home} {_score_text(row)} {away}"
    decision = _decision_text(row)
    advanced_html = (
        f'<div class="cm-mobile-bracket-advanced">Advanced: {escape(advancing)}</div>'
        if advancing != "TBD" and _status_key(row) in FINISHED_STATUSES
        else ""
    )
    top = (
        f'<div class="cm-mobile-bracket-top"><span>{escape(stage_name)} · Match '
        f'{escape(str(number if number is not None else "—"))}</span>'
        f'<span class="cm-mobile-bracket-badge">{escape(_badge_text(row))}</span></div>'
    )
    body = (
        f'{top}<div class="cm-mobile-bracket-fixture">{escape(fixture)}</div>'
        f'<div class="cm-mobile-bracket-decision">{escape(decision)}</div>{advanced_html}'
    )

    if api_match_id is not None:
        query = urlencode({"view": view, "match_id": int(api_match_id)})
        st.markdown(
            f'<a class="cm-mobile-bracket-card {escape(_card_class(row))}" '
            f'href="/4_Match_Hub?{escape(query)}" target="_self" '
            f'aria-label="Open {escape(fixture)} match details">{body}'
            f'<div class="cm-mobile-bracket-open">Tap for match details →</div></a>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="cm-mobile-bracket-card {escape(_card_class(row))}">{body}'
            '<div class="cm-mobile-bracket-unavailable">Match details will appear when the official fixture ID is published.</div></div>',
            unsafe_allow_html=True,
        )


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
    st.markdown(MOBILE_CARD_STYLES, unsafe_allow_html=True)
    st.markdown("### Stage view")
    st.caption(
        "Mobile-friendly view. Tap an official match card anywhere to open it. Finished matches state whether the win came in regular time, extra time or a penalty shootout."
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
