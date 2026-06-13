from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st

API_URL = "https://api.football-data.org/v4/competitions/WC/matches"
FINISHED_STATUSES = {"FINISHED", "AWARDED"}


def nested_get(dictionary: dict, keys: list[str], default=None):
    current: Any = dictionary
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


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
                "home_score_full_time": nested_get(
                    match, ["score", "fullTime", "home"]
                ),
                "away_score_full_time": nested_get(
                    match, ["score", "fullTime", "away"]
                ),
                "last_updated": match.get("lastUpdated"),
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    frame["match_id"] = pd.to_numeric(frame["match_id"], errors="coerce")
    frame = frame.dropna(subset=["match_id"])
    frame["match_id"] = frame["match_id"].astype(int)
    for column in ["utc_date", "last_updated"]:
        frame[column] = pd.to_datetime(frame[column], errors="coerce", utc=True)
    return frame.sort_values(["utc_date", "match_id"]).reset_index(drop=True)


@st.cache_data(ttl=60, show_spinner=False)
def fetch_live_matches(token: str) -> tuple[pd.DataFrame, dict]:
    response = requests.get(
        API_URL,
        headers={"X-Auth-Token": token},
        timeout=30,
    )
    response.raise_for_status()
    metadata = {
        "source": "Live football-data.org API",
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "requests_remaining": (
            response.headers.get("X-RequestsAvailable")
            or response.headers.get("X-Requests-Available-Minute")
        ),
        "warning": None,
    }
    return parse_api_matches(response.json()), metadata


def read_snapshot(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    if "match_id" in frame.columns:
        frame["match_id"] = pd.to_numeric(frame["match_id"], errors="coerce")
        frame = frame.dropna(subset=["match_id"])
        frame["match_id"] = frame["match_id"].astype(int)
    for column in ["utc_date", "last_updated"]:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce", utc=True)
    return frame.sort_values(["utc_date", "match_id"]).reset_index(drop=True)


def load_matches(snapshot_path: Path) -> tuple[pd.DataFrame, dict]:
    token = None
    try:
        token = st.secrets.get("FOOTBALL_DATA_TOKEN")
    except Exception:
        token = None

    if token:
        try:
            matches, metadata = fetch_live_matches(str(token))
            if not matches.empty:
                return matches, metadata
        except Exception as exc:
            warning = f"Live scores could not be loaded: {exc}"
        else:
            warning = "The live API returned no matches."
    else:
        warning = "FOOTBALL_DATA_TOKEN is not available to this Streamlit app."

    snapshot = read_snapshot(snapshot_path)
    latest_update = None
    if not snapshot.empty and "last_updated" in snapshot.columns:
        latest = snapshot["last_updated"].max()
        if pd.notna(latest):
            latest_update = latest.isoformat()
    return snapshot, {
        "source": "Saved GitHub snapshot",
        "fetched_at_utc": latest_update,
        "requests_remaining": None,
        "warning": warning,
    }


def group_freshness(matches: pd.DataFrame, model_metadata: dict) -> dict:
    live_finished = 0
    if not matches.empty and {"stage", "status"}.issubset(matches.columns):
        live_finished = int(
            (
                (matches["stage"] == "GROUP_STAGE")
                & matches["status"].isin(FINISHED_STATUSES)
            ).sum()
        )
    model_finished = int(model_metadata.get("finished_group_matches", 0) or 0)
    return {
        "live_finished_group_matches": live_finished,
        "model_finished_group_matches": model_finished,
        "pending_model_updates": max(0, live_finished - model_finished),
    }


def format_source_time(value) -> str:
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(timestamp):
        return "time unavailable"
    return timestamp.strftime("%d %b %Y · %H:%M:%S UTC")
