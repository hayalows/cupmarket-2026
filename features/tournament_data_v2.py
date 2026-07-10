from __future__ import annotations

from pathlib import Path
import re

import pandas as pd
import streamlit as st

from features.official_bundle import load_consistent_official_bundle
from features.official_data import load_latest_csv
from features.tournament_helpers import (
    actual_outcome,
    batch_context_for_match,
    leading_outcome_label,
    latest_update_matches,
    outcome_probability,
    reference_prediction,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
STATE_DIR = ROOT / "backend" / "state"
HISTORY_DIR = DATA_DIR / "market_history"


def load_csv(path: Path) -> pd.DataFrame:
    return load_latest_csv(path)


@st.cache_data(show_spinner=False)
def _load_local_history(
    directory_text: str,
    manifest: tuple[tuple[str, int], ...],
) -> pd.DataFrame:
    directory = Path(directory_text)
    rows: list[pd.DataFrame] = []
    for filename, _ in manifest:
        path = directory / filename
        try:
            frame = pd.read_csv(path)
        except (OSError, pd.errors.ParserError):
            continue
        timestamp_match = re.search(r"(\d{8}T\d{6}Z)", filename)
        fallback_time = (
            pd.to_datetime(
                timestamp_match.group(1),
                format="%Y%m%dT%H%M%SZ",
                utc=True,
                errors="coerce",
            )
            if timestamp_match
            else pd.NaT
        )
        if "generated_at_utc" not in frame.columns:
            frame["generated_at_utc"] = fallback_time
        frame["generated_at_utc"] = pd.to_datetime(
            frame["generated_at_utc"], errors="coerce", utc=True
        )
        rows.append(frame)

    if not rows:
        return pd.DataFrame()
    history = pd.concat(rows, ignore_index=True, sort=False)
    required = ["team", "cupmarket_price", "generated_at_utc"]
    if not set(required).issubset(history.columns):
        return pd.DataFrame()
    return (
        history.dropna(subset=required)
        .drop_duplicates(["team", "generated_at_utc"], keep="last")
        .sort_values(["generated_at_utc", "team"])
        .reset_index(drop=True)
    )


def _combine_market_history(
    current_frame: pd.DataFrame,
    snapshots: pd.DataFrame,
) -> pd.DataFrame:
    """Use the published team snapshot ledger, not a possibly stale app checkout."""
    history = snapshots.copy()
    current_frame = current_frame.copy()
    if current_frame.empty:
        return history
    if history.empty:
        return current_frame
    combined = pd.concat([history, current_frame], ignore_index=True, sort=False)
    required = ["team", "cupmarket_price", "generated_at_utc"]
    if not set(required).issubset(combined.columns):
        return history
    return (
        combined.dropna(subset=required)
        .drop_duplicates(["team", "generated_at_utc"], keep="last")
        .sort_values(["generated_at_utc", "team"])
        .reset_index(drop=True)
    )


def load_market_history(current: pd.DataFrame | None = None) -> pd.DataFrame:
    if current is None:
        bundle = load_consistent_official_bundle(
            csv_paths={
                "prices": DATA_DIR / "cupmarket_prices_latest.csv",
                "snapshots": DATA_DIR / "history" / "team_snapshots.csv",
            }
        )
        return _combine_market_history(bundle["prices"], bundle["snapshots"])
    snapshots = load_csv(DATA_DIR / "history" / "team_snapshots.csv")
    return _combine_market_history(current, snapshots)


def load_static_data() -> dict[str, pd.DataFrame]:
    bundle = load_consistent_official_bundle(
        csv_paths={
            "prices": DATA_DIR / "cupmarket_prices_latest.csv",
            "snapshots": DATA_DIR / "history" / "team_snapshots.csv",
            "latest_predictions": DATA_DIR / "world_cup_live_predictions_latest.csv",
            "prediction_ledger": STATE_DIR / "world_cup_prediction_ledger.csv",
            "processed_ledger": STATE_DIR / "world_cup_processed_match_ledger.csv",
        }
    )
    bundle["history"] = _combine_market_history(
        bundle["prices"], bundle["snapshots"]
    )
    return bundle


__all__ = [
    "DATA_DIR",
    "HISTORY_DIR",
    "ROOT",
    "STATE_DIR",
    "actual_outcome",
    "batch_context_for_match",
    "leading_outcome_label",
    "latest_update_matches",
    "load_csv",
    "load_market_history",
    "load_static_data",
    "outcome_probability",
    "reference_prediction",
]
