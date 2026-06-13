from __future__ import annotations

from typing import Any

from features.live_group_data import LIVE, current_tables, group_records
from features.thirds import rank_thirds


def team_context(
    matches,
    predictions,
    team: str,
    strength: dict[str, float] | None = None,
) -> dict[str, Any]:
    strength = strength or {}
    records, groups = group_records(matches, predictions)
    tables = current_tables(records, groups, strength)
    selected = next(
        item for item in records
        if team in {item["home_team"], item["away_team"]}
    )
    group = selected["group"]
    table = tables[group]
    row = next(item for item in table if item["team"] == team)
    thirds = rank_thirds(tables, strength)
    qualifying_thirds = {item["team"] for item in thirds[:8]}
    position = int(row["position"])

    if position <= 2:
        status = "Qualifies directly if matches ended now"
    elif position == 3 and team in qualifying_thirds:
        status = "Qualifies as a best third-place team if matches ended now"
    else:
        status = "Outside the qualification places if matches ended now"

    return {
        "team": team,
        "group": group,
        "table": table,
        "position": position,
        "points": int(row["points"]),
        "goal_difference": int(row["goal_difference"]),
        "status_if_ended_now": status,
        "live_matches": [
            item for item in records
            if item["group"] == group and item["status"] in LIVE
        ],
        "ranked_thirds": thirds,
    }
