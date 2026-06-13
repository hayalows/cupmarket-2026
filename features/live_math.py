from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from features.live_group_data import FINISHED, LIVE, group_records, match_result
from features.thirds import rank_thirds
from backend.group_scenarios import _rank_group


def match_minute(match: dict) -> int:
    value = pd.to_numeric(match.get("minute"), errors="coerce")
    if pd.notna(value):
        return int(np.clip(value, 0, 90))
    kickoff = match.get("utc_date")
    if pd.notna(kickoff):
        elapsed = (pd.Timestamp.now(tz="UTC") - kickoff).total_seconds() / 60
        return int(np.clip(elapsed, 0, 90))
    return 45


def sample_score(match: dict, rng: np.random.Generator) -> tuple[int, int]:
    if match["status"] in FINISHED:
        return match["home_score"], match["away_score"]
    if match["status"] in LIVE:
        fraction = max(0.0, (90 - match_minute(match)) / 90)
        home_rate = max(0.0, match["home_xg"] * fraction)
        away_rate = max(0.0, match["away_xg"] * fraction)
        if match["home_score"] > match["away_score"]:
            home_rate *= 0.90
            away_rate *= 1.15
        elif match["away_score"] > match["home_score"]:
            away_rate *= 0.90
            home_rate *= 1.15
        return (
            match["home_score"] + int(rng.poisson(home_rate)),
            match["away_score"] + int(rng.poisson(away_rate)),
        )
    return (
        int(rng.poisson(max(0.05, match["home_xg"]))),
        int(rng.poisson(max(0.05, match["away_xg"]))),
    )


def simulate_tables(
    records: list[dict],
    groups: dict[str, list[str]],
    strength: dict[str, float],
    rng: np.random.Generator,
) -> dict[str, list[dict]]:
    results = {group: [] for group in groups}
    for match in records:
        home, away = sample_score(match, rng)
        results[match["group"]].append(match_result(match, home, away))
    return {
        group: _rank_group(teams, results[group], strength)
        for group, teams in groups.items()
    }


def team_setup(records: list[dict], team: str) -> tuple[str, dict | None]:
    selected = next(
        item for item in records
        if team in {item["home_team"], item["away_team"]}
    )
    live_match = next(
        (
            item for item in records
            if team in {item["home_team"], item["away_team"]}
            and item["status"] in LIVE
        ),
        None,
    )
    return selected["group"], live_match
