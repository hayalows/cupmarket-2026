from __future__ import annotations

from hashlib import sha256

import pandas as pd


def _latest_generation(frame: pd.DataFrame) -> str:
    if frame.empty or "generated_at_utc" not in frame.columns:
        return ""
    timestamps = pd.to_datetime(
        frame["generated_at_utc"], errors="coerce", utc=True
    ).dropna()
    return "" if timestamps.empty else timestamps.max().isoformat()


def qualification_context_token(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    prices: pd.DataFrame,
    selected_match_id: int,
    team: str,
) -> str:
    """Fingerprint only inputs that can change a qualification calculation.

    Provider fetch timestamps are deliberately excluded. A routine auto-refresh
    should not invalidate a result when the football state and model inputs are
    unchanged.
    """
    if matches.empty or "match_id" not in matches.columns:
        selected_rows = pd.DataFrame()
    else:
        selected_rows = matches[
            pd.to_numeric(matches["match_id"], errors="coerce")
            == int(selected_match_id)
        ]

    group = (
        selected_rows.iloc[0].get("group")
        if not selected_rows.empty
        else None
    )
    if "group" in matches.columns:
        group_rows = matches[matches["group"].astype(str) == str(group)].copy()
    else:
        group_rows = pd.DataFrame()

    if "match_id" in group_rows.columns:
        group_rows = group_rows.sort_values("match_id")

    snapshot_columns = [
        "match_id",
        "status",
        "home_team",
        "away_team",
        "home_score_full_time",
        "away_score_full_time",
        "home_score",
        "away_score",
    ]
    available_columns = [
        column for column in snapshot_columns if column in group_rows.columns
    ]
    group_snapshot = tuple(
        tuple(str(value) for value in row)
        for row in group_rows[available_columns].itertuples(index=False, name=None)
    )

    payload = (
        int(selected_match_id),
        str(team),
        str(group),
        group_snapshot,
        _latest_generation(predictions),
        _latest_generation(prices),
    )
    return sha256(repr(payload).encode("utf-8")).hexdigest()[:20]


def stored_result_is_current(
    stored: dict | None,
    team: str,
    context_token: str,
) -> bool:
    return bool(
        stored
        and stored.get("team") == team
        and stored.get("context_token") == context_token
        and "result" in stored
    )
