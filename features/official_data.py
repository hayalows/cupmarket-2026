from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st

RAW_MAIN_BASE_URL = (
    "https://raw.githubusercontent.com/hayalows/cupmarket-2026/main"
)
REMOTE_DATA_FILES = {
    "cupmarket_prices_latest.csv": "data/cupmarket_prices_latest.csv",
    "tournament_probabilities_latest.csv": "data/tournament_probabilities_latest.csv",
    "current_group_tables.csv": "data/current_group_tables.csv",
    "world_cup_live_predictions_latest.csv": (
        "data/world_cup_live_predictions_latest.csv"
    ),
    "phase3_goal_model_evaluation.json": (
        "data/phase3_goal_model_evaluation.json"
    ),
    "phase4_live_evaluation.json": "data/phase4_live_evaluation.json",
    "phase5_simulation_metadata.json": (
        "data/phase5_simulation_metadata.json"
    ),
}
DATE_COLUMNS = (
    "utc_date",
    "generated_at_utc",
    "processed_at_utc",
    "last_updated",
    "prediction_created_at",
)


def _normalise_dates(frame: pd.DataFrame) -> pd.DataFrame:
    for column in DATE_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_datetime(
                frame[column], errors="coerce", utc=True, format="mixed"
            )
    return frame


@st.cache_data(ttl=90, show_spinner=False)
def _fetch_remote_text(relative_path: str) -> str:
    """Fetch a public, allow-listed official output from the main branch."""
    response = requests.get(
        f"{RAW_MAIN_BASE_URL}/{relative_path}",
        headers={"User-Agent": "CupMarket-Streamlit"},
        timeout=12,
    )
    response.raise_for_status()
    return response.text


def _remote_path(path: Path) -> str | None:
    return REMOTE_DATA_FILES.get(path.name)


def load_latest_csv(path: Path) -> pd.DataFrame:
    """Read the newest official CSV from GitHub, with local deployment fallback."""
    relative_path = _remote_path(path)
    if relative_path:
        try:
            remote_frame = pd.read_csv(StringIO(_fetch_remote_text(relative_path)))
            if not remote_frame.empty:
                return _normalise_dates(remote_frame)
        except (requests.RequestException, pd.errors.ParserError, ValueError):
            # The deployed copy remains a safe fallback during transient GitHub errors.
            pass

    if not path.exists():
        return pd.DataFrame()
    return _normalise_dates(pd.read_csv(path))


def load_latest_json(path: Path) -> dict[str, Any]:
    """Read the newest official JSON from GitHub, with local deployment fallback."""
    relative_path = _remote_path(path)
    if relative_path:
        try:
            payload = json.loads(_fetch_remote_text(relative_path))
            if isinstance(payload, dict):
                return payload
        except (requests.RequestException, json.JSONDecodeError, ValueError):
            pass

    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def clear_official_data_cache() -> None:
    """Clear only the remote official-output cache."""
    _fetch_remote_text.clear()
