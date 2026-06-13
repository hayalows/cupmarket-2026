from __future__ import annotations

from typing import Any

import pandas as pd

from backend.group_scenarios import FINISHED_STATUSES, _prepare, _rank_group


def build_live_group_table(
    matches: pd.DataFrame,
    group: str,
    strength: dict[str, float] | None = None,
) -> pd.DataFrame:
    strength = strength or {}
    rows, groups_to_teams = _prepare(matches, pd.DataFrame())
    normalized_group = str(group).replace("GROUP_", "")
    teams = groups_to_teams.get(normalized_group, [])
    if not teams:
        return pd.DataFrame()

    finished = [
        {
            "home_team": match["home_team"],
            "away_team": match["away_team"],
            "home_goals": match["home_score"],
            "away_goals": match["away_score"],
        }
        for match in rows
        if match["group"] == normalized_group
        and match["status"] in FINISHED_STATUSES
        and match["home_score"] is not None
        and match["away_score"] is not None
    ]
    ranked: list[dict[str, Any]] = _rank_group(teams, finished, strength)
    return pd.DataFrame(ranked)
