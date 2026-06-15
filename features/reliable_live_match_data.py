from __future__ import annotations

import threading
from pathlib import Path

import pandas as pd
import streamlit as st

from features import live_match_data as base

FINISHED_STATUSES = base.FINISHED_STATUSES
LIVE_STATUSES = base.LIVE_STATUSES
UPCOMING_STATUSES = base.UPCOMING_STATUSES
format_source_time = base.format_source_time
group_freshness = base.group_freshness
clear_live_match_cache = base.clear_live_match_cache

_TERMINAL_COLUMNS = [
    "status",
    "winner",
    "duration",
    "home_score_full_time",
    "away_score_full_time",
    "minute",
    "injury_time",
    "last_updated",
]


@st.cache_resource(show_spinner=False)
def _terminal_store() -> dict:
    """Process-wide memory of terminal match states seen by any page/session."""
    return {"lock": threading.RLock(), "records": {}}


def merge_terminal_states(
    current: pd.DataFrame,
    trusted: pd.DataFrame,
) -> tuple[pd.DataFrame, set[int]]:
    """Preserve confirmed FINISHED/AWARDED results over regressed provider states.

    A terminal football result is monotonic: once a match is officially finished, a
    later IN_PLAY, TIMED or AWAITING_CONFIRMATION response must not move it backwards.
    """
    if current.empty or trusted.empty:
        return current.copy(), set()
    if "match_id" not in current.columns or "match_id" not in trusted.columns:
        return current.copy(), set()
    if "status" not in trusted.columns:
        return current.copy(), set()

    frame = current.copy()
    terminal = trusted[trusted["status"].isin(FINISHED_STATUSES)].copy()
    if terminal.empty:
        return frame, set()

    frame["match_id"] = pd.to_numeric(frame["match_id"], errors="coerce")
    terminal["match_id"] = pd.to_numeric(terminal["match_id"], errors="coerce")
    frame = frame.dropna(subset=["match_id"])
    terminal = terminal.dropna(subset=["match_id"])
    frame["match_id"] = frame["match_id"].astype(int)
    terminal["match_id"] = terminal["match_id"].astype(int)

    restored: set[int] = set()
    terminal_by_id = terminal.drop_duplicates("match_id", keep="last").set_index("match_id")

    for match_id, trusted_row in terminal_by_id.iterrows():
        matches = frame.index[frame["match_id"] == int(match_id)]
        if len(matches) == 0:
            appended = trusted_row.to_dict()
            appended["match_id"] = int(match_id)
            frame = pd.concat([frame, pd.DataFrame([appended])], ignore_index=True, sort=False)
            restored.add(int(match_id))
            continue

        index = matches[0]
        current_status = str(frame.at[index, "status"]) if "status" in frame.columns else ""
        if current_status in FINISHED_STATUSES:
            continue

        for column in _TERMINAL_COLUMNS:
            if column in trusted_row.index:
                if column not in frame.columns:
                    frame[column] = pd.NA
                frame.at[index, column] = trusted_row[column]
        restored.add(int(match_id))

    sort_columns = [column for column in ["utc_date", "match_id"] if column in frame.columns]
    if sort_columns:
        frame = frame.sort_values(sort_columns).reset_index(drop=True)
    return frame, restored


def _memory_frame() -> pd.DataFrame:
    store = _terminal_store()
    with store["lock"]:
        records = list(store["records"].values())
    return pd.DataFrame(records)


def _remember_terminal_states(matches: pd.DataFrame) -> None:
    if matches.empty or not {"match_id", "status"}.issubset(matches.columns):
        return
    terminal = matches[matches["status"].isin(FINISHED_STATUSES)].copy()
    if terminal.empty:
        return

    store = _terminal_store()
    with store["lock"]:
        for row in terminal.to_dict("records"):
            match_id = pd.to_numeric(row.get("match_id"), errors="coerce")
            if pd.notna(match_id):
                store["records"][int(match_id)] = row


def _status_counts(matches: pd.DataFrame) -> dict[str, int]:
    if matches.empty or "status" not in matches.columns:
        return {}
    return {
        str(status): int(count)
        for status, count in matches["status"].fillna("UNKNOWN").value_counts().items()
    }


def load_matches(snapshot_path: Path) -> tuple[pd.DataFrame, dict]:
    """Load live matches with monotonic terminal-state reconciliation."""
    matches, metadata = base.load_matches(snapshot_path)
    snapshot = base.read_snapshot(snapshot_path)

    matches, snapshot_restored = merge_terminal_states(matches, snapshot)
    matches, memory_restored = merge_terminal_states(matches, _memory_frame())
    restored_ids = snapshot_restored | memory_restored
    _remember_terminal_states(matches)

    stale_records = [
        record
        for record in metadata.get("stale_live_matches", [])
        if record.get("match_id") not in restored_ids
    ]
    metadata["stale_live_matches"] = stale_records
    metadata["stale_live_count"] = len(stale_records)
    metadata["terminal_reconciled_count"] = len(restored_ids)
    metadata["terminal_reconciled_match_ids"] = sorted(restored_ids)
    metadata["status_counts"] = _status_counts(matches)
    metadata["active_match_count"] = int(
        matches["status"].isin(LIVE_STATUSES).sum()
        if not matches.empty and "status" in matches.columns
        else 0
    )
    metadata["expected_live_count"] = int(len(base.expected_live_matches(matches)))

    if restored_ids and not stale_records:
        metadata["feed_state"] = "terminal_reconciled"
        metadata["warning"] = None
        metadata["reconciliation_note"] = (
            "CupMarket preserved a previously confirmed finished result after the "
            "provider returned an older match state."
        )
    elif stale_records:
        names = ", ".join(
            f"{item.get('home_team')}–{item.get('away_team')}"
            for item in stale_records
        )
        metadata["feed_state"] = "stale_provider_status"
        metadata["warning"] = (
            "The provider returned an impossible live timeline for "
            f"{names}. CupMarket removed the live label and is awaiting official "
            "final-status confirmation."
        )

    return matches, metadata
