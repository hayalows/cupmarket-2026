from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from features.official_data import load_latest_csv, load_latest_json

DATE_COLUMNS = (
    "utc_date",
    "generated_at_utc",
    "processed_at_utc",
    "last_updated",
    "prediction_created_at",
)
MIXED_SNAPSHOT_REASON = (
    "The official publication files did not resolve to one GitHub snapshot. "
    "CupMarket kept the complete deployed bundle instead of mixing generations."
)


def _normalise_dates(frame: pd.DataFrame) -> pd.DataFrame:
    for column in DATE_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_datetime(
                frame[column], errors="coerce", utc=True, format="mixed"
            )
    return frame


def _local_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        frame = pd.DataFrame()
    else:
        try:
            frame = _normalise_dates(pd.read_csv(path))
        except (OSError, pd.errors.ParserError, ValueError):
            frame = pd.DataFrame()
    frame.attrs["cupmarket_source"] = "Deployed fallback"
    frame.attrs["cupmarket_commit"] = None
    frame.attrs["cupmarket_relative_path"] = None
    frame.attrs["cupmarket_fallback_reason"] = MIXED_SNAPSHOT_REASON
    return frame


def _local_json(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if path.exists():
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(candidate, dict):
                payload = dict(candidate)
        except (OSError, json.JSONDecodeError):
            payload = {}
    payload["_cupmarket_source"] = "Deployed fallback"
    payload["_cupmarket_commit"] = None
    payload["_cupmarket_fallback_reason"] = MIXED_SNAPSHOT_REASON
    return payload


def _signature(value: Any) -> tuple[str | None, str | None]:
    if isinstance(value, pd.DataFrame):
        return (
            value.attrs.get("cupmarket_source"),
            value.attrs.get("cupmarket_commit"),
        )
    if isinstance(value, dict):
        return (
            value.get("_cupmarket_source"),
            value.get("_cupmarket_commit"),
        )
    return (None, None)


def load_consistent_official_bundle(
    *,
    csv_paths: dict[str, Path],
    json_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Load one all-remote or all-local publication bundle.

    A page must never combine current GitHub prices with an older deployed table
    or ledger. If any file resolves from a different source or commit, the whole
    bundle falls back together.
    """
    json_paths = json_paths or {}
    loaded: dict[str, Any] = {
        key: load_latest_csv(path) for key, path in csv_paths.items()
    }
    loaded.update(
        {key: load_latest_json(path) for key, path in json_paths.items()}
    )
    if not loaded:
        return loaded

    signatures = [_signature(value) for value in loaded.values()]
    if (None, None) not in signatures and len(set(signatures)) == 1:
        return loaded

    fallback: dict[str, Any] = {
        key: _local_csv(path) for key, path in csv_paths.items()
    }
    fallback.update({key: _local_json(path) for key, path in json_paths.items()})
    return fallback
