from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import numpy as np
import pandas as pd

from backend.group_scenarios import (
    FINISHED_STATUSES,
    UPCOMING_STATUSES,
    _prepare,
    _rank_group,
)

LIVE_STATUSES = {"IN_PLAY", "PAUSED"}
THIRD_PLACE_SLOTS = 8


def resolve_match_minute(row: pd.Series | dict[str, Any]) -> int:
    minute = row.get("minute") if hasattr(row, "get") else None
    status = str(row.get("status", "")) if hasattr(row, "get") else ""
    kickoff = pd.to_datetime(
        row.get("utc_date") if hasattr(row, "get") else None,
        errors="coerce",
        utc=True,
    )

    if minute is not None and not pd.isna(minute):
        return int(np.clip(float(minute), 0, 90))
    if status == "PAUSED":
        return 45
    if status == "IN_PLAY" and pd.notna(kickoff):
        elapsed = max(
            0.0,
            (pd.Timestamp.now(tz="UTC") - kickoff).total_seconds() / 60.0,
        )
        if elapsed <= 50:
            return int(np.clip(elapsed, 1, 45))
        return int(np.clip(elapsed - 15, 46, 90))
    return 0


def _prediction_lookup(predictions: pd.DataFrame) -> dict[int, tuple[float, float]]:
    if predictions.empty or "match_id" not in predictions.columns:
        return {}
    frame = predictions.copy()
    frame["match_id"] = pd.to_numeric(frame["match_id"], errors="coerce")
    frame = frame.dropna(subset=["match_id"])
    frame["match_id"] = frame["match_id"].astype(int)
    if "generated_at_utc" in frame.columns:
        frame["generated_at_utc"] = pd.to_datetime(
            frame["generated_at_utc"], errors="coerce", utc=True
        )
        frame = frame.sort_values("generated_at_utc")
    frame = frame.drop_duplicates("match_id", keep="last")
    return {
        int(row.match_id): (
            float(getattr(row, "expected_home_goals", 1.25) or 1.25),
            float(getattr(row, "expected_away_goals", 1.25) or 1.25),
        )
        for row in frame.itertuples(index=False)
    }


def _enriched_rows(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    base_rows, group_teams = _prepare(matches, predictions)
    minute_lookup = {}
    matchday_lookup = {}
    for row in matches.itertuples(index=False):
        match_id = int(row.match_id)
        minute_lookup[match_id] = resolve_match_minute(pd.Series(row._asdict()))
        matchday_lookup[match_id] = getattr(row, "matchday", None)

    for row in base_rows:
        row["minute"] = minute_lookup.get(row["match_id"], 0)
        row["matchday"] = matchday_lookup.get(row["match_id"])
    return base_rows, group_teams


def _current_results(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    results: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for match in rows:
        use_score = (
            match["status"] in FINISHED_STATUSES | LIVE_STATUSES
            and match["home_score"] is not None
            and match["away_score"] is not None
        )
        if not use_score:
            continue
        results[match["group"]].append(
            {
                "home_team": match["home_team"],
                "away_team": match["away_team"],
                "home_goals": int(match["home_score"]),
                "away_goals": int(match["away_score"]),
            }
        )
    return results


def _rank_all_groups(
    group_teams: dict[str, list[str]],
    results: dict[str, list[dict[str, Any]]],
    strength: dict[str, float],
    third_place_slots: int = THIRD_PLACE_SLOTS,
) -> tuple[dict[str, list[dict[str, Any]]], set[str], set[str], list[dict[str, Any]]]:
    tables = {}
    direct_teams: set[str] = set()
    third_rows = []

    for group, teams in group_teams.items():
        table = _rank_group(teams, results.get(group, []), strength)
        tables[group] = table
        if len(table) >= 2:
            direct_teams.update([table[0]["team"], table[1]["team"]])
        if len(table) >= 3:
            third = dict(table[2])
            third["group"] = group
            third_rows.append(third)

    third_rows = sorted(
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
    best_thirds = {
        row["team"]
        for row in third_rows[: min(third_place_slots, len(third_rows))]
    }
    return tables, direct_teams, best_thirds, third_rows


def build_provisional_snapshot(
    matches: pd.DataFrame,
    strength: dict[str, float] | None = None,
    third_place_slots: int = THIRD_PLACE_SLOTS,
) -> dict[str, Any]:
    strength = strength or {}
    rows, group_teams = _enriched_rows(matches, pd.DataFrame())
    results = _current_results(rows)
    tables, direct, best_thirds, third_rows = _rank_all_groups(
        group_teams,
        results,
        strength,
        third_place_slots,
    )

    team_status = {}
    for group, table in tables.items():
        for row in table:
            position = int(row["position"])
            if row["team"] in direct:
                label = "Currently qualifying in the top two"
            elif row["team"] in best_thirds:
                label = "Currently qualifying as a best third-placed team"
            else:
                label = "Currently outside the qualification places"
            team_status[row["team"]] = {
                **row,
                "group": group,
                "status_if_ended_now": label,
                "qualifies_if_ended_now": row["team"] in direct | best_thirds,
                "direct_if_ended_now": row["team"] in direct,
                "best_third_if_ended_now": row["team"] in best_thirds,
                "position": position,
            }

    live_matches = [
        {
            **match,
            "display_minute": (
                "HT"
                if match["status"] == "PAUSED"
                else f'{match["minute"]}\''
            ),
        }
        for match in rows
        if match["status"] in LIVE_STATUSES
    ]

    return {
        "tables": tables,
        "third_place_ranking": third_rows,
        "team_status": team_status,
        "live_matches": live_matches,
        "has_live_matches": bool(live_matches),
    }


def _sample_remaining_score(
    match: dict[str, Any],
    rng: np.random.Generator,
) -> tuple[int, int]:
    status = match["status"]
    current_home = int(match["home_score"] or 0)
    current_away = int(match["away_score"] or 0)

    if status in FINISHED_STATUSES:
        return current_home, current_away

    if status in LIVE_STATUSES:
        remaining_fraction = max(0.0, 90 - int(match["minute"])) / 90.0
        home_extra = int(rng.poisson(max(0.01, match["home_xg"] * remaining_fraction)))
        away_extra = int(rng.poisson(max(0.01, match["away_xg"] * remaining_fraction)))
        return current_home + home_extra, current_away + away_extra

    return (
        int(rng.poisson(max(0.05, match["home_xg"]))),
        int(rng.poisson(max(0.05, match["away_xg"]))),
    )


def _outcome(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "HOME_WIN"
    if away_goals > home_goals:
        return "AWAY_WIN"
    return "DRAW"


def run_live_qualification_projection(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    strength: dict[str, float] | None = None,
    selected_team: str | None = None,
    n_simulations: int = 2000,
    random_seed: int = 2026,
    third_place_slots: int = THIRD_PLACE_SLOTS,
) -> dict[str, Any]:
    if n_simulations < 100:
        raise ValueError("n_simulations must be at least 100.")

    strength = strength or {}
    rows, group_teams = _enriched_rows(matches, predictions)
    live_rows = [row for row in rows if row["status"] in LIVE_STATUSES]
    if not live_rows:
        return {
            "available": False,
            "reason": "No group-stage match is currently in play.",
        }

    all_teams = sorted({team for teams in group_teams.values() for team in teams})
    qualified = Counter()
    direct_count = Counter()
    best_third_count = Counter()
    position_count: dict[str, Counter[int]] = defaultdict(Counter)
    match_outcomes: dict[int, Counter[str]] = defaultdict(Counter)
    scorelines: dict[int, Counter[tuple[int, int]]] = defaultdict(Counter)
    support_total: dict[int, Counter[str]] = defaultdict(Counter)
    support_success: dict[int, Counter[str]] = defaultdict(Counter)

    selected_group = None
    if selected_team:
        for group, teams in group_teams.items():
            if selected_team in teams:
                selected_group = group
                break

    rng = np.random.default_rng(random_seed)
    for _ in range(n_simulations):
        results: dict[str, list[dict[str, Any]]] = defaultdict(list)
        selected_support_outcomes = {}

        for match in rows:
            home_goals, away_goals = _sample_remaining_score(match, rng)
            results[match["group"]].append(
                {
                    "home_team": match["home_team"],
                    "away_team": match["away_team"],
                    "home_goals": home_goals,
                    "away_goals": away_goals,
                }
            )
            if match["status"] in LIVE_STATUSES:
                result_outcome = _outcome(home_goals, away_goals)
                match_outcomes[match["match_id"]][result_outcome] += 1
                scorelines[match["match_id"]][(home_goals, away_goals)] += 1
            if (
                selected_team
                and selected_group == match["group"]
                and selected_team not in {match["home_team"], match["away_team"]}
                and match["status"] not in FINISHED_STATUSES
            ):
                selected_support_outcomes[match["match_id"]] = _outcome(
                    home_goals, away_goals
                )

        tables, direct, best_thirds, _ = _rank_all_groups(
            group_teams,
            results,
            strength,
            third_place_slots,
        )
        qualifiers = direct | best_thirds

        for team in all_teams:
            qualified[team] += int(team in qualifiers)
            direct_count[team] += int(team in direct)
            best_third_count[team] += int(team in best_thirds)

        for group, table in tables.items():
            for row in table:
                position_count[row["team"]][int(row["position"])] += 1

        if selected_team:
            did_qualify = selected_team in qualifiers
            for match_id, outcome in selected_support_outcomes.items():
                support_total[match_id][outcome] += 1
                support_success[match_id][outcome] += int(did_qualify)

    teams_output = {}
    for team in all_teams:
        position_probs = {
            position: position_count[team][position] / n_simulations
            for position in range(1, 5)
        }
        teams_output[team] = {
            "qualification_probability": qualified[team] / n_simulations,
            "direct_top_two_probability": direct_count[team] / n_simulations,
            "best_third_probability": best_third_count[team] / n_simulations,
            "finish_first_probability": position_probs[1],
            "finish_second_probability": position_probs[2],
            "finish_third_probability": position_probs[3],
            "finish_fourth_probability": position_probs[4],
            "most_likely_position": max(position_probs, key=position_probs.get),
        }

    match_output = {}
    for match in live_rows:
        match_id = match["match_id"]
        likely_scores = scorelines[match_id].most_common(3)
        match_output[match_id] = {
            "home_win_probability": match_outcomes[match_id]["HOME_WIN"] / n_simulations,
            "draw_probability": match_outcomes[match_id]["DRAW"] / n_simulations,
            "away_win_probability": match_outcomes[match_id]["AWAY_WIN"] / n_simulations,
            "likely_scorelines": [
                {
                    "score": f"{home}-{away}",
                    "probability": count / n_simulations,
                }
                for (home, away), count in likely_scores
            ],
            "minute": match["minute"],
            "current_score": f'{int(match["home_score"] or 0)}-{int(match["away_score"] or 0)}',
        }

    helpful_result = None
    if selected_team and selected_group:
        baseline = teams_output[selected_team]["qualification_probability"]
        for match in rows:
            if (
                match["group"] != selected_group
                or selected_team in {match["home_team"], match["away_team"]}
                or match["status"] in FINISHED_STATUSES
            ):
                continue
            match_id = match["match_id"]
            for outcome in ("HOME_WIN", "DRAW", "AWAY_WIN"):
                total = support_total[match_id][outcome]
                if total < max(20, int(0.02 * n_simulations)):
                    continue
                conditional = support_success[match_id][outcome] / total
                if outcome == "HOME_WIN":
                    label = f'{match["home_team"]} beat {match["away_team"]}'
                elif outcome == "AWAY_WIN":
                    label = f'{match["away_team"]} beat {match["home_team"]}'
                else:
                    label = f'{match["home_team"]} and {match["away_team"]} draw'
                candidate = {
                    "label": label,
                    "qualification_probability": conditional,
                    "lift": conditional - baseline,
                }
                if helpful_result is None or candidate["lift"] > helpful_result["lift"]:
                    helpful_result = candidate

    return {
        "available": True,
        "n_simulations": n_simulations,
        "teams": teams_output,
        "matches": match_output,
        "selected_team_helpful_result": helpful_result,
        "method_note": (
            "Current scores are fixed. Remaining goals are simulated from the latest "
            "published expected-goal rates scaled by the minutes left."
        ),
    }


def next_goal_impacts(
    matches: pd.DataFrame,
    team: str,
    strength: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    strength = strength or {}
    baseline = build_provisional_snapshot(matches, strength)
    team_now = baseline["team_status"].get(team)
    if not team_now:
        return []
    group = team_now["group"]
    impacts = []

    active = matches[
        (matches["stage"] == "GROUP_STAGE")
        & (matches["group"].astype(str).str.replace("GROUP_", "") == group)
        & matches["status"].isin(LIVE_STATUSES)
    ]

    for row in active.itertuples(index=False):
        for side in ("home", "away"):
            scenario = matches.copy()
            mask = scenario["match_id"] == int(row.match_id)
            score_column = (
                "home_score_full_time" if side == "home" else "away_score_full_time"
            )
            current_score = pd.to_numeric(
                scenario.loc[mask, score_column], errors="coerce"
            ).fillna(0)
            scenario.loc[mask, score_column] = current_score + 1
            snapshot = build_provisional_snapshot(scenario, strength)
            team_after = snapshot["team_status"].get(team)
            scoring_team = row.home_team if side == "home" else row.away_team
            impacts.append(
                {
                    "event": f"{scoring_team} score next",
                    "position": team_after["position"],
                    "status": team_after["status_if_ended_now"],
                    "position_change": int(team_now["position"] - team_after["position"]),
                }
            )
    return impacts
