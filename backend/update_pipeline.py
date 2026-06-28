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

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import joblib
import numpy as np
import pandas as pd
import requests
from scipy.stats import poisson
from sklearn.metrics import accuracy_score, log_loss

try:
    from features import adaptive_ratings
except ImportError:
    adaptive_ratings = None


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
    "1",
    "true",
    "yes",
    "on",
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
MODEL_VERSION = "phase9b_adaptive_prediction_v1"
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
ADAPTIVE_RATINGS_OUTPUT_PATH = DATA_DIR / "adaptive_ratings_latest.csv"

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

UPCOMING_MATCH_STATUSES = {"TIMED", "SCHEDULED"}
PLACEHOLDER_TEAM_NAMES = {
    "",
    "TBD",
    "TBA",
    "TO BE DECIDED",
    "TO BE CONFIRMED",
    "UNKNOWN",
    "NULL",
    "NONE",
    "NAN",
}
KNOCKOUT_SETTLEMENT_STAGES = {
    "LAST_32": "round_32",
    "ROUND_OF_32": "round_32",
    "R32": "round_32",
    "LAST_16": "round_16",
    "ROUND_OF_16": "round_16",
    "R16": "round_16",
    "QUARTER_FINALS": "quarter_final",
    "QUARTER_FINAL": "quarter_final",
    "QF": "quarter_final",
    "SEMI_FINALS": "semi_final",
    "SEMI_FINAL": "semi_final",
    "SF": "semi_final",
    "FINAL": "final",
}

# NOTE: remainder of file intentionally omitted by this patch guard.
