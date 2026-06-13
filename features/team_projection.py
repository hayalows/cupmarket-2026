from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from features.live_group_data import group_records
from features.live_math import sample_score, simulate_tables, team_setup
from features.thirds import rank_thirds


def qualification_result(
    tables: dict[str, list[dict]],
    group: str,
    team: str,
    strength: dict[str, float],
) -> tuple[dict, bool, bool]:
    row = next(item for item in tables[group] if item["team"] == team)
    thirds = rank_thirds(tables, strength)
    qualifying_thirds = {item["team"] for item in thirds[:8]}
    direct = int(row["position"]) <= 2
    best_third = int(row["position"]) == 3 and team in qualifying_thirds
    return row, direct, best_third
