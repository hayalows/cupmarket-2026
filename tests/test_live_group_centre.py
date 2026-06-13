from __future__ import annotations

import unittest

import pandas as pd

from features.live_context import team_context
from features.team_projection import project_team


def build_data() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    matches = []
    predictions = []
    match_id = 1
    for group in "ABCDEFGHIJKL":
        teams = [f"{group}{number}" for number in range(1, 5)]
        fixtures = [(0, 1), (2, 3), (0, 2), (1, 3), (0, 3), (1, 2)]
        for index, (home_index, away_index) in enumerate(fixtures):
            status = "TIMED"
            home_score = away_score = None
            if group == "A" and index == 0:
                status, home_score, away_score = "FINISHED", 1, 0
            elif group == "A" and index == 1:
                status, home_score, away_score = "FINISHED", 0, 0
            elif group == "A" and index in {4, 5}:
                status = "IN_PLAY"
                home_score, away_score = ((3, 0) if index == 4 else (0, 0))
            matches.append({
                "match_id": match_id,
                "utc_date": pd.Timestamp("2026-06-20", tz="UTC")
                + pd.Timedelta(days=index),
                "status": status,
                "stage": "GROUP_STAGE",
                "group": f"GROUP_{group}",
                "home_team": teams[home_index],
                "away_team": teams[away_index],
                "home_score_full_time": home_score,
                "away_score_full_time": away_score,
            })
            predictions.append({
                "match_id": match_id,
                "generated_at_utc": pd.Timestamp("2026-06-19", tz="UTC"),
                "expected_home_goals": 1.4,
                "expected_away_goals": 1.0,
            })
            match_id += 1
    strength = {
        f"{group}{number}": 100 - number
        for group in "ABCDEFGHIJKL"
        for number in range(1, 5)
    }
    return pd.DataFrame(matches), pd.DataFrame(predictions), strength
