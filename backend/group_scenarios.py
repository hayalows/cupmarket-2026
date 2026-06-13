from __future__ import annotations

from collections import Counter, defaultdict
import math
from typing import Any

import numpy as np
import pandas as pd

FINISHED_STATUSES = {"FINISHED", "AWARDED"}
UPCOMING_STATUSES = {"TIMED", "SCHEDULED"}
SCENARIOS = ("WIN", "DRAW", "LOSS")
DEFAULT_XG = 1.25
MAX_GOALS = 8


def _poisson(values: np.ndarray, rate: float) -> np.ndarray:
    factorials = np.array([math.factorial(int(value)) for value in values], dtype=float)
    return np.exp(-rate) * np.power(rate, values) / factorials


def _score_matrix(home_xg: float, away_xg: float) -> np.ndarray:
    home_xg = float(np.clip(home_xg, 0.05, 5.5))
    away_xg = float(np.clip(away_xg, 0.05, 5.5))
    goals = np.arange(MAX_GOALS + 1)
    matrix = np.outer(_poisson(goals, home_xg), _poisson(goals, away_xg))
    return matrix / matrix.sum()


def _sample_score(
    home_xg: float,
    away_xg: float,
    rng: np.random.Generator,
    forced_outcome: str | None = None,
    selected_team_is_home: bool = True,
) -> tuple[int, int]:
    matrix = _score_matrix(home_xg, away_xg)
    scores: list[tuple[int, int]] = []
    weights: list[float] = []

    for home_goals in range(MAX_GOALS + 1):
        for away_goals in range(MAX_GOALS + 1):
            selected_goals = home_goals if selected_team_is_home else away_goals
            opponent_goals = away_goals if selected_team_is_home else home_goals
            if forced_outcome == "WIN" and selected_goals <= opponent_goals:
                continue
            if forced_outcome == "DRAW" and selected_goals != opponent_goals:
                continue
            if forced_outcome == "LOSS" and selected_goals >= opponent_goals:
                continue
            scores.append((home_goals, away_goals))
            weights.append(float(matrix[home_goals, away_goals]))

    probabilities = np.asarray(weights, dtype=float)
    probabilities /= probabilities.sum()
    return scores[int(rng.choice(len(scores), p=probabilities))]


def _blank(team: str) -> dict[str, Any]:
    return {
        "team": team,
        "played": 0,
        "wins": 0,
        "draws": 0,
        "losses": 0,
        "goals_for": 0,
        "goals_against": 0,
        "goal_difference": 0,
        "points": 0,
    }


def _stats(teams: list[str], results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    table = {team: _blank(team) for team in teams}
    for result in results:
        home = result["home_team"]
        away = result["away_team"]
        if home not in table or away not in table:
            continue
        home_goals = int(result["home_goals"])
        away_goals = int(result["away_goals"])
        table[home]["played"] += 1
        table[away]["played"] += 1
        table[home]["goals_for"] += home_goals
        table[home]["goals_against"] += away_goals
        table[away]["goals_for"] += away_goals
        table[away]["goals_against"] += home_goals

        if home_goals > away_goals:
            table[home]["wins"] += 1
            table[away]["losses"] += 1
            table[home]["points"] += 3
        elif away_goals > home_goals:
            table[away]["wins"] += 1
            table[home]["losses"] += 1
            table[away]["points"] += 3
        else:
            table[home]["draws"] += 1
            table[away]["draws"] += 1
            table[home]["points"] += 1
            table[away]["points"] += 1

    for team in teams:
        table[team]["goal_difference"] = (
            table[team]["goals_for"] - table[team]["goals_against"]
        )
    return table


def _rank_group(
    teams: list[str],
    results: list[dict[str, Any]],
    strength: dict[str, float],
) -> list[dict[str, Any]]:
    overall = _stats(teams, results)
    points_groups: dict[int, list[str]] = defaultdict(list)
    for team in teams:
        points_groups[int(overall[team]["points"])].append(team)

    ranked: list[str] = []
    for points in sorted(points_groups, reverse=True):
        tied = points_groups[points]
        if len(tied) == 1:
            ranked.extend(tied)
            continue
        tied_set = set(tied)
        head_to_head = _stats(
            tied,
            [
                row
                for row in results
                if row["home_team"] in tied_set and row["away_team"] in tied_set
            ],
        )
        ranked.extend(
            sorted(
                tied,
                key=lambda team: (
                    head_to_head[team]["points"],
                    head_to_head[team]["goal_difference"],
                    head_to_head[team]["goals_for"],
                    overall[team]["goal_difference"],
                    overall[team]["goals_for"],
                    strength.get(team, 0.0),
                    team,
                ),
                reverse=True,
            )
        )

    output = []
    for position, team in enumerate(ranked, start=1):
        row = overall[team].copy()
        row["position"] = position
        output.append(row)
    return output


def _prediction_lookup(predictions: pd.DataFrame) -> dict[int, tuple[float, float]]:
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
    lookup = {}
    for row in frame.itertuples(index=False):
        home_xg = getattr(row, "expected_home_goals", DEFAULT_XG)
        away_xg = getattr(row, "expected_away_goals", DEFAULT_XG)
        lookup[int(row.match_id)] = (
            float(home_xg) if pd.notna(home_xg) else DEFAULT_XG,
            float(away_xg) if pd.notna(away_xg) else DEFAULT_XG,
        )
    return lookup


def _prepare(matches: pd.DataFrame, predictions: pd.DataFrame) -> tuple[list[dict], dict]:
    required = {"match_id", "stage", "group", "home_team", "away_team", "status"}
    missing = required - set(matches.columns)
    if missing:
        raise ValueError(f"Missing match columns: {sorted(missing)}")

    frame = matches[
        (matches["stage"] == "GROUP_STAGE")
        & matches["group"].notna()
        & matches["home_team"].notna()
        & matches["away_team"].notna()
    ].copy()
    if frame.empty:
        raise ValueError("No group-stage matches are available.")

    prediction_lookup = _prediction_lookup(predictions)
    group_teams: dict[str, set[str]] = defaultdict(set)
    rows: list[dict] = []
    for row in frame.itertuples(index=False):
        match_id = int(row.match_id)
        group = str(row.group).replace("GROUP_", "")
        home_team = str(row.home_team)
        away_team = str(row.away_team)
        group_teams[group].update([home_team, away_team])
        home_xg, away_xg = prediction_lookup.get(
            match_id, (DEFAULT_XG, DEFAULT_XG)
        )
        home_score = getattr(row, "home_score_full_time", None)
        away_score = getattr(row, "away_score_full_time", None)
        rows.append(
            {
                "match_id": match_id,
                "group": group,
                "home_team": home_team,
                "away_team": away_team,
                "status": str(row.status),
                "utc_date": pd.to_datetime(
                    getattr(row, "utc_date", None), errors="coerce", utc=True
                ),
                "home_score": int(home_score) if pd.notna(home_score) else None,
                "away_score": int(away_score) if pd.notna(away_score) else None,
                "home_xg": home_xg,
                "away_xg": away_xg,
            }
        )
    rows.sort(key=lambda item: (item["utc_date"], item["match_id"]))
    return rows, {group: sorted(teams) for group, teams in group_teams.items()}


def _outcome(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "HOME_WIN"
    if away_goals > home_goals:
        return "AWAY_WIN"
    return "DRAW"


def _support_label(match: dict, outcome: str) -> str:
    if outcome == "HOME_WIN":
        return f'{match["home_team"]} beat {match["away_team"]}'
    if outcome == "AWAY_WIN":
        return f'{match["away_team"]} beat {match["home_team"]}'
    return f'{match["home_team"]} and {match["away_team"]} draw'


def _message(probability: float, outcome: str) -> str:
    if probability >= 0.90:
        meaning = "puts qualification in a very strong position"
    elif probability >= 0.70:
        meaning = "makes qualification likely"
    elif probability >= 0.40:
        meaning = "keeps the qualification race open"
    elif probability >= 0.15:
        meaning = "leaves the team needing help from other results"
    else:
        meaning = "would make qualification highly unlikely"
    return f"A {outcome.lower()} {meaning}."


def current_team_summary(
    matches: pd.DataFrame,
    team: str,
    strength: dict[str, float] | None = None,
) -> dict[str, Any]:
    strength = strength or {}
    rows, groups_to_teams = _prepare(matches, pd.DataFrame())
    team_matches = [
        match for match in rows if team in {match["home_team"], match["away_team"]}
    ]
    if not team_matches:
        raise ValueError(f"{team} is not in the group-stage match list.")
    group = team_matches[0]["group"]
    finished = [
        {
            "home_team": match["home_team"],
            "away_team": match["away_team"],
            "home_goals": match["home_score"],
            "away_goals": match["away_score"],
        }
        for match in rows
        if match["group"] == group
        and match["status"] in FINISHED_STATUSES
        and match["home_score"] is not None
        and match["away_score"] is not None
    ]
    table = _rank_group(groups_to_teams[group], finished, strength)
    current = next(row for row in table if row["team"] == team)
    upcoming = [
        match for match in team_matches if match["status"] in UPCOMING_STATUSES
    ]
    upcoming.sort(key=lambda item: (item["utc_date"], item["match_id"]))
    next_match = upcoming[0] if upcoming else None
    return {
        "team": team,
        "group": group,
        "current_position": int(current["position"]),
        "current_points": int(current["points"]),
        "played": int(current["played"]),
        "goal_difference": int(current["goal_difference"]),
        "matches_remaining": len(upcoming),
        "next_match_id": next_match["match_id"] if next_match else None,
        "next_opponent": (
            next_match["away_team"]
            if next_match and next_match["home_team"] == team
            else next_match["home_team"] if next_match else None
        ),
        "next_kickoff_utc": (
            next_match["utc_date"].isoformat() if next_match else None
        ),
    }


def run_qualification_scenarios(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    team: str,
    strength: dict[str, float] | None = None,
    n_simulations: int = 2000,
    random_seed: int = 2026,
    third_place_slots: int = 8,
) -> dict[str, Any]:
    if n_simulations < 100:
        raise ValueError("n_simulations must be at least 100.")
    strength = strength or {}
    rows, groups_to_teams = _prepare(matches, predictions)
    team_matches = [
        match for match in rows if team in {match["home_team"], match["away_team"]}
    ]
    if not team_matches:
        raise ValueError(f"{team} is not in the group-stage match list.")

    group = team_matches[0]["group"]
    upcoming_team = [
        match for match in team_matches if match["status"] in UPCOMING_STATUSES
    ]
    upcoming_team.sort(key=lambda item: (item["utc_date"], item["match_id"]))
    if not upcoming_team:
        return {
            "team": team,
            "group": group,
            "available": False,
            "reason": "No unplayed group-stage match remains for this team.",
            "scenarios": {},
        }

    selected_match = upcoming_team[0]
    selected_is_home = selected_match["home_team"] == team
    current = current_team_summary(matches, team, strength)

    finished_by_group = {name: [] for name in groups_to_teams}
    upcoming_matches = []
    for match in rows:
        if (
            match["status"] in FINISHED_STATUSES
            and match["home_score"] is not None
            and match["away_score"] is not None
        ):
            finished_by_group[match["group"]].append(
                {
                    "home_team": match["home_team"],
                    "away_team": match["away_team"],
                    "home_goals": match["home_score"],
                    "away_goals": match["away_score"],
                }
            )
        elif match["status"] in UPCOMING_STATUSES:
            upcoming_matches.append(match)

    supporting_matches = [
        match
        for match in upcoming_matches
        if match["group"] == group
        and match["match_id"] != selected_match["match_id"]
        and team not in {match["home_team"], match["away_team"]}
    ]

    scenario_results = {}
    scenario_points = {"WIN": 3, "DRAW": 1, "LOSS": 0}

    for scenario_index, scenario in enumerate(SCENARIOS):
        rng = np.random.default_rng(random_seed + scenario_index * 1009)
        qualified = direct = best_third = 0
        positions: Counter[int] = Counter()
        final_points: list[int] = []
        support_total: dict[int, Counter[str]] = defaultdict(Counter)
        support_success: dict[int, Counter[str]] = defaultdict(Counter)

        for _ in range(n_simulations):
            results = {
                name: [dict(item) for item in group_results]
                for name, group_results in finished_by_group.items()
            }
            support_outcomes = {}

            for match in upcoming_matches:
                forced = (
                    scenario
                    if match["match_id"] == selected_match["match_id"]
                    else None
                )
                home_goals, away_goals = _sample_score(
                    match["home_xg"],
                    match["away_xg"],
                    rng,
                    forced_outcome=forced,
                    selected_team_is_home=selected_is_home,
                )
                results[match["group"]].append(
                    {
                        "home_team": match["home_team"],
                        "away_team": match["away_team"],
                        "home_goals": home_goals,
                        "away_goals": away_goals,
                    }
                )
                if match in supporting_matches:
                    support_outcomes[match["match_id"]] = _outcome(
                        home_goals, away_goals
                    )

            tables = {}
            direct_teams = set()
            third_rows = []
            for group_name, teams in groups_to_teams.items():
                table = _rank_group(teams, results[group_name], strength)
                tables[group_name] = table
                direct_teams.update([table[0]["team"], table[1]["team"]])
                third_row = dict(table[2])
                third_row["group"] = group_name
                third_rows.append(third_row)

            ranked_thirds = sorted(
                third_rows,
                key=lambda row: (
                    row["points"],
                    row["goal_difference"],
                    row["goals_for"],
                    strength.get(row["team"], 0.0),
                    row["team"],
                ),
                reverse=True,
            )
            third_teams = {
                row["team"]
                for row in ranked_thirds[: min(third_place_slots, len(ranked_thirds))]
            }

            team_row = next(row for row in tables[group] if row["team"] == team)
            position = int(team_row["position"])
            positions[position] += 1
            final_points.append(int(team_row["points"]))
            is_direct = team in direct_teams
            is_best_third = position == 3 and team in third_teams
            did_qualify = is_direct or is_best_third
            direct += int(is_direct)
            best_third += int(is_best_third)
            qualified += int(did_qualify)

            for match_id, result_outcome in support_outcomes.items():
                support_total[match_id][result_outcome] += 1
                if did_qualify:
                    support_success[match_id][result_outcome] += 1

        qualification_probability = qualified / n_simulations
        position_probabilities = {
            position: positions[position] / n_simulations
            for position in range(1, 5)
        }
        most_likely_position = max(
            position_probabilities, key=position_probabilities.get
        )

        best_supporting_result = None
        for match in supporting_matches:
            for result_outcome in ("HOME_WIN", "DRAW", "AWAY_WIN"):
                total = support_total[match["match_id"]][result_outcome]
                if total < max(20, int(n_simulations * 0.02)):
                    continue
                conditional = (
                    support_success[match["match_id"]][result_outcome] / total
                )
                candidate = {
                    "match_id": match["match_id"],
                    "label": _support_label(match, result_outcome),
                    "qualification_probability": conditional,
                    "lift": conditional - qualification_probability,
                }
                if (
                    best_supporting_result is None
                    or candidate["lift"] > best_supporting_result["lift"]
                ):
                    best_supporting_result = candidate

        scenario_results[scenario] = {
            "points_after_next_match": current["current_points"]
            + scenario_points[scenario],
            "qualification_probability": qualification_probability,
            "direct_top_two_probability": direct / n_simulations,
            "best_third_probability": best_third / n_simulations,
            "finish_first_probability": position_probabilities[1],
            "finish_second_probability": position_probabilities[2],
            "finish_third_probability": position_probabilities[3],
            "finish_fourth_probability": position_probabilities[4],
            "most_likely_group_position": most_likely_position,
            "expected_final_points": float(np.mean(final_points)),
            "supporting_result": best_supporting_result,
            "message": _message(qualification_probability, scenario),
        }

    return {
        "team": team,
        "group": group,
        "available": True,
        "next_match": {
            "match_id": selected_match["match_id"],
            "home_team": selected_match["home_team"],
            "away_team": selected_match["away_team"],
            "opponent": (
                selected_match["away_team"]
                if selected_is_home
                else selected_match["home_team"]
            ),
            "utc_date": selected_match["utc_date"].isoformat(),
            "is_home": selected_is_home,
        },
        "current": current,
        "n_simulations_per_scenario": n_simulations,
        "scenarios": scenario_results,
    }
