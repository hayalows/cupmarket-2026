from __future__ import annotations

from collections import Counter

import numpy as np

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


def project_team(
    matches,
    predictions,
    team: str,
    strength: dict[str, float] | None = None,
    simulations: int = 2500,
    seed: int = 2026,
) -> dict:
    strength = strength or {}
    records, groups = group_records(matches, predictions)
    group, live_match = team_setup(records, team)
    rng = np.random.default_rng(seed)
    qualified = direct_count = third_count = 0
    positions: Counter[int] = Counter()
    points = []
    scorelines: Counter[str] = Counter()

    for _ in range(simulations):
        tables = simulate_tables(records, groups, strength, rng)
        row, direct, best_third = qualification_result(
            tables, group, team, strength
        )
        qualified += int(direct or best_third)
        direct_count += int(direct)
        third_count += int(best_third)
        positions[int(row["position"])] += 1
        points.append(int(row["points"]))
        if live_match:
            home, away = sample_score(live_match, rng)
            scorelines[f"{home}-{away}"] += 1

    likely_score = scorelines.most_common(1)
    return {
        "team": team,
        "group": group,
        "simulations": simulations,
        "qualification_probability": qualified / simulations,
        "direct_probability": direct_count / simulations,
        "best_third_probability": third_count / simulations,
        "position_probabilities": {
            position: positions[position] / simulations
            for position in range(1, 5)
        },
        "expected_final_points": float(np.mean(points)),
        "most_likely_final_score": likely_score[0][0] if likely_score else None,
        "live_match": live_match,
        "method": (
            "Current scores are the starting point. Remaining goals use "
            "time-adjusted pre-match expected-goal rates."
        ),
    }
