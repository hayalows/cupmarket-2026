from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from uuid import uuid4
import json
import math
import os
import sys
import time

import joblib
import numpy as np
import pandas as pd
import requests
from scipy.stats import poisson
from sklearn.metrics import accuracy_score, log_loss


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
HISTORY_DIR = DATA_DIR / "market_history"
STATE_DIR = REPO_ROOT / "backend" / "state"
MODELS_DIR = STATE_DIR / "models"

for folder in [DATA_DIR, HISTORY_DIR, STATE_DIR, MODELS_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

API_URL = "https://api.football-data.org/v4/competitions/WC/matches"
TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
N_SIMULATIONS = int(os.environ.get("N_SIMULATIONS", "20000"))
FORCE_RUN = os.environ.get("FORCE_RUN", "false").lower() in {
    "1", "true", "yes", "on"
}
RANDOM_SEED = int(
    os.environ.get(
        "RANDOM_SEED",
        datetime.now(timezone.utc).strftime("%Y%m%d"),
    )
)

if not TOKEN:
    raise RuntimeError(
        "FOOTBALL_DATA_TOKEN is missing from GitHub Actions secrets."
    )

MODEL_VERSION = "phase7_automated_group_stage_v1"
BRACKET_MODE = "provisional_constraint_assignment"

HOME_MODEL_PATH = MODELS_DIR / "phase3_home_goal_model.joblib"
AWAY_MODEL_PATH = MODELS_DIR / "phase3_away_goal_model.joblib"
TEAM_MAP_PATH = STATE_DIR / "world_cup_team_name_map.csv"
LIVE_ELO_PATH = STATE_DIR / "live_elo_ratings.csv"
LIVE_TEAM_STATE_PATH = STATE_DIR / "live_team_state.csv"
PROCESSED_LEDGER_PATH = STATE_DIR / "world_cup_processed_match_ledger.csv"
PREDICTION_LEDGER_PATH = STATE_DIR / "world_cup_prediction_ledger.csv"
FROZEN_PREDICTIONS_PATH = STATE_DIR / "group_stage_phase3_xg_predictions.csv"

MATCHES_OUTPUT_PATH = DATA_DIR / "world_cup_2026_matches_latest.csv"
LIVE_PREDICTIONS_OUTPUT_PATH = DATA_DIR / "world_cup_live_predictions_latest.csv"
CURRENT_TABLES_OUTPUT_PATH = DATA_DIR / "current_group_tables.csv"
TOURNAMENT_OUTPUT_PATH = DATA_DIR / "tournament_probabilities_latest.csv"
PRICES_OUTPUT_PATH = DATA_DIR / "cupmarket_prices_latest.csv"
LIVE_EVALUATION_OUTPUT_PATH = DATA_DIR / "phase4_live_evaluation.json"
SIMULATION_METADATA_OUTPUT_PATH = DATA_DIR / "phase5_simulation_metadata.json"
RUN_SUMMARY_PATH = STATE_DIR / "last_automation_run.json"

INITIAL_RATING = 1500.0
INITIAL_GOALS_AVERAGE = 1.25
INITIAL_POINTS_AVERAGE = 1.25
STATE_ALPHA = 0.18
WORLD_CUP_K = 60.0
HOST_ELO_ADJUSTMENT = 65.0
MAX_REST_DAYS = 365.0
MAX_GOALS = 10
MIN_XG = 0.05
MAX_XG = 5.50
EXTRA_TIME_GOAL_FACTOR = 0.30

WORLD_CUP_HOSTS = {"Mexico", "Canada", "United States"}

FEATURE_COLUMNS = [
    "home_elo",
    "away_elo",
    "elo_diff",
    "abs_elo_diff",
    "neutral",
    "home_attack_form",
    "home_defence_form",
    "away_attack_form",
    "away_defence_form",
    "home_points_form",
    "away_points_form",
    "home_matches_before",
    "away_matches_before",
    "home_rest_days",
    "away_rest_days",
    "k_factor",
]

SETTLEMENT_VALUES = {
    "group_exit": 5.0,
    "round_32_exit": 15.0,
    "round_16_exit": 30.0,
    "quarter_final_exit": 50.0,
    "semi_final_exit": 70.0,
    "runner_up": 85.0,
    "champion": 100.0,
}

FIXED_R32 = {
    73: ("2A", "2B"),
    75: ("1F", "2C"),
    76: ("1C", "2F"),
    78: ("2E", "2I"),
    83: ("2K", "2L"),
    84: ("1H", "2J"),
    86: ("1J", "2H"),
    88: ("2D", "2G"),
}

THIRD_PLACE_R32_WINNER = {
    74: "1E",
    77: "1I",
    79: "1A",
    80: "1L",
    81: "1D",
    82: "1G",
    85: "1B",
    87: "1K",
}

THIRD_SLOT_ALLOWED = {
    74: set("ABCDF"),
    77: set("CDFGH"),
    79: set("CEFHI"),
    80: set("EHIJK"),
    81: set("BEFIJ"),
    82: set("AEHIJ"),
    85: set("EFGIJ"),
    87: set("DEIJL"),
}

ROUND_OF_16 = {
    89: (74, 77),
    90: (73, 75),
    91: (76, 78),
    92: (79, 80),
    93: (83, 84),
    94: (81, 82),
    95: (86, 88),
    96: (85, 87),
}

QUARTER_FINALS = {
    97: (89, 90),
    98: (93, 94),
    99: (91, 92),
    100: (95, 96),
}

SEMI_FINALS = {
    101: (97, 98),
    102: (99, 100),
}


def atomic_to_csv(frame: pd.DataFrame, path: Path) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temp_path, index=False)
    temp_path.replace(path)


def atomic_to_json(payload: dict, path: Path) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)
    temp_path.replace(path)


def nested_get(dictionary: dict, keys: list[str], default=None):
    current = dictionary
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def fetch_world_cup_matches() -> tuple[pd.DataFrame, dict]:
    response = requests.get(
        API_URL,
        headers={"X-Auth-Token": TOKEN},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()

    rows = []
    for match in payload.get("matches", []):
        rows.append(
            {
                "match_id": match.get("id"),
                "utc_date": match.get("utcDate"),
                "status": match.get("status"),
                "stage": match.get("stage"),
                "group": match.get("group"),
                "matchday": match.get("matchday"),
                "home_team": nested_get(match, ["homeTeam", "name"]),
                "away_team": nested_get(match, ["awayTeam", "name"]),
                "winner": nested_get(match, ["score", "winner"]),
                "duration": nested_get(match, ["score", "duration"]),
                "home_score_full_time": nested_get(
                    match, ["score", "fullTime", "home"]
                ),
                "away_score_full_time": nested_get(
                    match, ["score", "fullTime", "away"]
                ),
                "last_updated": match.get("lastUpdated"),
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("The World Cup API returned no matches.")

    frame["utc_date"] = pd.to_datetime(
        frame["utc_date"], errors="coerce", utc=True
    )
    frame["last_updated"] = pd.to_datetime(
        frame["last_updated"], errors="coerce", utc=True
    )
    frame = frame.sort_values(["utc_date", "match_id"]).reset_index(drop=True)

    metadata = {
        "http_status": response.status_code,
        "matches_returned": len(frame),
        "requests_remaining": (
            response.headers.get("X-RequestsAvailable")
            or response.headers.get("X-Requests-Available-Minute")
        ),
        "request_counter_reset": response.headers.get(
            "X-RequestCounter-Reset"
        ),
    }
    return frame, metadata


def actual_result(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "HOME_WIN"
    if home_score == away_score:
        return "DRAW"
    return "AWAY_WIN"


def points_from_score(goals_for: int, goals_against: int) -> float:
    if goals_for > goals_against:
        return 3.0
    if goals_for == goals_against:
        return 1.0
    return 0.0


def goal_margin_multiplier(home_score: int, away_score: int) -> float:
    margin = abs(int(home_score) - int(away_score))
    if margin <= 1:
        return 1.0
    if margin == 2:
        return 1.5
    if margin == 3:
        return 1.75
    return 1.75 + (margin - 3) / 8.0


def elo_expected_score(
    home_rating: float,
    away_rating: float,
    host_adjustment: float = 0.0,
) -> float:
    effective_home = home_rating + host_adjustment
    return 1.0 / (
        1.0 + 10.0 ** ((away_rating - effective_home) / 400.0)
    )


def actual_home_elo_score(home_score: int, away_score: int) -> float:
    if home_score > away_score:
        return 1.0
    if home_score == away_score:
        return 0.5
    return 0.0


def rest_days(last_date, current_date) -> float:
    if last_date is None or pd.isna(last_date):
        return MAX_REST_DAYS
    days = (current_date - last_date).days
    return float(np.clip(days, 0, MAX_REST_DAYS))


def clip_xg(value: float) -> float:
    return float(np.clip(value, MIN_XG, MAX_XG))


def score_probability_matrix(
    expected_home_goals: float,
    expected_away_goals: float,
    max_goals: int = MAX_GOALS,
) -> np.ndarray:
    home_probs = poisson.pmf(
        np.arange(max_goals + 1), clip_xg(expected_home_goals)
    )
    away_probs = poisson.pmf(
        np.arange(max_goals + 1), clip_xg(expected_away_goals)
    )
    matrix = np.outer(home_probs, away_probs)
    return matrix / matrix.sum()


def summarize_score_matrix(matrix: np.ndarray) -> dict:
    home_win = float(np.tril(matrix, k=-1).sum())
    draw = float(np.trace(matrix))
    away_win = float(np.triu(matrix, k=1).sum())
    btts_yes = float(matrix[1:, 1:].sum())
    over_2_5 = float(
        sum(
            matrix[h, a]
            for h in range(MAX_GOALS + 1)
            for a in range(MAX_GOALS + 1)
            if h + a >= 3
        )
    )

    scorelines = []
    for home_goals in range(MAX_GOALS + 1):
        for away_goals in range(MAX_GOALS + 1):
            scorelines.append(
                {
                    "score": f"{home_goals}-{away_goals}",
                    "probability": float(matrix[home_goals, away_goals]),
                }
            )

    scorelines.sort(key=lambda row: row["probability"], reverse=True)

    return {
        "prob_home_win": home_win,
        "prob_draw": draw,
        "prob_away_win": away_win,
        "prob_btts_yes": btts_yes,
        "prob_over_2_5": over_2_5,
        "top_scorelines": scorelines[:5],
    }


def display_prediction_label(
    home_probability: float,
    draw_probability: float,
    away_probability: float,
) -> str:
    probability_map = {
        "HOME_WIN": home_probability,
        "DRAW": draw_probability,
        "AWAY_WIN": away_probability,
    }
    ordered = sorted(
        probability_map.items(), key=lambda item: item[1], reverse=True
    )
    top_result, top_probability = ordered[0]
    gap = ordered[0][1] - ordered[1][1]

    if top_probability < 0.45 or gap < 0.08:
        return "TOO_CLOSE_TO_CALL"
    if top_probability >= 0.65:
        return f"STRONG_{top_result}"
    return f"LEAN_{top_result}"


def blank_stats(team: str) -> dict:
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


def build_group_stats(group_teams: list[str], results: list[dict]) -> dict:
    stats = {team: blank_stats(team) for team in group_teams}

    for result in results:
        home = result["home_team"]
        away = result["away_team"]
        home_goals = int(result["home_goals"])
        away_goals = int(result["away_goals"])

        stats[home]["played"] += 1
        stats[away]["played"] += 1
        stats[home]["goals_for"] += home_goals
        stats[home]["goals_against"] += away_goals
        stats[away]["goals_for"] += away_goals
        stats[away]["goals_against"] += home_goals

        if home_goals > away_goals:
            stats[home]["wins"] += 1
            stats[away]["losses"] += 1
            stats[home]["points"] += 3
        elif home_goals < away_goals:
            stats[away]["wins"] += 1
            stats[home]["losses"] += 1
            stats[away]["points"] += 3
        else:
            stats[home]["draws"] += 1
            stats[away]["draws"] += 1
            stats[home]["points"] += 1
            stats[away]["points"] += 1

    for team in group_teams:
        stats[team]["goal_difference"] = (
            stats[team]["goals_for"] - stats[team]["goals_against"]
        )
    return stats


def head_to_head_stats(tied_teams: list[str], results: list[dict]) -> dict:
    tied_set = set(tied_teams)
    relevant = [
        result
        for result in results
        if result["home_team"] in tied_set
        and result["away_team"] in tied_set
    ]
    return build_group_stats(tied_teams, relevant)


def rank_group(
    group_teams: list[str],
    results: list[dict],
    live_elo_lookup: dict[str, float],
) -> tuple[list[dict], int]:
    overall = build_group_stats(group_teams, results)
    points_groups: dict[int, list[str]] = {}

    for team in group_teams:
        points_groups.setdefault(overall[team]["points"], []).append(team)

    ranked = []
    elo_fallback_used = 0

    for points in sorted(points_groups, reverse=True):
        tied = points_groups[points]
        if len(tied) == 1:
            ranked.extend(tied)
            continue

        h2h = head_to_head_stats(tied, results)

        def ranking_key(team: str):
            return (
                h2h[team]["points"],
                h2h[team]["goal_difference"],
                h2h[team]["goals_for"],
                overall[team]["goal_difference"],
                overall[team]["goals_for"],
                live_elo_lookup.get(team, INITIAL_RATING),
            )

        tied_sorted = sorted(tied, key=ranking_key, reverse=True)

        for index in range(len(tied_sorted) - 1):
            first = tied_sorted[index]
            second = tied_sorted[index + 1]
            if ranking_key(first)[:-1] == ranking_key(second)[:-1]:
                elo_fallback_used += 1

        ranked.extend(tied_sorted)

    table = []
    for position, team in enumerate(ranked, start=1):
        row = overall[team].copy()
        row["position"] = position
        table.append(row)

    return table, elo_fallback_used


def rank_third_placed(
    third_rows: list[dict],
    live_elo_lookup: dict[str, float],
) -> list[dict]:
    return sorted(
        third_rows,
        key=lambda row: (
            row["points"],
            row["goal_difference"],
            row["goals_for"],
            live_elo_lookup.get(row["team"], INITIAL_RATING),
        ),
        reverse=True,
    )


@lru_cache(maxsize=None)
def valid_third_place_assignments(
    qualifying_groups_tuple: tuple[str, ...],
) -> tuple:
    qualifying_groups = set(qualifying_groups_tuple)
    slot_order = sorted(
        THIRD_SLOT_ALLOWED,
        key=lambda slot: len(THIRD_SLOT_ALLOWED[slot] & qualifying_groups),
    )
    solutions = []

    def backtrack(position, remaining_groups, current):
        if position == len(slot_order):
            solutions.append(tuple(sorted(current.items())))
            return

        slot = slot_order[position]
        possible_groups = sorted(
            THIRD_SLOT_ALLOWED[slot] & remaining_groups
        )

        for group in possible_groups:
            current[slot] = group
            backtrack(
                position + 1,
                remaining_groups - {group},
                current,
            )
            del current[slot]

    backtrack(0, qualifying_groups, {})
    return tuple(solutions)


def choose_third_place_assignment(
    best_third_by_group: dict[str, str],
    rng: np.random.Generator,
) -> dict[int, str]:
    group_tuple = tuple(sorted(best_third_by_group))
    assignments = valid_third_place_assignments(group_tuple)

    if not assignments:
        raise RuntimeError(
            f"No valid third-place assignment for groups {group_tuple}."
        )

    selected = assignments[int(rng.integers(0, len(assignments)))]
    slot_to_group = dict(selected)

    return {
        slot: best_third_by_group[group]
        for slot, group in slot_to_group.items()
    }


def load_state() -> tuple:
    required = [
        HOME_MODEL_PATH,
        AWAY_MODEL_PATH,
        TEAM_MAP_PATH,
        LIVE_ELO_PATH,
        LIVE_TEAM_STATE_PATH,
    ]
    for path in required:
        if not path.exists():
            raise FileNotFoundError(f"Required backend artifact missing: {path}")

    home_model = joblib.load(HOME_MODEL_PATH)
    away_model = joblib.load(AWAY_MODEL_PATH)
    team_map = pd.read_csv(TEAM_MAP_PATH)
    live_elo = pd.read_csv(LIVE_ELO_PATH)
    live_team_state = pd.read_csv(LIVE_TEAM_STATE_PATH)
    live_team_state["last_date"] = pd.to_datetime(
        live_team_state["last_date"], errors="coerce", utc=True
    )

    if PROCESSED_LEDGER_PATH.exists():
        processed_ledger = pd.read_csv(PROCESSED_LEDGER_PATH)
    else:
        processed_ledger = pd.DataFrame(
            columns=[
                "match_id",
                "utc_date",
                "stage",
                "home_team",
                "away_team",
                "home_score",
                "away_score",
                "processed_at_utc",
                "model_version",
            ]
        )

    if PREDICTION_LEDGER_PATH.exists():
        prediction_ledger = pd.read_csv(PREDICTION_LEDGER_PATH)
    elif FROZEN_PREDICTIONS_PATH.exists():
        prediction_ledger = pd.read_csv(FROZEN_PREDICTIONS_PATH)
        prediction_ledger["prediction_id"] = [
            f"frozen_{match_id}_{index}"
            for index, match_id in enumerate(prediction_ledger["match_id"])
        ]
        prediction_ledger["prediction_source"] = "frozen_phase3"
        prediction_ledger["state_matches_processed"] = 0
    else:
        raise FileNotFoundError(
            "Prediction ledger and frozen predictions are both missing."
        )

    return (
        home_model,
        away_model,
        team_map,
        live_elo,
        live_team_state,
        processed_ledger,
        prediction_ledger,
    )


def update_live_state(
    world_cup: pd.DataFrame,
    team_map: pd.DataFrame,
    live_elo: pd.DataFrame,
    live_team_state: pd.DataFrame,
    processed_ledger: pd.DataFrame,
) -> tuple:
    name_lookup = dict(
        zip(team_map["live_team_name"], team_map["historical_team_name"])
    )
    rating_lookup = dict(zip(live_elo["team"], live_elo["elo_rating"]))
    state_lookup = (
        live_team_state.set_index("team").to_dict(orient="index")
    )

    processed_ids = set(
        pd.to_numeric(
            processed_ledger.get("match_id", pd.Series(dtype=float)),
            errors="coerce",
        )
        .dropna()
        .astype(int)
    )

    finished_group_matches = (
        world_cup[
            (world_cup["stage"] == "GROUP_STAGE")
            & (world_cup["status"] == "FINISHED")
            & world_cup["home_team"].notna()
            & world_cup["away_team"].notna()
            & world_cup["home_score_full_time"].notna()
            & world_cup["away_score_full_time"].notna()
        ]
        .sort_values("utc_date")
        .copy()
    )

    new_finished_matches = (
        finished_group_matches[
            ~finished_group_matches["match_id"]
            .astype(int)
            .isin(processed_ids)
        ]
        .sort_values("utc_date")
        .reset_index(drop=True)
    )

    def get_live_state(team):
        if team not in state_lookup:
            state_lookup[team] = {
                "matches": 0,
                "ema_goals_for": INITIAL_GOALS_AVERAGE,
                "ema_goals_against": INITIAL_GOALS_AVERAGE,
                "ema_points": INITIAL_POINTS_AVERAGE,
                "last_date": pd.NaT,
            }
        return state_lookup[team]

    ledger_rows = []
    audit_rows = []

    for match in new_finished_matches.itertuples(index=False):
        home_live = match.home_team
        away_live = match.away_team
        home_team = name_lookup.get(home_live, home_live)
        away_team = name_lookup.get(away_live, away_live)
        home_score = int(match.home_score_full_time)
        away_score = int(match.away_score_full_time)

        home_rating_before = float(
            rating_lookup.get(home_team, INITIAL_RATING)
        )
        away_rating_before = float(
            rating_lookup.get(away_team, INITIAL_RATING)
        )

        host_adjustment = 0.0
        if home_live in WORLD_CUP_HOSTS:
            host_adjustment += HOST_ELO_ADJUSTMENT
        if away_live in WORLD_CUP_HOSTS:
            host_adjustment -= HOST_ELO_ADJUSTMENT

        expected_home = elo_expected_score(
            home_rating_before,
            away_rating_before,
            host_adjustment=host_adjustment,
        )
        actual_home = actual_home_elo_score(home_score, away_score)
        rating_change = (
            WORLD_CUP_K
            * goal_margin_multiplier(home_score, away_score)
            * (actual_home - expected_home)
        )

        home_rating_after = home_rating_before + rating_change
        away_rating_after = away_rating_before - rating_change

        rating_lookup[home_team] = home_rating_after
        rating_lookup[away_team] = away_rating_after

        home_state = get_live_state(home_team)
        away_state = get_live_state(away_team)

        home_attack_before = float(home_state["ema_goals_for"])
        home_defence_before = float(home_state["ema_goals_against"])
        home_points_before = float(home_state["ema_points"])
        away_attack_before = float(away_state["ema_goals_for"])
        away_defence_before = float(away_state["ema_goals_against"])
        away_points_before = float(away_state["ema_points"])

        home_points = points_from_score(home_score, away_score)
        away_points = points_from_score(away_score, home_score)

        home_state["ema_goals_for"] = (
            STATE_ALPHA * home_score
            + (1 - STATE_ALPHA) * home_attack_before
        )
        home_state["ema_goals_against"] = (
            STATE_ALPHA * away_score
            + (1 - STATE_ALPHA) * home_defence_before
        )
        home_state["ema_points"] = (
            STATE_ALPHA * home_points
            + (1 - STATE_ALPHA) * home_points_before
        )
        home_state["matches"] = int(home_state["matches"]) + 1
        home_state["last_date"] = match.utc_date

        away_state["ema_goals_for"] = (
            STATE_ALPHA * away_score
            + (1 - STATE_ALPHA) * away_attack_before
        )
        away_state["ema_goals_against"] = (
            STATE_ALPHA * home_score
            + (1 - STATE_ALPHA) * away_defence_before
        )
        away_state["ema_points"] = (
            STATE_ALPHA * away_points
            + (1 - STATE_ALPHA) * away_points_before
        )
        away_state["matches"] = int(away_state["matches"]) + 1
        away_state["last_date"] = match.utc_date

        processed_at = datetime.now(timezone.utc).isoformat()

        ledger_rows.append(
            {
                "match_id": int(match.match_id),
                "utc_date": match.utc_date,
                "stage": match.stage,
                "home_team": home_live,
                "away_team": away_live,
                "home_score": home_score,
                "away_score": away_score,
                "processed_at_utc": processed_at,
                "model_version": MODEL_VERSION,
            }
        )

        audit_rows.append(
            {
                "match_id": int(match.match_id),
                "home_team": home_live,
                "away_team": away_live,
                "home_score": home_score,
                "away_score": away_score,
                "home_elo_change": rating_change,
                "away_elo_change": -rating_change,
            }
        )

    live_elo_updated = (
        pd.DataFrame(
            {
                "team": list(rating_lookup.keys()),
                "elo_rating": list(rating_lookup.values()),
            }
        )
        .sort_values("elo_rating", ascending=False)
        .reset_index(drop=True)
    )
    live_elo_updated["rank"] = np.arange(1, len(live_elo_updated) + 1)

    live_state_rows = []
    for team, state in state_lookup.items():
        live_state_rows.append(
            {
                "team": team,
                "matches": int(state["matches"]),
                "ema_goals_for": float(state["ema_goals_for"]),
                "ema_goals_against": float(state["ema_goals_against"]),
                "ema_points": float(state["ema_points"]),
                "last_date": state["last_date"],
            }
        )

    live_team_state_updated = (
        pd.DataFrame(live_state_rows)
        .sort_values("team")
        .reset_index(drop=True)
    )

    if ledger_rows:
        processed_ledger = pd.concat(
            [processed_ledger, pd.DataFrame(ledger_rows)],
            ignore_index=True,
        )
        processed_ledger = (
            processed_ledger.drop_duplicates(
                subset=["match_id"], keep="first"
            )
            .sort_values("utc_date")
            .reset_index(drop=True)
        )

    return (
        live_elo_updated,
        live_team_state_updated,
        processed_ledger,
        new_finished_matches,
        audit_rows,
        finished_group_matches,
        name_lookup,
    )


def generate_live_predictions(
    world_cup: pd.DataFrame,
    home_model,
    away_model,
    team_map: pd.DataFrame,
    live_elo: pd.DataFrame,
    live_team_state: pd.DataFrame,
    processed_ledger: pd.DataFrame,
    prediction_ledger: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    name_lookup = dict(
        zip(team_map["live_team_name"], team_map["historical_team_name"])
    )
    rating_lookup = dict(zip(live_elo["team"], live_elo["elo_rating"]))
    state_lookup = (
        live_team_state.set_index("team").to_dict(orient="index")
    )

    def current_state(team):
        state = state_lookup.get(team)
        if state is None:
            return {
                "matches": 0,
                "ema_goals_for": INITIAL_GOALS_AVERAGE,
                "ema_goals_against": INITIAL_GOALS_AVERAGE,
                "ema_points": INITIAL_POINTS_AVERAGE,
                "last_date": pd.NaT,
            }
        return state

    def build_features(home_live, away_live, match_date):
        home_team = name_lookup.get(home_live, home_live)
        away_team = name_lookup.get(away_live, away_live)

        home_rating = float(
            rating_lookup.get(home_team, INITIAL_RATING)
        )
        away_rating = float(
            rating_lookup.get(away_team, INITIAL_RATING)
        )

        if home_live in WORLD_CUP_HOSTS:
            home_rating += HOST_ELO_ADJUSTMENT
        if away_live in WORLD_CUP_HOSTS:
            away_rating += HOST_ELO_ADJUSTMENT

        home_state = current_state(home_team)
        away_state = current_state(away_team)

        home_last_date = pd.to_datetime(
            home_state["last_date"], errors="coerce", utc=True
        )
        away_last_date = pd.to_datetime(
            away_state["last_date"], errors="coerce", utc=True
        )

        elo_diff = home_rating - away_rating

        return {
            "home_elo": home_rating,
            "away_elo": away_rating,
            "elo_diff": elo_diff,
            "abs_elo_diff": abs(elo_diff),
            "neutral": 1,
            "home_attack_form": float(home_state["ema_goals_for"]),
            "home_defence_form": float(
                home_state["ema_goals_against"]
            ),
            "away_attack_form": float(away_state["ema_goals_for"]),
            "away_defence_form": float(
                away_state["ema_goals_against"]
            ),
            "home_points_form": float(home_state["ema_points"]),
            "away_points_form": float(away_state["ema_points"]),
            "home_matches_before": int(home_state["matches"]),
            "away_matches_before": int(away_state["matches"]),
            "home_rest_days": rest_days(home_last_date, match_date),
            "away_rest_days": rest_days(away_last_date, match_date),
            "k_factor": WORLD_CUP_K,
        }

    upcoming = (
        world_cup[
            (world_cup["stage"] == "GROUP_STAGE")
            & world_cup["status"].isin(["TIMED", "SCHEDULED"])
            & world_cup["home_team"].notna()
            & world_cup["away_team"].notna()
        ]
        .sort_values("utc_date")
        .reset_index(drop=True)
    )

    generated_at = datetime.now(timezone.utc)
    state_match_count = int(len(processed_ledger))
    rows = []

    for match in upcoming.itertuples(index=False):
        features = build_features(
            match.home_team,
            match.away_team,
            match.utc_date,
        )
        feature_frame = pd.DataFrame([features])[FEATURE_COLUMNS]
        home_xg = clip_xg(home_model.predict(feature_frame)[0])
        away_xg = clip_xg(away_model.predict(feature_frame)[0])

        summary = summarize_score_matrix(
            score_probability_matrix(home_xg, away_xg)
        )
        top_scores = summary["top_scorelines"]
        probability_map = {
            "HOME_WIN": summary["prob_home_win"],
            "DRAW": summary["prob_draw"],
            "AWAY_WIN": summary["prob_away_win"],
        }
        predicted_result = max(
            probability_map, key=probability_map.get
        )

        rows.append(
            {
                "prediction_id": str(uuid4()),
                "prediction_source": "phase7_automation",
                "model_version": MODEL_VERSION,
                "generated_at_utc": generated_at.isoformat(),
                "state_matches_processed": state_match_count,
                "created_before_kickoff": (
                    generated_at < match.utc_date.to_pydatetime()
                ),
                "prediction_type": "live_pre_match",
                "match_id": int(match.match_id),
                "utc_date": match.utc_date,
                "status": match.status,
                "stage": match.stage,
                "group": match.group,
                "home_team": match.home_team,
                "away_team": match.away_team,
                "expected_home_goals": round(home_xg, 3),
                "expected_away_goals": round(away_xg, 3),
                "prob_home_win": round(summary["prob_home_win"], 6),
                "prob_draw": round(summary["prob_draw"], 6),
                "prob_away_win": round(summary["prob_away_win"], 6),
                "prob_btts_yes": round(summary["prob_btts_yes"], 6),
                "prob_over_2_5": round(summary["prob_over_2_5"], 6),
                "predicted_result": predicted_result,
                "display_label": display_prediction_label(
                    summary["prob_home_win"],
                    summary["prob_draw"],
                    summary["prob_away_win"],
                ),
                "most_likely_score": top_scores[0]["score"],
                "most_likely_score_probability": round(
                    top_scores[0]["probability"], 6
                ),
                "second_likely_score": top_scores[1]["score"],
                "second_likely_score_probability": round(
                    top_scores[1]["probability"], 6
                ),
                "third_likely_score": top_scores[2]["score"],
                "third_likely_score_probability": round(
                    top_scores[2]["probability"], 6
                ),
            }
        )

    live_predictions = pd.DataFrame(rows)

    if not live_predictions.empty:
        sums = live_predictions[
            ["prob_home_win", "prob_draw", "prob_away_win"]
        ].sum(axis=1)
        if not np.allclose(sums, 1.0, atol=0.00001):
            raise ValueError(
                "Some live result probabilities do not add to 1."
            )

        prediction_ledger = pd.concat(
            [prediction_ledger, live_predictions],
            ignore_index=True,
            sort=False,
        )
        prediction_ledger = (
            prediction_ledger.drop_duplicates(
                subset=["prediction_id"], keep="first"
            )
            .sort_values(["utc_date", "generated_at_utc"])
            .reset_index(drop=True)
        )

    return live_predictions, prediction_ledger


def create_live_scorecard(
    finished_group_matches: pd.DataFrame,
    prediction_ledger: pd.DataFrame,
) -> dict:
    if prediction_ledger.empty:
        return {
            "eligible_completed_predictions": 0,
            "message": "The prediction ledger is empty.",
        }

    prediction_ledger = prediction_ledger.copy()
    prediction_ledger["generated_at_utc"] = pd.to_datetime(
        prediction_ledger["generated_at_utc"],
        errors="coerce",
        utc=True,
    )

    rows = []

    for match in finished_group_matches.itertuples(index=False):
        candidates = prediction_ledger[
            (
                pd.to_numeric(
                    prediction_ledger["match_id"], errors="coerce"
                )
                == int(match.match_id)
            )
            & (
                prediction_ledger["generated_at_utc"]
                < match.utc_date
            )
        ].sort_values("generated_at_utc")

        if candidates.empty:
            continue

        selected = candidates.iloc[-1]
        actual = actual_result(
            int(match.home_score_full_time),
            int(match.away_score_full_time),
        )

        probability_map = {
            "HOME_WIN": float(selected["prob_home_win"]),
            "DRAW": float(selected["prob_draw"]),
            "AWAY_WIN": float(selected["prob_away_win"]),
        }

        rows.append(
            {
                "actual_result": actual,
                "predicted_result": max(
                    probability_map,
                    key=probability_map.get,
                ),
                "prob_home_win": probability_map["HOME_WIN"],
                "prob_draw": probability_map["DRAW"],
                "prob_away_win": probability_map["AWAY_WIN"],
            }
        )

    scorecard = pd.DataFrame(rows)

    if scorecard.empty:
        return {
            "eligible_completed_predictions": 0,
            "message": (
                "No completed match has a prediction "
                "stored before kickoff yet."
            ),
        }

    probability_matrix = scorecard[
        ["prob_away_win", "prob_draw", "prob_home_win"]
    ].to_numpy()

    accuracy = accuracy_score(
        scorecard["actual_result"],
        scorecard["predicted_result"],
    )
    scorecard_log_loss = log_loss(
        scorecard["actual_result"],
        probability_matrix,
        labels=["AWAY_WIN", "DRAW", "HOME_WIN"],
    )

    actual_one_hot = (
        pd.get_dummies(scorecard["actual_result"])
        .reindex(
            columns=["HOME_WIN", "DRAW", "AWAY_WIN"],
            fill_value=0,
        )
        .to_numpy()
    )
    predicted_for_brier = scorecard[
        ["prob_home_win", "prob_draw", "prob_away_win"]
    ].to_numpy()
    brier = float(
        np.mean(
            np.sum(
                (predicted_for_brier - actual_one_hot) ** 2,
                axis=1,
            )
        )
    )

    return {
        "eligible_completed_predictions": int(len(scorecard)),
        "accuracy": float(accuracy),
        "log_loss": float(scorecard_log_loss),
        "multiclass_brier": brier,
    }


def build_current_tables(
    world_cup: pd.DataFrame,
    live_elo_lookup: dict[str, float],
) -> tuple[pd.DataFrame, dict, dict, list[str]]:
    group_matches = (
        world_cup[world_cup["stage"] == "GROUP_STAGE"]
        .sort_values("utc_date")
        .reset_index(drop=True)
    )
    if len(group_matches) != 72:
        raise ValueError(
            f"Expected 72 group matches, found {len(group_matches)}."
        )

    group_letter = {
        f"GROUP_{letter}": letter for letter in "ABCDEFGHIJKL"
    }
    team_to_group = {}

    for row in group_matches.itertuples(index=False):
        team_to_group[row.home_team] = group_letter[row.group]
        team_to_group[row.away_team] = group_letter[row.group]

    teams = sorted(team_to_group)
    if len(teams) != 48:
        raise ValueError(f"Expected 48 teams, found {len(teams)}.")

    groups_to_teams = {
        letter: sorted(
            [
                team
                for team, team_group in team_to_group.items()
                if team_group == letter
            ]
        )
        for letter in "ABCDEFGHIJKL"
    }

    completed_results = {letter: [] for letter in "ABCDEFGHIJKL"}

    for match in group_matches.itertuples(index=False):
        is_finished = (
            match.status == "FINISHED"
            and pd.notna(match.home_score_full_time)
            and pd.notna(match.away_score_full_time)
        )
        if not is_finished:
            continue

        letter = group_letter[match.group]
        completed_results[letter].append(
            {
                "home_team": match.home_team,
                "away_team": match.away_team,
                "home_goals": int(match.home_score_full_time),
                "away_goals": int(match.away_score_full_time),
            }
        )

    rows = []
    for letter in "ABCDEFGHIJKL":
        table, _ = rank_group(
            groups_to_teams[letter],
            completed_results[letter],
            live_elo_lookup,
        )
        for row in table:
            output = row.copy()
            output["group"] = letter
            rows.append(output)

    current_tables = pd.DataFrame(rows)[
        [
            "group",
            "position",
            "team",
            "played",
            "wins",
            "draws",
            "losses",
            "goals_for",
            "goals_against",
            "goal_difference",
            "points",
        ]
    ]

    return (
        current_tables,
        groups_to_teams,
        team_to_group,
        teams,
    )


def run_tournament_simulation(
    world_cup: pd.DataFrame,
    live_predictions: pd.DataFrame,
    home_model,
    away_model,
    team_map: pd.DataFrame,
    live_elo: pd.DataFrame,
    live_team_state: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    group_matches = (
        world_cup[world_cup["stage"] == "GROUP_STAGE"]
        .sort_values("utc_date")
        .reset_index(drop=True)
    )

    prediction_lookup = (
        live_predictions.drop_duplicates("match_id", keep="last")
        .set_index("match_id")
        if not live_predictions.empty
        else pd.DataFrame()
    )

    name_lookup = dict(
        zip(team_map["live_team_name"], team_map["historical_team_name"])
    )
    rating_lookup = dict(zip(live_elo["team"], live_elo["elo_rating"]))
    state_lookup = (
        live_team_state.set_index("team").to_dict(orient="index")
    )

    group_letter = {
        f"GROUP_{letter}": letter for letter in "ABCDEFGHIJKL"
    }
    team_to_group = {}
    for row in group_matches.itertuples(index=False):
        team_to_group[row.home_team] = group_letter[row.group]
        team_to_group[row.away_team] = group_letter[row.group]

    teams = sorted(team_to_group)
    groups_to_teams = {
        letter: sorted(
            [
                team
                for team, group in team_to_group.items()
                if group == letter
            ]
        )
        for letter in "ABCDEFGHIJKL"
    }

    live_elo_lookup = {}
    for live_team in teams:
        historical_team = name_lookup.get(live_team, live_team)
        live_elo_lookup[live_team] = float(
            rating_lookup.get(historical_team, INITIAL_RATING)
        )

    simulation_matches_by_group = {
        letter: [] for letter in "ABCDEFGHIJKL"
    }

    for match in group_matches.itertuples(index=False):
        letter = group_letter[match.group]
        is_finished = (
            match.status == "FINISHED"
            and pd.notna(match.home_score_full_time)
            and pd.notna(match.away_score_full_time)
        )

        if is_finished:
            home_xg = None
            away_xg = None
        else:
            if prediction_lookup.empty or int(match.match_id) not in prediction_lookup.index:
                raise ValueError(
                    "No live prediction found for unplayed match "
                    f"{match.match_id}: {match.home_team} vs {match.away_team}."
                )
            prediction = prediction_lookup.loc[int(match.match_id)]
            home_xg = float(prediction["expected_home_goals"])
            away_xg = float(prediction["expected_away_goals"])

        simulation_matches_by_group[letter].append(
            {
                "match_id": int(match.match_id),
                "home_team": match.home_team,
                "away_team": match.away_team,
                "is_finished": is_finished,
                "actual_home_score": (
                    int(match.home_score_full_time)
                    if is_finished
                    else None
                ),
                "actual_away_score": (
                    int(match.away_score_full_time)
                    if is_finished
                    else None
                ),
                "home_xg": home_xg,
                "away_xg": away_xg,
            }
        )

    pair_xg_cache = {}

    def get_state_for_live_team(live_team):
        historical_team = name_lookup.get(live_team, live_team)
        state = state_lookup.get(historical_team)
        if state is None:
            return {
                "matches": 0,
                "ema_goals_for": INITIAL_GOALS_AVERAGE,
                "ema_goals_against": INITIAL_GOALS_AVERAGE,
                "ema_points": INITIAL_POINTS_AVERAGE,
            }
        return state

    def predict_knockout_xg(home_team, away_team):
        key = (home_team, away_team)
        if key in pair_xg_cache:
            return pair_xg_cache[key]

        home_rating = float(
            live_elo_lookup.get(home_team, INITIAL_RATING)
        )
        away_rating = float(
            live_elo_lookup.get(away_team, INITIAL_RATING)
        )

        if home_team in WORLD_CUP_HOSTS:
            home_rating += HOST_ELO_ADJUSTMENT
        if away_team in WORLD_CUP_HOSTS:
            away_rating += HOST_ELO_ADJUSTMENT

        home_state = get_state_for_live_team(home_team)
        away_state = get_state_for_live_team(away_team)
        elo_diff = home_rating - away_rating

        frame = pd.DataFrame(
            [
                {
                    "home_elo": home_rating,
                    "away_elo": away_rating,
                    "elo_diff": elo_diff,
                    "abs_elo_diff": abs(elo_diff),
                    "neutral": 1,
                    "home_attack_form": float(
                        home_state["ema_goals_for"]
                    ),
                    "home_defence_form": float(
                        home_state["ema_goals_against"]
                    ),
                    "away_attack_form": float(
                        away_state["ema_goals_for"]
                    ),
                    "away_defence_form": float(
                        away_state["ema_goals_against"]
                    ),
                    "home_points_form": float(
                        home_state["ema_points"]
                    ),
                    "away_points_form": float(
                        away_state["ema_points"]
                    ),
                    "home_matches_before": int(
                        home_state["matches"]
                    ),
                    "away_matches_before": int(
                        away_state["matches"]
                    ),
                    "home_rest_days": 5.0,
                    "away_rest_days": 5.0,
                    "k_factor": WORLD_CUP_K,
                }
            ]
        )[FEATURE_COLUMNS]

        home_xg = clip_xg(home_model.predict(frame)[0])
        away_xg = clip_xg(away_model.predict(frame)[0])
        pair_xg_cache[key] = (home_xg, away_xg)
        return home_xg, away_xg

    def penalty_home_probability(home_team, away_team):
        home_elo = live_elo_lookup.get(home_team, INITIAL_RATING)
        away_elo = live_elo_lookup.get(away_team, INITIAL_RATING)
        probability = 1.0 / (
            1.0 + 10.0 ** ((away_elo - home_elo) / 500.0)
        )
        return float(np.clip(probability, 0.35, 0.65))

    def simulate_knockout_match(home_team, away_team, rng):
        home_xg, away_xg = predict_knockout_xg(
            home_team, away_team
        )
        home_goals = int(rng.poisson(home_xg))
        away_goals = int(rng.poisson(away_xg))

        if home_goals == away_goals:
            home_goals += int(
                rng.poisson(home_xg * EXTRA_TIME_GOAL_FACTOR)
            )
            away_goals += int(
                rng.poisson(away_xg * EXTRA_TIME_GOAL_FACTOR)
            )

        if home_goals == away_goals:
            if rng.random() < penalty_home_probability(
                home_team, away_team
            ):
                return home_team, away_team
            return away_team, home_team

        if home_goals > away_goals:
            return home_team, away_team
        return away_team, home_team

    rng = np.random.default_rng(RANDOM_SEED)

    counter_columns = [
        "finish_1st_group",
        "finish_2nd_group",
        "finish_3rd_group",
        "best_third_qualifier",
        "reach_round_32",
        "reach_round_16",
        "reach_quarter_final",
        "reach_semi_final",
        "reach_final",
        "champion",
    ]
    counters = {
        team: {column: 0 for column in counter_columns}
        for team in teams
    }

    elo_fallback_total = 0
    assignment_counts = []
    simulation_start = time.time()

    for _ in range(N_SIMULATIONS):
        slot_team = {}
        third_rows = []

        for letter in "ABCDEFGHIJKL":
            group_results = []
            for match in simulation_matches_by_group[letter]:
                if match["is_finished"]:
                    home_goals = match["actual_home_score"]
                    away_goals = match["actual_away_score"]
                else:
                    home_goals = int(rng.poisson(match["home_xg"]))
                    away_goals = int(rng.poisson(match["away_xg"]))

                group_results.append(
                    {
                        "home_team": match["home_team"],
                        "away_team": match["away_team"],
                        "home_goals": home_goals,
                        "away_goals": away_goals,
                    }
                )

            table, fallback_count = rank_group(
                groups_to_teams[letter],
                group_results,
                live_elo_lookup,
            )
            elo_fallback_total += fallback_count

            first = table[0]["team"]
            second = table[1]["team"]
            third = table[2].copy()
            third["group"] = letter

            counters[first]["finish_1st_group"] += 1
            counters[second]["finish_2nd_group"] += 1
            counters[third["team"]]["finish_3rd_group"] += 1

            slot_team[f"1{letter}"] = first
            slot_team[f"2{letter}"] = second
            third_rows.append(third)

        ranked_thirds = rank_third_placed(
            third_rows, live_elo_lookup
        )
        best_eight = ranked_thirds[:8]
        best_third_by_group = {
            row["group"]: row["team"] for row in best_eight
        }

        for row in best_eight:
            counters[row["team"]]["best_third_qualifier"] += 1

        group_tuple = tuple(sorted(best_third_by_group))
        assignment_counts.append(
            len(valid_third_place_assignments(group_tuple))
        )
        third_slot_team = choose_third_place_assignment(
            best_third_by_group, rng
        )

        r32_pairings = {}
        for match_id, (home_slot, away_slot) in FIXED_R32.items():
            r32_pairings[match_id] = (
                slot_team[home_slot],
                slot_team[away_slot],
            )
        for match_id, winner_slot in THIRD_PLACE_R32_WINNER.items():
            r32_pairings[match_id] = (
                slot_team[winner_slot],
                third_slot_team[match_id],
            )

        r32_teams = {
            team for pairing in r32_pairings.values() for team in pairing
        }
        if len(r32_teams) != 32:
            raise RuntimeError(
                f"Round of 32 contains {len(r32_teams)} unique teams."
            )

        for team in r32_teams:
            counters[team]["reach_round_32"] += 1

        winners = {}

        for match_id in sorted(r32_pairings):
            home_team, away_team = r32_pairings[match_id]
            winner, _ = simulate_knockout_match(
                home_team, away_team, rng
            )
            winners[match_id] = winner
            counters[winner]["reach_round_16"] += 1

        for match_id, (source_a, source_b) in ROUND_OF_16.items():
            winner, _ = simulate_knockout_match(
                winners[source_a], winners[source_b], rng
            )
            winners[match_id] = winner
            counters[winner]["reach_quarter_final"] += 1

        for match_id, (source_a, source_b) in QUARTER_FINALS.items():
            winner, _ = simulate_knockout_match(
                winners[source_a], winners[source_b], rng
            )
            winners[match_id] = winner
            counters[winner]["reach_semi_final"] += 1

        for match_id, (source_a, source_b) in SEMI_FINALS.items():
            winner, _ = simulate_knockout_match(
                winners[source_a], winners[source_b], rng
            )
            winners[match_id] = winner
            counters[winner]["reach_final"] += 1

        champion, _ = simulate_knockout_match(
            winners[101], winners[102], rng
        )
        counters[champion]["champion"] += 1

    simulation_seconds = time.time() - simulation_start

    rows = []
    for team in teams:
        row = {
            "team": team,
            "group": team_to_group[team],
            "live_elo": live_elo_lookup.get(team, INITIAL_RATING),
        }
        for column in counter_columns:
            row[f"prob_{column}"] = (
                counters[team][column] / N_SIMULATIONS
            )

        row["prob_group_exit"] = 1.0 - row["prob_reach_round_32"]
        row["prob_round_32_exit"] = (
            row["prob_reach_round_32"]
            - row["prob_reach_round_16"]
        )
        row["prob_round_16_exit"] = (
            row["prob_reach_round_16"]
            - row["prob_reach_quarter_final"]
        )
        row["prob_quarter_final_exit"] = (
            row["prob_reach_quarter_final"]
            - row["prob_reach_semi_final"]
        )
        row["prob_semi_final_exit"] = (
            row["prob_reach_semi_final"]
            - row["prob_reach_final"]
        )
        row["prob_runner_up"] = (
            row["prob_reach_final"] - row["prob_champion"]
        )
        rows.append(row)

    probabilities = (
        pd.DataFrame(rows)
        .sort_values(
            [
                "prob_champion",
                "prob_reach_final",
                "prob_reach_semi_final",
            ],
            ascending=False,
        )
        .reset_index(drop=True)
    )
    probabilities["champion_rank"] = np.arange(
        1, len(probabilities) + 1
    )

    validation = {
        "round_32_total": float(
            probabilities["prob_reach_round_32"].sum()
        ),
        "round_16_total": float(
            probabilities["prob_reach_round_16"].sum()
        ),
        "quarter_final_total": float(
            probabilities["prob_reach_quarter_final"].sum()
        ),
        "semi_final_total": float(
            probabilities["prob_reach_semi_final"].sum()
        ),
        "final_total": float(
            probabilities["prob_reach_final"].sum()
        ),
        "champion_total": float(
            probabilities["prob_champion"].sum()
        ),
    }
    expected = {
        "round_32_total": 32.0,
        "round_16_total": 16.0,
        "quarter_final_total": 8.0,
        "semi_final_total": 4.0,
        "final_total": 2.0,
        "champion_total": 1.0,
    }
    for key, expected_value in expected.items():
        if not np.isclose(
            validation[key], expected_value, atol=1e-6
        ):
            raise ValueError(
                f"{key} failed: {validation[key]} != {expected_value}"
            )

    prices = probabilities.copy()
    prices["cupmarket_price"] = (
        prices["prob_group_exit"] * SETTLEMENT_VALUES["group_exit"]
        + prices["prob_round_32_exit"]
        * SETTLEMENT_VALUES["round_32_exit"]
        + prices["prob_round_16_exit"]
        * SETTLEMENT_VALUES["round_16_exit"]
        + prices["prob_quarter_final_exit"]
        * SETTLEMENT_VALUES["quarter_final_exit"]
        + prices["prob_semi_final_exit"]
        * SETTLEMENT_VALUES["semi_final_exit"]
        + prices["prob_runner_up"] * SETTLEMENT_VALUES["runner_up"]
        + prices["prob_champion"] * SETTLEMENT_VALUES["champion"]
    ).round(2)

    prices = (
        prices.sort_values("cupmarket_price", ascending=False)
        .reset_index(drop=True)
    )
    prices["market_rank"] = np.arange(1, len(prices) + 1)

    if PRICES_OUTPUT_PATH.exists():
        previous = pd.read_csv(PRICES_OUTPUT_PATH)[
            ["team", "cupmarket_price"]
        ].rename(columns={"cupmarket_price": "previous_price"})
        prices = prices.merge(previous, on="team", how="left")
        prices["price_change"] = (
            prices["cupmarket_price"] - prices["previous_price"]
        )
        prices["price_change_percent"] = (
            100.0 * prices["price_change"] / prices["previous_price"]
        )
    else:
        prices["previous_price"] = np.nan
        prices["price_change"] = np.nan
        prices["price_change_percent"] = np.nan

    metadata = {
        "model_version": MODEL_VERSION,
        "number_of_simulations": N_SIMULATIONS,
        "random_seed": RANDOM_SEED,
        "bracket_mode": BRACKET_MODE,
        "finished_group_matches": int(
            (
                (world_cup["stage"] == "GROUP_STAGE")
                & (world_cup["status"] == "FINISHED")
            ).sum()
        ),
        "remaining_group_matches": int(
            (
                (world_cup["stage"] == "GROUP_STAGE")
                & world_cup["status"].isin(["TIMED", "SCHEDULED"])
            ).sum()
        ),
        "simulation_seconds": float(simulation_seconds),
        "pair_xg_cache_size": int(len(pair_xg_cache)),
        "elo_fallback_uses": int(elo_fallback_total),
        "average_valid_third_place_assignments": float(
            np.mean(assignment_counts)
        ),
        "stage_probability_totals": validation,
        "settlement_values": SETTLEMENT_VALUES,
        "limitations": [
            (
                "Automation v1 processes completed group-stage "
                "matches. Exact knockout-result ingestion is a later phase."
            ),
            (
                "Team conduct data is unavailable; live Elo is used "
                "only after football tiebreak criteria remain equal."
            ),
            (
                "Before the Round of 32 is populated, third-place "
                "teams are sampled across valid official slot constraints."
            ),
            (
                "Extra-time and penalties use transparent approximation rules."
            ),
        ],
    }

    return probabilities, prices, metadata


def main() -> None:
    started_at = datetime.now(timezone.utc)
    print("Starting CupMarket automated update.")
    print("Simulations:", N_SIMULATIONS)
    print("Force run:", FORCE_RUN)

    world_cup, api_metadata = fetch_world_cup_matches()
    (
        home_model,
        away_model,
        team_map,
        live_elo,
        live_team_state,
        processed_ledger,
        prediction_ledger,
    ) = load_state()

    (
        live_elo_updated,
        live_team_state_updated,
        processed_ledger_updated,
        new_finished_matches,
        audit_rows,
        finished_group_matches,
        name_lookup,
    ) = update_live_state(
        world_cup,
        team_map,
        live_elo,
        live_team_state,
        processed_ledger,
    )

    print("New finished group matches:", len(new_finished_matches))

    if new_finished_matches.empty and not FORCE_RUN:
        summary = {
            "status": "no_new_finished_match",
            "checked_at_utc": started_at.isoformat(),
            "api": api_metadata,
            "number_of_simulations": N_SIMULATIONS,
        }
        atomic_to_json(summary, RUN_SUMMARY_PATH)
        print("No new finished group match. No model files changed.")
        return

    live_predictions, prediction_ledger_updated = (
        generate_live_predictions(
            world_cup,
            home_model,
            away_model,
            team_map,
            live_elo_updated,
            live_team_state_updated,
            processed_ledger_updated,
            prediction_ledger,
        )
    )

    historical_name_lookup = dict(
        zip(
            team_map["live_team_name"],
            team_map["historical_team_name"],
        )
    )
    rating_by_historical_name = dict(
        zip(
            live_elo_updated["team"],
            live_elo_updated["elo_rating"],
        )
    )
    live_elo_lookup = {
        live_name: float(
            rating_by_historical_name.get(
                historical_name_lookup.get(live_name, live_name),
                INITIAL_RATING,
            )
        )
        for live_name in set(
            world_cup["home_team"].dropna()
        ).union(
            set(world_cup["away_team"].dropna())
        )
    }

    current_tables, _, _, _ = build_current_tables(
        world_cup,
        live_elo_lookup,
    )

    live_evaluation = create_live_scorecard(
        finished_group_matches,
        prediction_ledger_updated,
    )

    probabilities, prices, simulation_metadata = (
        run_tournament_simulation(
            world_cup,
            live_predictions,
            home_model,
            away_model,
            team_map,
            live_elo_updated,
            live_team_state_updated,
        )
    )

    generated_at = datetime.now(timezone.utc)
    generated_iso = generated_at.isoformat()
    timestamp = generated_at.strftime("%Y%m%dT%H%M%SZ")

    probabilities["generated_at_utc"] = generated_iso
    probabilities["model_version"] = MODEL_VERSION
    probabilities["bracket_mode"] = BRACKET_MODE

    prices["generated_at_utc"] = generated_iso
    prices["model_version"] = MODEL_VERSION
    prices["bracket_mode"] = BRACKET_MODE

    simulation_metadata["generated_at_utc"] = generated_iso
    simulation_metadata["new_finished_matches_processed"] = int(
        len(new_finished_matches)
    )
    simulation_metadata["api"] = api_metadata

    atomic_to_csv(world_cup, MATCHES_OUTPUT_PATH)
    atomic_to_csv(
        live_predictions,
        LIVE_PREDICTIONS_OUTPUT_PATH,
    )
    atomic_to_csv(current_tables, CURRENT_TABLES_OUTPUT_PATH)
    atomic_to_csv(probabilities, TOURNAMENT_OUTPUT_PATH)
    atomic_to_csv(prices, PRICES_OUTPUT_PATH)
    atomic_to_json(
        live_evaluation,
        LIVE_EVALUATION_OUTPUT_PATH,
    )
    atomic_to_json(
        simulation_metadata,
        SIMULATION_METADATA_OUTPUT_PATH,
    )

    history_path = (
        HISTORY_DIR / f"cupmarket_prices_{timestamp}.csv"
    )
    atomic_to_csv(prices, history_path)

    atomic_to_csv(live_elo_updated, LIVE_ELO_PATH)
    atomic_to_csv(live_team_state_updated, LIVE_TEAM_STATE_PATH)
    atomic_to_csv(
        processed_ledger_updated,
        PROCESSED_LEDGER_PATH,
    )
    atomic_to_csv(
        prediction_ledger_updated,
        PREDICTION_LEDGER_PATH,
    )

    summary = {
        "status": "updated",
        "started_at_utc": started_at.isoformat(),
        "completed_at_utc": generated_iso,
        "new_finished_matches": int(len(new_finished_matches)),
        "new_matches": audit_rows,
        "number_of_simulations": N_SIMULATIONS,
        "api": api_metadata,
    }
    atomic_to_json(summary, RUN_SUMMARY_PATH)

    print("CupMarket automated update completed.")
    print("New finished matches processed:", len(new_finished_matches))
    print("Upcoming predictions:", len(live_predictions))
    print("Simulations:", N_SIMULATIONS)
    print("Market leader:", prices.iloc[0]["team"])
    print("Market leader price:", prices.iloc[0]["cupmarket_price"])


if __name__ == "__main__":
    main()
