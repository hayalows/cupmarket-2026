"""Projected Round-of-32 opponents from CupMarket group simulations.

This module runs a group-stage-only Monte Carlo pass after the main model has
published. It reuses CupMarket's ranking and official slot-constraint helpers,
then counts the Round-of-32 pairings produced in each simulation.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import json
import os

import numpy as np
import pandas as pd


GROUPS = tuple("ABCDEFGHIJKL")


def opponent_probabilities_enabled() -> bool:
    return os.environ.get("ENABLE_OPPONENT_PROBABILITIES", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _atomic_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


def _group_letter(value: str) -> str:
    value = str(value)
    return value.removeprefix("GROUP_")


def _completed_groups(world_cup: pd.DataFrame) -> set[str]:
    group_matches = world_cup.loc[world_cup["stage"] == "GROUP_STAGE"].copy()
    finished = group_matches.loc[
        (group_matches["status"] == "FINISHED")
        & group_matches["home_score_full_time"].notna()
        & group_matches["away_score_full_time"].notna()
    ].copy()
    counts = finished.assign(
        group_letter=finished["group"].map(_group_letter)
    ).groupby("group_letter")["match_id"].nunique()
    return {group for group, count in counts.items() if int(count) == 6}


def _fixed_slot_index(pipeline) -> dict[str, tuple[int, str]]:
    result: dict[str, tuple[int, str]] = {}
    for match_id, (home_slot, away_slot) in pipeline.FIXED_R32.items():
        result[home_slot] = (int(match_id), away_slot)
        result[away_slot] = (int(match_id), home_slot)
    for match_id, winner_slot in pipeline.THIRD_PLACE_R32_WINNER.items():
        result[winner_slot] = (int(match_id), "BEST_THIRD")
    return result


def classify_team_path(
    team: str,
    group: str,
    current_position: int | None,
    completed_groups: set[str],
    pipeline,
) -> tuple[str, str | None, int | None]:
    """Return a conservative fixture status, slot and match number."""
    if group not in completed_groups or current_position is None:
        return "projected", None, None
    if current_position == 4:
        return "eliminated", None, None
    if current_position == 3:
        return "third_place_ranking_pending", f"3{group}", None

    slot = f"{current_position}{group}"
    index = _fixed_slot_index(pipeline)
    match_data = index.get(slot)
    if match_data is None:
        return "slot_confirmed", slot, None
    match_id, opponent_slot = match_data

    if opponent_slot == "BEST_THIRD":
        return "slot_confirmed_opponent_pending", slot, match_id

    opponent_group = opponent_slot[1:]
    if opponent_group in completed_groups:
        return "confirmed", slot, match_id
    return "slot_confirmed", slot, match_id


def _build_simulation_inputs(
    world_cup: pd.DataFrame,
    live_predictions: pd.DataFrame,
) -> tuple[dict[str, list[dict]], dict[str, list[str]], dict[str, str]]:
    group_matches = (
        world_cup.loc[world_cup["stage"] == "GROUP_STAGE"]
        .sort_values("utc_date")
        .reset_index(drop=True)
    )
    prediction_lookup = (
        live_predictions.drop_duplicates("match_id", keep="last").set_index("match_id")
        if not live_predictions.empty
        else pd.DataFrame()
    )

    matches_by_group = {group: [] for group in GROUPS}
    groups_to_teams = {group: set() for group in GROUPS}
    team_to_group: dict[str, str] = {}

    for match in group_matches.itertuples(index=False):
        group = _group_letter(match.group)
        groups_to_teams[group].update([match.home_team, match.away_team])
        team_to_group[str(match.home_team)] = group
        team_to_group[str(match.away_team)] = group
        is_finished = (
            match.status == "FINISHED"
            and pd.notna(match.home_score_full_time)
            and pd.notna(match.away_score_full_time)
        )
        if is_finished:
            home_xg = away_xg = None
        else:
            if prediction_lookup.empty or int(match.match_id) not in prediction_lookup.index:
                raise ValueError(
                    "No live prediction found for unplayed match "
                    f"{match.match_id}: {match.home_team} vs {match.away_team}."
                )
            prediction = prediction_lookup.loc[int(match.match_id)]
            home_xg = float(prediction["expected_home_goals"])
            away_xg = float(prediction["expected_away_goals"])
        matches_by_group[group].append(
            {
                "home_team": str(match.home_team),
                "away_team": str(match.away_team),
                "is_finished": is_finished,
                "actual_home_score": int(match.home_score_full_time) if is_finished else None,
                "actual_away_score": int(match.away_score_full_time) if is_finished else None,
                "home_xg": home_xg,
                "away_xg": away_xg,
            }
        )

    normalized_groups = {group: sorted(teams) for group, teams in groups_to_teams.items()}
    if any(len(teams) != 4 for teams in normalized_groups.values()):
        raise ValueError("Every World Cup group must contain exactly four teams")
    return matches_by_group, normalized_groups, team_to_group


def simulate_opponent_probabilities(
    world_cup: pd.DataFrame,
    live_predictions: pd.DataFrame,
    live_elo_lookup: dict[str, float],
    pipeline,
    number_of_simulations: int,
    random_seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    matches_by_group, groups_to_teams, team_to_group = _build_simulation_inputs(
        world_cup, live_predictions
    )
    teams = sorted(team_to_group)
    rng = np.random.default_rng(random_seed)
    pairing_counts: dict[str, dict[str, int]] = {
        team: defaultdict(int) for team in teams
    }
    qualification_counts = {team: 0 for team in teams}
    position_counts = {
        team: {1: 0, 2: 0, 3: 0, 4: 0} for team in teams
    }

    for _ in range(number_of_simulations):
        slot_team: dict[str, str] = {}
        third_rows: list[dict] = []

        for group in GROUPS:
            results = []
            for match in matches_by_group[group]:
                if match["is_finished"]:
                    home_goals = match["actual_home_score"]
                    away_goals = match["actual_away_score"]
                else:
                    home_goals = int(rng.poisson(match["home_xg"]))
                    away_goals = int(rng.poisson(match["away_xg"]))
                results.append(
                    {
                        "home_team": match["home_team"],
                        "away_team": match["away_team"],
                        "home_goals": home_goals,
                        "away_goals": away_goals,
                    }
                )

            table, _ = pipeline.rank_group(
                groups_to_teams[group], results, live_elo_lookup
            )
            for index, row in enumerate(table, start=1):
                position_counts[row["team"]][index] += 1
            first = table[0]["team"]
            second = table[1]["team"]
            third = table[2].copy()
            third["group"] = group
            slot_team[f"1{group}"] = first
            slot_team[f"2{group}"] = second
            third_rows.append(third)

        ranked_thirds = pipeline.rank_third_placed(third_rows, live_elo_lookup)
        best_eight = ranked_thirds[:8]
        best_third_by_group = {row["group"]: row["team"] for row in best_eight}
        third_slot_team = pipeline.choose_third_place_assignment(
            best_third_by_group, rng
        )

        pairings: dict[int, tuple[str, str]] = {}
        for match_id, (home_slot, away_slot) in pipeline.FIXED_R32.items():
            pairings[int(match_id)] = (
                slot_team[home_slot],
                slot_team[away_slot],
            )
        for match_id, winner_slot in pipeline.THIRD_PLACE_R32_WINNER.items():
            pairings[int(match_id)] = (
                slot_team[winner_slot],
                third_slot_team[match_id],
            )

        qualified = {team for pairing in pairings.values() for team in pairing}
        for team in qualified:
            qualification_counts[team] += 1
        for home_team, away_team in pairings.values():
            pairing_counts[home_team][away_team] += 1
            pairing_counts[away_team][home_team] += 1

    opponent_rows = []
    for team in teams:
        qualified_count = qualification_counts[team]
        for opponent, count in sorted(
            pairing_counts[team].items(), key=lambda item: (-item[1], item[0])
        ):
            opponent_rows.append(
                {
                    "team": team,
                    "team_group": team_to_group[team],
                    "opponent": opponent,
                    "opponent_group": team_to_group[opponent],
                    "pairing_count": int(count),
                    "probability_unconditional": count / number_of_simulations,
                    "probability_given_qualification": (
                        count / qualified_count if qualified_count else 0.0
                    ),
                    "qualification_count": int(qualified_count),
                    "number_of_simulations": int(number_of_simulations),
                }
            )

    summary_rows = []
    completed_groups = _completed_groups(world_cup)
    current_tables = pd.read_csv(
        pipeline.CURRENT_TABLES_OUTPUT_PATH
    ) if pipeline.CURRENT_TABLES_OUTPUT_PATH.exists() else pd.DataFrame()
    current_position_lookup = (
        dict(zip(current_tables["team"].astype(str), current_tables["position"].astype(int)))
        if not current_tables.empty
        else {}
    )

    for team in teams:
        group = team_to_group[team]
        status, slot, match_id = classify_team_path(
            team,
            group,
            current_position_lookup.get(team),
            completed_groups,
            pipeline,
        )
        qualified_count = qualification_counts[team]
        likely_opponents = pairing_counts[team]
        top_opponent = (
            max(likely_opponents, key=likely_opponents.get)
            if likely_opponents
            else None
        )
        summary_rows.append(
            {
                "team": team,
                "group": group,
                "fixture_status": status,
                "confirmed_slot": slot,
                "round_32_match_id": match_id,
                "current_group_position": current_position_lookup.get(team),
                "group_complete": group in completed_groups,
                "prob_reach_round_32": qualified_count / number_of_simulations,
                "prob_eliminated": 1.0 - qualified_count / number_of_simulations,
                "most_likely_opponent": top_opponent,
                "most_likely_opponent_probability_unconditional": (
                    likely_opponents.get(top_opponent, 0) / number_of_simulations
                    if top_opponent
                    else 0.0
                ),
                "most_likely_opponent_probability_given_qualification": (
                    likely_opponents.get(top_opponent, 0) / qualified_count
                    if top_opponent and qualified_count
                    else 0.0
                ),
                "prob_finish_1st_group": position_counts[team][1] / number_of_simulations,
                "prob_finish_2nd_group": position_counts[team][2] / number_of_simulations,
                "prob_finish_3rd_group": position_counts[team][3] / number_of_simulations,
                "prob_finish_4th_group": position_counts[team][4] / number_of_simulations,
                "number_of_simulations": int(number_of_simulations),
            }
        )

    return pd.DataFrame(opponent_rows), pd.DataFrame(summary_rows)


def generate_and_save_opponent_probabilities(repo_root: Path, pipeline) -> dict:
    if not opponent_probabilities_enabled():
        return {"status": "disabled"}

    summary_path = repo_root / "backend" / "state" / "last_automation_run.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"Run summary is missing: {summary_path}")
    run_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if run_summary.get("status") != "updated":
        return {"status": "skipped", "reason": str(run_summary.get("status"))}

    data_dir = repo_root / "data"
    world_cup = pd.read_csv(data_dir / "world_cup_2026_matches_latest.csv")
    predictions = pd.read_csv(data_dir / "world_cup_live_predictions_latest.csv")
    team_map = pd.read_csv(pipeline.TEAM_MAP_PATH)
    live_elo = pd.read_csv(pipeline.LIVE_ELO_PATH)
    name_lookup = dict(zip(team_map["live_team_name"], team_map["historical_team_name"]))
    rating_lookup = dict(zip(live_elo["team"], live_elo["elo_rating"]))
    teams = sorted(
        set(world_cup["home_team"].dropna()).union(world_cup["away_team"].dropna())
    )
    live_elo_lookup = {
        team: float(rating_lookup.get(name_lookup.get(team, team), pipeline.INITIAL_RATING))
        for team in teams
    }

    simulations = int(os.environ.get("OPPONENT_PROBABILITY_SIMULATIONS", pipeline.N_SIMULATIONS))
    seed = int(os.environ.get("OPPONENT_PROBABILITY_SEED", pipeline.RANDOM_SEED + 404))
    opponents, team_summary = simulate_opponent_probabilities(
        world_cup,
        predictions,
        live_elo_lookup,
        pipeline,
        simulations,
        seed,
    )

    generated_at = str(run_summary.get("completed_at_utc", ""))
    for frame in (opponents, team_summary):
        frame["generated_at_utc"] = generated_at
        frame["model_version"] = pipeline.MODEL_VERSION
        frame["bracket_mode"] = pipeline.BRACKET_MODE

    opponents_path = data_dir / "round_32_opponent_probabilities_latest.csv"
    summary_output_path = data_dir / "round_32_path_status_latest.csv"
    metadata_path = data_dir / "round_32_opponent_probabilities_metadata.json"
    _atomic_csv(opponents, opponents_path)
    _atomic_csv(team_summary, summary_output_path)
    _atomic_json(
        {
            "status": "generated",
            "generated_at_utc": generated_at,
            "number_of_simulations": simulations,
            "random_seed": seed,
            "teams": int(team_summary["team"].nunique()),
            "opponent_rows": int(len(opponents)),
            "fixture_status_counts": team_summary["fixture_status"].value_counts().to_dict(),
            "bracket_mode": pipeline.BRACKET_MODE,
            "note": (
                "Third-place opponent assignments remain provisional while the "
                "main bracket mode is provisional_constraint_assignment."
            ),
        },
        metadata_path,
    )
    return {
        "status": "generated",
        "opponent_rows": int(len(opponents)),
        "teams": int(team_summary["team"].nunique()),
        "number_of_simulations": simulations,
    }
