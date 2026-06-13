from __future__ import annotations

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
