from __future__ import annotations

from typing import Any

import pandas as pd

from features.live_match_data import load_matches
from features.tournament_data import DATA_DIR
from features.tournament_path_data import load_tournament_path_data


TERMINAL_STATUSES = {"FINISHED", "AWARDED"}
ACTIVE_STATUSES = {"IN_PLAY", "LIVE", "PAUSED", "SUSPENDED"}
UPCOMING_STATUSES = {"TIMED", "SCHEDULED", "POSTPONED"}
STATUS_PRIORITY = {
    **{status: 1 for status in UPCOMING_STATUSES},
    **{status: 2 for status in ACTIVE_STATUSES},
    **{status: 3 for status in TERMINAL_STATUSES},
}


def _text(value: Any) -> str:
    try:
        if value is None or pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _number(value: Any) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(parsed) else float(parsed)


def _decision_method(row: pd.Series) -> str:
    raw = _text(row.get("duration")).upper()
    if "PENALT" in raw:
        return "penalties"
    if "EXTRA" in raw:
        return "extra_time"
    return "regular_time"


def _advancing_team(row: pd.Series) -> str:
    winner = _text(row.get("winner")).upper()
    home = _text(row.get("home_team"))
    away = _text(row.get("away_team"))
    if winner == "HOME_TEAM":
        return home
    if winner == "AWAY_TEAM":
        return away

    home_score = _number(row.get("home_score_full_time"))
    away_score = _number(row.get("away_score_full_time"))
    if home_score is not None and away_score is not None:
        if home_score > away_score:
            return home
        if away_score > home_score:
            return away
    return ""


def _status_priority(value: Any) -> int:
    return STATUS_PRIORITY.get(_text(value).upper(), 0)


def merge_live_state_into_progress(
    progress: pd.DataFrame,
    matches: pd.DataFrame,
) -> pd.DataFrame:
    """Overlay the newest match status and score without regressing final results.

    The knockout processor publishes probabilities and bracket progression, while the
    live feed can update a score sooner. This merge keeps those responsibilities
    separate and prevents a delayed model run from leaving the visual bracket stale.
    """
    if progress.empty or matches.empty or "match_id" not in matches.columns:
        return progress.copy()

    id_column = next(
        (column for column in ("api_match_id", "match_id") if column in progress.columns),
        None,
    )
    if id_column is None:
        return progress.copy()

    live = matches.copy()
    live["match_id"] = pd.to_numeric(live["match_id"], errors="coerce")
    live = live.dropna(subset=["match_id"])
    if live.empty:
        return progress.copy()
    live["match_id"] = live["match_id"].astype(int)
    if "last_updated" in live.columns:
        live["last_updated"] = pd.to_datetime(
            live["last_updated"], errors="coerce", utc=True
        )
        live = live.sort_values("last_updated", na_position="first")
    live_by_id = {
        int(row["match_id"]): pd.Series(row)
        for row in live.drop_duplicates("match_id", keep="last").to_dict("records")
    }

    output = progress.copy()
    output[id_column] = pd.to_numeric(output[id_column], errors="coerce")
    for index, current in output.iterrows():
        match_id = current.get(id_column)
        if pd.isna(match_id):
            continue
        fresh = live_by_id.get(int(match_id))
        if fresh is None:
            continue

        current_status = _text(current.get("status")).upper()
        fresh_status = _text(fresh.get("status")).upper()
        if _status_priority(fresh_status) < _status_priority(current_status):
            continue

        if fresh_status:
            output.at[index, "status"] = fresh_status
        for target, source in (
            ("home_team", "home_team"),
            ("away_team", "away_team"),
            ("home_score", "home_score_full_time"),
            ("away_score", "away_score_full_time"),
            ("duration", "duration"),
            ("home_penalties", "home_score_penalties"),
            ("away_penalties", "away_score_penalties"),
        ):
            value = fresh.get(source)
            try:
                missing = value is None or pd.isna(value)
            except (TypeError, ValueError):
                missing = value is None
            if not missing:
                output.at[index, target] = value

        if fresh_status in TERMINAL_STATUSES:
            output.at[index, "decision_method"] = _decision_method(fresh)
            winner = _advancing_team(fresh)
            if winner:
                output.at[index, "advancing_team"] = winner

    return output


def load_bracket_page_data() -> dict[str, Any]:
    """Load bracket publications and reconcile their cards with the live feed."""
    data = load_tournament_path_data()
    matches, source = load_matches(DATA_DIR / "world_cup_2026_matches_latest.csv")
    data["matches"] = matches
    data["match_source"] = source

    progress = data.get("progress", pd.DataFrame())
    if isinstance(progress, pd.DataFrame):
        data["progress"] = merge_live_state_into_progress(progress, matches)
    return data
