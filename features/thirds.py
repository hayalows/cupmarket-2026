from __future__ import annotations

from typing import Any


def rank_thirds(
    tables: dict[str, list[dict[str, Any]]],
    strength: dict[str, float],
) -> list[dict[str, Any]]:
    rows = []
    for group, table in tables.items():
        if len(table) >= 3:
            item = dict(table[2])
            item["group"] = group
            rows.append(item)
    return sorted(
        rows,
        key=lambda item: (
            item["points"],
            item["goal_difference"],
            item["goals_for"],
            strength.get(item["team"], 0.0),
            item["team"],
        ),
        reverse=True,
    )
