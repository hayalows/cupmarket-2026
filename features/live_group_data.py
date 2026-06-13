from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

FINISHED = {"FINISHED", "AWARDED"}
LIVE = {"IN_PLAY", "PAUSED"}
UPCOMING = {"TIMED", "SCHEDULED"}
DEFAULT_XG = 1.25


def prediction_lookup(predictions: pd.DataFrame) -> dict[int, tuple[float, float]]:
    if predictions.empty or "match_id" not in predictions.columns:
        return {}
    frame = predictions.copy()
    frame["match_id"] = pd.to_numeric(frame["match_id"], errors="coerce")
    frame = frame.dropna(subset=["match_id"])
    if "generated_at_utc" in frame.columns:
        frame["generated_at_utc"] = pd.to_datetime(
            frame["generated_at_utc"], errors="coerce", utc=True
        )
        frame = frame.sort_values("generated_at_utc")
    frame = frame.drop_duplicates("match_id", keep="last")
    return {
        int(row.match_id): (
            float(getattr(row, "expected_home_goals", DEFAULT_XG)),
            float(getattr(row, "expected_away_goals", DEFAULT_XG)),
        )
        for row in frame.itertuples(index=False)
    }


def row_record(row: Any, lookup: dict[int, tuple[float, float]]) -> dict[str, Any]:
    match_id = int(row.match_id)
    home_score = getattr(row, "home_score_full_time", None)
    away_score = getattr(row, "away_score_full_time", None)
    home_xg, away_xg = lookup.get(match_id, (DEFAULT_XG, DEFAULT_XG))
    return {
        "match_id": match_id,
        "group": str(row.group).replace("GROUP_", ""),
        "status": str(row.status),
        "minute": getattr(row, "minute", None),
        "utc_date": pd.to_datetime(
            getattr(row, "utc_date", None), errors="coerce", utc=True
        ),
        "home_team": str(row.home_team),
        "away_team": str(row.away_team),
        "home_score": int(home_score) if pd.notna(home_score) else 0,
        "away_score": int(away_score) if pd.notna(away_score) else 0,
        "home_xg": home_xg if pd.notna(home_xg) else DEFAULT_XG,
        "away_xg": away_xg if pd.notna(away_xg) else DEFAULT_XG,
    }
