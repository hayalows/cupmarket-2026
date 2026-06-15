from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import threading

import pandas as pd
import requests
import streamlit as st

from features.live_match_reconciliation import (
    ACTIVE_PLAY_STATUSES,
    FINISHED_STATUSES,
    STALE_PROVIDER_STATUS,
    TerminalReconciliationReport,
    mark_impossible_live_states,
    merge_terminal_states,
)

API_URL = "https://api.football-data.org/v4/competitions/WC/matches"
LIVE_STATUSES = {"IN_PLAY", "PAUSED", "SUSPENDED"}
UPCOMING_STATUSES = {"TIMED", "SCHEDULED"}
ACTIVE_REFRESH_SECONDS = 45
IDLE_REFRESH_SECONDS = 300


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


def _normalise_match_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()

    result = frame.copy()
    if "match_id" in result.columns:
        result["match_id"] = pd.to_numeric(result["match_id"], errors="coerce")
        result = result.dropna(subset=["match_id"])
        result["match_id"] = result["match_id"].astype(int)

    for column in (
        "minute",
        "injury_time",
        "matchday",
        "home_score_full_time",
        "away_score_full_time",
    ):
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")

    for column in ("utc_date", "last_updated"):
        if column in result.columns:
            result[column] = pd.to_datetime(
                result[column], errors="coerce", utc=True
            )

    sort_columns = [
        column for column in ("utc_date", "match_id") if column in result.columns
    ]
    return (
        result.sort_values(sort_columns).reset_index(drop=True)
        if sort_columns
        else result.reset_index(drop=True)
    )


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
    return _normalise_match_frame(pd.DataFrame(rows))


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
    return matches[
        matches["status"].isin(UPCOMING_STATUSES)
        & (current >= kickoff - pd.Timedelta(minutes=early_minutes))
        & (current <= kickoff + pd.Timedelta(hours=late_hours))
    ].copy()


def should_auto_refresh(matches: pd.DataFrame) -> bool:
    if matches.empty or "status" not in matches.columns:
        return False
    return bool(
        matches["status"].isin(LIVE_STATUSES).any()
        or not expected_live_matches(matches).empty
    )


def recommended_refresh_seconds(matches: pd.DataFrame) -> int:
    return ACTIVE_REFRESH_SECONDS if should_auto_refresh(matches) else IDLE_REFRESH_SECONDS


@st.cache_resource(show_spinner=False)
def _observed_terminal_store() -> dict:
    """Defensive in-process cache, never the primary source of official truth."""
    return {"lock": threading.RLock(), "records": {}}


def _observed_terminal_frame() -> pd.DataFrame:
    store = _observed_terminal_store()
    with store["lock"]:
        return _normalise_match_frame(pd.DataFrame(store["records"].values()))


def _remember_terminal_states(matches: pd.DataFrame) -> None:
    if matches.empty or not {"match_id", "status"}.issubset(matches.columns):
        return

    terminal = matches[matches["status"].isin(FINISHED_STATUSES)].copy()
    if terminal.empty:
        return

    store = _observed_terminal_store()
    with store["lock"]:
        existing = _normalise_match_frame(pd.DataFrame(store["records"].values()))
        merged, _ = merge_terminal_states(existing, terminal)
        store["records"] = {
            int(row["match_id"]): row
            for row in merged.to_dict("records")
            if pd.notna(row.get("match_id"))
            and str(row.get("status")) in FINISHED_STATUSES
        }


def _combine_reports(
    *reports: TerminalReconciliationReport,
) -> TerminalReconciliationReport:
    return TerminalReconciliationReport(
        restored_match_ids=tuple(
            sorted(
                {
                    match_id
                    for report in reports
                    for match_id in report.restored_match_ids
                }
            )
        ),
        corrected_match_ids=tuple(
            sorted(
                {
                    match_id
                    for report in reports
                    for match_id in report.corrected_match_ids
                }
            )
        ),
        appended_match_ids=tuple(
            sorted(
                {
                    match_id
                    for report in reports
                    for match_id in report.appended_match_ids
                }
            )
        ),
    )


def reconcile_live_matches(
    live_matches: pd.DataFrame,
    snapshot: pd.DataFrame,
) -> tuple[pd.DataFrame, TerminalReconciliationReport, list[dict]]:
    """Build one consistent match state from live, saved, and observed records."""
    reconciled, snapshot_report = merge_terminal_states(live_matches, snapshot)
    reconciled, observed_report = merge_terminal_states(
        reconciled, _observed_terminal_frame()
    )
    report = _combine_reports(snapshot_report, observed_report)
    reconciled, stale_records = mark_impossible_live_states(reconciled)
    _remember_terminal_states(reconciled)
    return reconciled, report, stale_records


@st.cache_data(ttl=ACTIVE_REFRESH_SECONDS, show_spinner=False)
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
        raise LiveFeedRequestError(
            f"Live-score request failed ({response.status_code}): "
            f"{_safe_provider_message(response)}",
            kind=_classify_http_error(response.status_code),
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
    provider_updated = None
    if not matches.empty and "last_updated" in matches.columns:
        latest = matches["last_updated"].max()
        provider_updated = latest.isoformat() if pd.notna(latest) else None

    return matches, {
        "source": "Live football-data.org API",
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider_last_updated_utc": provider_updated,
        "http_status": response.status_code,
        "requests_remaining": (
            response.headers.get("X-RequestsAvailable")
            or response.headers.get("X-Requests-Available-Minute")
        ),
        "counter_reset": response.headers.get("X-RequestCounter-Reset"),
        "token_configured": True,
        "is_fallback": False,
        "failure_kind": None,
    }


def clear_live_match_cache() -> None:
    """Clear only the football feed cache, not every CupMarket cache."""
    fetch_live_matches.clear()


def read_snapshot(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return _normalise_match_frame(pd.read_csv(path))


def _fallback_message(failure_kind: str | None) -> tuple[str, str]:
    if failure_kind == "missing_token":
        return (
            "error",
            "Live scores are not connected right now. CupMarket is showing the last saved update.",
        )
    if failure_kind == "invalid_token":
        return (
            "error",
            "The live-score connection needs attention. CupMarket is showing the last saved update.",
        )
    if failure_kind == "rate_limit":
        return (
            "warning",
            "Live scores are temporarily delayed. CupMarket will retry automatically.",
        )
    return (
        "warning",
        "The live score service is temporarily unavailable. CupMarket is showing the last saved update.",
    )


def _apply_live_metadata(
    matches: pd.DataFrame,
    metadata: dict,
    report: TerminalReconciliationReport,
    stale_records: list[dict],
) -> dict:
    result = dict(metadata)
    expected = expected_live_matches(matches)
    active_count = int(matches["status"].isin(LIVE_STATUSES).sum())

    result.update(
        {
            "status_counts": _status_counts(matches),
            "expected_live_count": int(len(expected)),
            "active_match_count": active_count,
            "terminal_restored_match_ids": list(report.restored_match_ids),
            "terminal_corrected_match_ids": list(report.corrected_match_ids),
            "terminal_appended_match_ids": list(report.appended_match_ids),
            "stale_live_matches": stale_records,
            "stale_live_count": len(stale_records),
            "notice_level": None,
            "public_notice": None,
            "technical_warning": None,
        }
    )

    if report.corrected_match_ids:
        result["feed_state"] = "official_correction_applied"
        result["public_notice"] = (
            "An official result correction was received and CupMarket has updated the match record."
        )
        result["notice_level"] = "info"
    elif report.changed_match_ids:
        result["feed_state"] = "terminal_reconciled"
        result["reconciliation_note"] = (
            "CupMarket kept a previously confirmed final result when the provider returned an older state."
        )
    elif stale_records:
        names = ", ".join(
            f"{item.get('home_team')}–{item.get('away_team')}"
            for item in stale_records
        )
        result["feed_state"] = "stale_provider_status"
        result["notice_level"] = "warning"
        result["public_notice"] = (
            "This match status is being confirmed. CupMarket is keeping the latest verified score."
        )
        result["technical_warning"] = (
            f"Provider returned an impossible active timeline for {names}."
        )
    elif not expected.empty and active_count == 0:
        result["feed_state"] = "provider_delayed"
        result["notice_level"] = "info"
        result["public_notice"] = (
            "The match may have started, but the score feed has not confirmed it yet. CupMarket will keep checking."
        )
    else:
        result["feed_state"] = "live" if active_count else "healthy"

    return result


def load_matches(snapshot_path: Path) -> tuple[pd.DataFrame, dict]:
    """Return one reconciled match table and diagnostics for every live page."""
    snapshot = read_snapshot(snapshot_path)
    _remember_terminal_states(snapshot)

    token = ""
    try:
        token = str(st.secrets.get("FOOTBALL_DATA_TOKEN", "")).strip()
    except Exception:
        token = ""

    failure_kind = None
    technical_error = None
    status_code = None

    if token:
        try:
            live_matches, metadata = fetch_live_matches(token)
            if not live_matches.empty:
                matches, report, stale_records = reconcile_live_matches(
                    live_matches, snapshot
                )
                return matches, _apply_live_metadata(
                    matches, metadata, report, stale_records
                )
            failure_kind = "empty_response"
            technical_error = "The live API returned no World Cup matches."
        except LiveFeedRequestError as exc:
            failure_kind = exc.kind
            technical_error = str(exc)
            status_code = exc.status_code
        except Exception as exc:
            failure_kind = "unexpected"
            technical_error = f"Unexpected live-score error: {type(exc).__name__}"
    else:
        failure_kind = "missing_token"
        technical_error = "FOOTBALL_DATA_TOKEN is not available to this Streamlit app."

    notice_level, public_notice = _fallback_message(failure_kind)
    latest_update = None
    if not snapshot.empty and "last_updated" in snapshot.columns:
        latest = snapshot["last_updated"].max()
        latest_update = latest.isoformat() if pd.notna(latest) else None

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
        "status_counts": _status_counts(snapshot),
        "expected_live_count": int(len(expected_live_matches(snapshot))),
        "active_match_count": int(
            snapshot["status"].isin(LIVE_STATUSES).sum()
            if not snapshot.empty and "status" in snapshot.columns
            else 0
        ),
        "terminal_restored_match_ids": [],
        "terminal_corrected_match_ids": [],
        "terminal_appended_match_ids": [],
        "stale_live_count": 0,
        "stale_live_matches": [],
        "feed_state": "fallback",
        "notice_level": notice_level,
        "public_notice": public_notice,
        "technical_warning": technical_error,
        "warning": public_notice,
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
