from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st

API_URL = "https://api.football-data.org/v4/competitions/WC/matches"
FINISHED_STATUSES = {"FINISHED", "AWARDED"}
LIVE_STATUSES = {"IN_PLAY", "PAUSED", "SUSPENDED"}
UPCOMING_STATUSES = {"TIMED", "SCHEDULED"}


class LiveFeedRequestError(RuntimeError):
    """A safe, classified error from the live football feed."""

    def __init__(
        self,
        message: str,
        *,
        kind: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code


def nested_get(dictionary: dict, keys: list[str], default=None):
    current: Any = dictionary
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def _score_value(match: dict, side: str):
    """Read the best score currently available from the provider payload."""
    for score_period in ("fullTime", "regularTime", "halfTime"):
        value = nested_get(match, ["score", score_period, side])
        if value is not None:
            return value
    return None


def parse_api_matches(payload: dict) -> pd.DataFrame:
    rows = []
    for match in payload.get("matches", []):
        rows.append(
            {
                "match_id": match.get("id"),
                "utc_date": match.get("utcDate"),
                "status": match.get("status"),
                "stage": match.get("stage"),
                "group": match.get("group"),
                "matchday": match.get("matchday"),
                "minute": match.get("minute"),
                "injury_time": match.get("injuryTime"),
                "home_team": nested_get(match, ["homeTeam", "name"]),
                "away_team": nested_get(match, ["awayTeam", "name"]),
                "winner": nested_get(match, ["score", "winner"]),
                "duration": nested_get(match, ["score", "duration"]),
                "home_score_full_time": _score_value(match, "home"),
                "away_score_full_time": _score_value(match, "away"),
                "last_updated": match.get("lastUpdated"),
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    frame["match_id"] = pd.to_numeric(frame["match_id"], errors="coerce")
    frame = frame.dropna(subset=["match_id"])
    frame["match_id"] = frame["match_id"].astype(int)
    for column in [
        "minute",
        "injury_time",
        "matchday",
        "home_score_full_time",
        "away_score_full_time",
    ]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ["utc_date", "last_updated"]:
        frame[column] = pd.to_datetime(frame[column], errors="coerce", utc=True)
    return frame.sort_values(["utc_date", "match_id"]).reset_index(drop=True)


def _safe_provider_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.reason or "The provider returned an unexpected response."
    if isinstance(payload, dict):
        return str(payload.get("message") or payload.get("error") or response.reason)
    return response.reason or "The provider returned an unexpected response."


def _classify_http_error(status_code: int) -> str:
    if status_code in {401, 403}:
        return "invalid_token"
    if status_code == 429:
        return "rate_limit"
    if 500 <= status_code:
        return "provider_outage"
    return "provider_error"


def _status_counts(matches: pd.DataFrame) -> dict[str, int]:
    if matches.empty or "status" not in matches.columns:
        return {}
    return {
        str(status): int(count)
        for status, count in matches["status"].fillna("UNKNOWN").value_counts().items()
    }


def expected_live_matches(
    matches: pd.DataFrame,
    now: pd.Timestamp | None = None,
    *,
    early_minutes: int = 10,
    late_hours: int = 4,
) -> pd.DataFrame:
    """Find fixtures whose kickoff window says they should probably be live."""
    required = {"utc_date", "status"}
    if matches.empty or not required.issubset(matches.columns):
        return pd.DataFrame()
    current = now or pd.Timestamp.now(tz="UTC")
    kickoff = pd.to_datetime(matches["utc_date"], errors="coerce", utc=True)
    window_start = kickoff - pd.Timedelta(minutes=early_minutes)
    window_end = kickoff + pd.Timedelta(hours=late_hours)
    return matches[
        matches["status"].isin(UPCOMING_STATUSES)
        & (current >= window_start)
        & (current <= window_end)
    ].copy()


def should_auto_refresh(matches: pd.DataFrame) -> bool:
    if matches.empty or "status" not in matches.columns:
        return False
    if matches["status"].isin(LIVE_STATUSES).any():
        return True
    return not expected_live_matches(matches).empty


@st.cache_data(ttl=45, show_spinner=False)
def fetch_live_matches(token: str) -> tuple[pd.DataFrame, dict]:
    try:
        response = requests.get(
            API_URL,
            headers={
                "X-Auth-Token": token,
                "Accept": "application/json",
                "User-Agent": "CupMarket-Streamlit/1.0",
            },
            timeout=20,
        )
    except requests.Timeout as exc:
        raise LiveFeedRequestError(
            "The live-score provider timed out.", kind="timeout"
        ) from exc
    except requests.RequestException as exc:
        raise LiveFeedRequestError(
            "The live-score provider could not be reached.", kind="network"
        ) from exc

    if response.status_code >= 400:
        kind = _classify_http_error(response.status_code)
        detail = _safe_provider_message(response)
        raise LiveFeedRequestError(
            f"Live-score request failed ({response.status_code}): {detail}",
            kind=kind,
            status_code=response.status_code,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise LiveFeedRequestError(
            "The live-score provider returned invalid JSON.", kind="invalid_response"
        ) from exc

    if not isinstance(payload, dict):
        raise LiveFeedRequestError(
            "The live-score provider returned an unexpected payload.",
            kind="invalid_response",
        )

    matches = parse_api_matches(payload)
    latest_provider_update = None
    if not matches.empty and "last_updated" in matches.columns:
        latest = matches["last_updated"].max()
        if pd.notna(latest):
            latest_provider_update = latest.isoformat()

    metadata = {
        "source": "Live football-data.org API",
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider_last_updated_utc": latest_provider_update,
        "http_status": response.status_code,
        "requests_remaining": (
            response.headers.get("X-RequestsAvailable")
            or response.headers.get("X-Requests-Available-Minute")
        ),
        "counter_reset": response.headers.get("X-RequestCounter-Reset"),
        "token_configured": True,
        "is_fallback": False,
        "failure_kind": None,
        "warning": None,
        "status_counts": _status_counts(matches),
    }
    return matches, metadata


def clear_live_match_cache() -> None:
    """Clear only the football feed cache, not every CupMarket cache."""
    fetch_live_matches.clear()


def read_snapshot(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    if "match_id" in frame.columns:
        frame["match_id"] = pd.to_numeric(frame["match_id"], errors="coerce")
        frame = frame.dropna(subset=["match_id"])
        frame["match_id"] = frame["match_id"].astype(int)
    for column in [
        "minute",
        "injury_time",
        "matchday",
        "home_score_full_time",
        "away_score_full_time",
    ]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ["utc_date", "last_updated"]:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce", utc=True)
    sort_columns = [column for column in ["utc_date", "match_id"] if column in frame.columns]
    return frame.sort_values(sort_columns).reset_index(drop=True) if sort_columns else frame


def load_matches(snapshot_path: Path) -> tuple[pd.DataFrame, dict]:
    token = ""
    try:
        token = str(st.secrets.get("FOOTBALL_DATA_TOKEN", "")).strip()
    except Exception:
        token = ""

    warning = None
    failure_kind = None
    status_code = None

    if token:
        try:
            matches, metadata = fetch_live_matches(token)
            if matches.empty:
                warning = "The live API returned no World Cup matches."
                failure_kind = "empty_response"
            else:
                expected = expected_live_matches(matches)
                active = matches[matches["status"].isin(LIVE_STATUSES)]
                metadata["expected_live_count"] = int(len(expected))
                metadata["active_match_count"] = int(len(active))
                if not expected.empty and active.empty:
                    metadata["feed_state"] = "provider_delayed"
                    metadata["warning"] = (
                        "A kickoff window is active, but the provider still marks the match "
                        "as scheduled. The feed may be delayed."
                    )
                else:
                    metadata["feed_state"] = "live" if not active.empty else "healthy"
                return matches, metadata
        except LiveFeedRequestError as exc:
            warning = str(exc)
            failure_kind = exc.kind
            status_code = exc.status_code
        except Exception as exc:
            warning = f"Unexpected live-score error: {type(exc).__name__}"
            failure_kind = "unexpected"
    else:
        warning = "FOOTBALL_DATA_TOKEN is not available to this Streamlit app."
        failure_kind = "missing_token"

    snapshot = read_snapshot(snapshot_path)
    latest_update = None
    if not snapshot.empty and "last_updated" in snapshot.columns:
        latest = snapshot["last_updated"].max()
        if pd.notna(latest):
            latest_update = latest.isoformat()
    expected = expected_live_matches(snapshot)
    return snapshot, {
        "source": "Saved GitHub snapshot",
        "fetched_at_utc": latest_update,
        "provider_last_updated_utc": latest_update,
        "http_status": status_code,
        "requests_remaining": None,
        "counter_reset": None,
        "token_configured": bool(token),
        "is_fallback": True,
        "failure_kind": failure_kind,
        "warning": warning,
        "status_counts": _status_counts(snapshot),
        "expected_live_count": int(len(expected)),
        "active_match_count": int(
            snapshot["status"].isin(LIVE_STATUSES).sum()
            if not snapshot.empty and "status" in snapshot.columns
            else 0
        ),
        "feed_state": "fallback_stale" if not expected.empty else "fallback",
    }


def group_freshness(matches: pd.DataFrame, model_metadata: dict) -> dict:
    live_finished = 0
    active_group_matches = 0
    if not matches.empty and {"stage", "status"}.issubset(matches.columns):
        group_mask = matches["stage"] == "GROUP_STAGE"
        live_finished = int(
            (group_mask & matches["status"].isin(FINISHED_STATUSES)).sum()
        )
        active_group_matches = int(
            (group_mask & matches["status"].isin(LIVE_STATUSES)).sum()
        )
    model_finished = int(model_metadata.get("finished_group_matches", 0) or 0)
    return {
        "live_finished_group_matches": live_finished,
        "model_finished_group_matches": model_finished,
        "pending_model_updates": max(0, live_finished - model_finished),
        "active_group_matches": active_group_matches,
    }


def format_source_time(value) -> str:
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(timestamp):
        return "time unavailable"
    return timestamp.strftime("%d %b %Y · %H:%M:%S UTC")
