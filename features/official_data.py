from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st

GITHUB_REPOSITORY = "hayalows/cupmarket-2026"
GITHUB_MAIN_COMMIT_URL = (
    f"https://api.github.com/repos/{GITHUB_REPOSITORY}/commits/main"
)
GITHUB_UPDATE_RUNS_URL = (
    f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/workflows/"
    "update-cupmarket.yml/runs?per_page=1"
)
RAW_REPOSITORY_BASE_URL = (
    f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}"
)
REMOTE_CACHE_TTL_SECONDS = 120
REMOTE_DATA_FILES = {
    "cupmarket_prices_latest.csv": "data/cupmarket_prices_latest.csv",
    "tournament_probabilities_latest.csv": (
        "data/tournament_probabilities_latest.csv"
    ),
    "current_group_tables.csv": "data/current_group_tables.csv",
    "world_cup_2026_matches_latest.csv": (
        "data/world_cup_2026_matches_latest.csv"
    ),
    "world_cup_live_predictions_latest.csv": (
        "data/world_cup_live_predictions_latest.csv"
    ),
    "round_32_opponent_probabilities_latest.csv": (
        "data/round_32_opponent_probabilities_latest.csv"
    ),
    "round_32_path_status_latest.csv": (
        "data/round_32_path_status_latest.csv"
    ),
    "official_round_32_bracket_locked.csv": (
        "data/official_round_32_bracket_locked.csv"
    ),
    "knockout_progress_latest.csv": "data/knockout_progress_latest.csv",
    "market_movements_latest.csv": "data/market_movements_latest.csv",
    "market_movements.csv": "data/history/market_movements.csv",
    "adaptive_ratings_latest.csv": "data/adaptive_ratings_latest.csv",
    "adaptive_model_health.json": "data/adaptive_model_health.json",
    "publication_manifest.json": "data/publication_manifest.json",
    "team_snapshots.csv": "data/history/team_snapshots.csv",
    "world_cup_prediction_ledger.csv": (
        "backend/state/world_cup_prediction_ledger.csv"
    ),
    "world_cup_processed_match_ledger.csv": (
        "backend/state/world_cup_processed_match_ledger.csv"
    ),
    "phase3_goal_model_evaluation.json": (
        "data/phase3_goal_model_evaluation.json"
    ),
    "phase4_live_evaluation.json": "data/phase4_live_evaluation.json",
    "phase5_simulation_metadata.json": (
        "data/phase5_simulation_metadata.json"
    ),
    "round_32_opponent_probabilities_metadata.json": (
        "data/round_32_opponent_probabilities_metadata.json"
    ),
    "official_round_32_bracket_lock.json": (
        "data/official_round_32_bracket_lock.json"
    ),
}
DATE_COLUMNS = (
    "utc_date",
    "generated_at_utc",
    "processed_at_utc",
    "last_updated",
    "prediction_created_at",
    "snapshot_id",
    "locked_at_utc",
)


def _normalise_dates(frame: pd.DataFrame) -> pd.DataFrame:
    for column in DATE_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_datetime(
                frame[column], errors="coerce", utc=True, format="mixed"
            )
    return frame


def _tag_frame(
    frame: pd.DataFrame,
    *,
    source: str,
    relative_path: str | None,
    commit_sha: str | None = None,
    fallback_reason: str | None = None,
) -> pd.DataFrame:
    frame.attrs["cupmarket_source"] = source
    frame.attrs["cupmarket_relative_path"] = relative_path
    frame.attrs["cupmarket_commit"] = commit_sha
    frame.attrs["cupmarket_fallback_reason"] = fallback_reason
    return frame


@st.cache_data(ttl=REMOTE_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_main_commit_sha() -> str:
    """Resolve main once so every official file comes from one repository state."""
    response = requests.get(
        GITHUB_MAIN_COMMIT_URL,
        headers={"User-Agent": "CupMarket-Streamlit"},
        timeout=12,
    )
    response.raise_for_status()
    payload = response.json()
    commit_sha = str(payload.get("sha", "")).strip()
    if len(commit_sha) < 7:
        raise ValueError("GitHub did not return a valid main-branch commit SHA.")
    return commit_sha


@st.cache_data(ttl=REMOTE_CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_remote_text(relative_path: str, commit_sha: str) -> str:
    """Fetch an allow-listed official output from one immutable commit."""
    response = requests.get(
        f"{RAW_REPOSITORY_BASE_URL}/{commit_sha}/{relative_path}",
        headers={"User-Agent": "CupMarket-Streamlit"},
        timeout=12,
    )
    response.raise_for_status()
    return response.text


@st.cache_data(ttl=300, show_spinner=False)
def fetch_update_workflow_health() -> dict[str, str | None]:
    """Read the latest public update workflow state without touching app data."""
    try:
        response = requests.get(
            GITHUB_UPDATE_RUNS_URL,
            headers={"User-Agent": "CupMarket-Streamlit"},
            timeout=12,
        )
        response.raise_for_status()
        runs = response.json().get("workflow_runs", [])
        if not runs:
            return {"state": "unavailable", "conclusion": None, "updated_at": None, "url": None}
        run = runs[0]
        return {
            "state": str(run.get("status") or "unknown"),
            "conclusion": str(run.get("conclusion") or ""),
            "updated_at": str(run.get("updated_at") or ""),
            "url": str(run.get("html_url") or ""),
        }
    except (requests.RequestException, ValueError, TypeError):
        return {"state": "unavailable", "conclusion": None, "updated_at": None, "url": None}


def _remote_path(path: Path) -> str | None:
    return REMOTE_DATA_FILES.get(path.name)


def official_frame_status(frame: pd.DataFrame) -> dict[str, str | None]:
    """Return user-safe provenance details attached by the official loader."""
    return {
        "source": frame.attrs.get("cupmarket_source"),
        "commit": frame.attrs.get("cupmarket_commit"),
        "relative_path": frame.attrs.get("cupmarket_relative_path"),
        "fallback_reason": frame.attrs.get("cupmarket_fallback_reason"),
    }


def load_latest_csv(path: Path) -> pd.DataFrame:
    """Read one official CSV from a fixed GitHub commit, with local fallback."""
    relative_path = _remote_path(path)
    fallback_reason = None
    if relative_path:
        try:
            commit_sha = _fetch_main_commit_sha()
            remote_frame = pd.read_csv(
                StringIO(_fetch_remote_text(relative_path, commit_sha))
            )
            if not remote_frame.empty:
                return _tag_frame(
                    _normalise_dates(remote_frame),
                    source="GitHub main",
                    relative_path=relative_path,
                    commit_sha=commit_sha,
                )
            fallback_reason = "The remote file was empty."
        except (
            requests.RequestException,
            pd.errors.ParserError,
            json.JSONDecodeError,
            ValueError,
        ) as error:
            fallback_reason = f"{type(error).__name__}: {error}"

    if not path.exists():
        return _tag_frame(
            pd.DataFrame(),
            source="Unavailable",
            relative_path=relative_path,
            fallback_reason=fallback_reason,
        )

    try:
        local_frame = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, ValueError) as error:
        return _tag_frame(
            pd.DataFrame(),
            source="Unavailable",
            relative_path=relative_path,
            fallback_reason=f"{type(error).__name__}: {error}",
        )

    return _tag_frame(
        _normalise_dates(local_frame),
        source="Deployed fallback",
        relative_path=relative_path,
        fallback_reason=fallback_reason,
    )


def load_latest_json(path: Path) -> dict[str, Any]:
    """Read one official JSON file from the same immutable GitHub commit."""
    relative_path = _remote_path(path)
    if relative_path:
        try:
            commit_sha = _fetch_main_commit_sha()
            payload = json.loads(_fetch_remote_text(relative_path, commit_sha))
            if isinstance(payload, dict):
                payload = dict(payload)
                payload["_cupmarket_source"] = "GitHub main"
                payload["_cupmarket_commit"] = commit_sha
                return payload
        except (requests.RequestException, json.JSONDecodeError, ValueError):
            pass

    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    payload = dict(payload)
    payload["_cupmarket_source"] = "Deployed fallback"
    payload["_cupmarket_commit"] = None
    return payload


def clear_official_data_cache() -> None:
    """Clear only the official publication cache."""
    _fetch_main_commit_sha.clear()
    _fetch_remote_text.clear()
