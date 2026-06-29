from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

try:
    from .live_clock import resolve_match_minute_detail as _resolve_minute_detail
except ImportError:
    from live_clock import resolve_match_minute_detail as _resolve_minute_detail


LIVE_STATUSES = {"IN_PLAY", "LIVE", "PAUSED", "SUSPENDED"}
EXTRA_TIME_GOAL_FACTOR = 0.30
MAX_GOALS = 10
MIN_XG = 0.05
MAX_XG = 5.50


def clean_text(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "null", "nat", "tbd"}:
        return ""
    return text


def is_knockout_stage(stage) -> bool:
    text = clean_text(stage).upper()
    return bool(text and text != "GROUP_STAGE")


def is_live_knockout_match(row: pd.Series | dict[str, Any]) -> bool:
    if not hasattr(row, "get"):
        return False
    return (
        str(row.get("status", "")).upper() in LIVE_STATUSES
        and is_knockout_stage(row.get("stage"))
        and bool(clean_text(row.get("home_team")))
        and bool(clean_text(row.get("away_team")))
    )


def resolve_match_minute(row: pd.Series | dict[str, Any]) -> int:
    return _resolve_minute_detail(row, allow_extra_time=True).minute


def _score_value(row: pd.Series | dict[str, Any], side: str) -> int:
    for suffix in ["full_time", "regular_time", "extra_time"]:
        value = row.get(f"{side}_score_{suffix}") if hasattr(row, "get") else None
        number = pd.to_numeric(value, errors="coerce")
        if pd.notna(number):
            return int(number)
    return 0


def _safe_probability(value) -> float | None:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return None
    return float(np.clip(float(number), 0.0, 1.0))


def _safe_xg(value) -> float | None:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return None
    return float(np.clip(float(number), MIN_XG, MAX_XG))


def _prediction_rows(predictions: pd.DataFrame) -> dict[int, pd.Series]:
    if predictions.empty or "match_id" not in predictions.columns:
        return {}
    frame = predictions.copy()
    frame["match_id"] = pd.to_numeric(frame["match_id"], errors="coerce")
    frame = frame.dropna(subset=["match_id"])
    frame["match_id"] = frame["match_id"].astype(int)
    if "generated_at_utc" in frame.columns:
        frame["generated_at_utc"] = pd.to_datetime(
            frame["generated_at_utc"],
            errors="coerce",
            utc=True,
        )
        frame = frame.sort_values("generated_at_utc")
    frame = frame.drop_duplicates("match_id", keep="last")
    return {
        int(row.match_id): pd.Series(row._asdict())
        for row in frame.itertuples(index=False)
    }


def _poisson_probabilities(mean: float, max_goals: int = MAX_GOALS) -> np.ndarray:
    mean = max(MIN_XG, float(mean))
    values = [np.exp(-mean)]
    for number in range(1, max_goals + 1):
        values.append(values[-1] * mean / number)
    probabilities = np.array(values, dtype=float)
    return probabilities / probabilities.sum()


def _score_matrix(home_xg: float, away_xg: float) -> np.ndarray:
    matrix = np.outer(
        _poisson_probabilities(home_xg),
        _poisson_probabilities(away_xg),
    )
    return matrix / matrix.sum()


def _summarize_matrix(matrix: np.ndarray) -> dict[str, float]:
    return {
        "prob_home_win": float(np.tril(matrix, -1).sum()),
        "prob_draw": float(np.trace(matrix)),
        "prob_away_win": float(np.triu(matrix, 1).sum()),
    }


def penalty_home_probability(prediction: pd.Series) -> float:
    home_elo = pd.to_numeric(
        prediction.get("home_prediction_elo", prediction.get("home_base_elo")),
        errors="coerce",
    )
    away_elo = pd.to_numeric(
        prediction.get("away_prediction_elo", prediction.get("away_base_elo")),
        errors="coerce",
    )
    if pd.isna(home_elo) or pd.isna(away_elo):
        return 0.50
    probability = 1.0 / (1.0 + 10.0 ** ((float(away_elo) - float(home_elo)) / 500.0))
    return float(np.clip(probability, 0.35, 0.65))


def _computed_prematch_advance(
    home_xg: float,
    away_xg: float,
    penalty_home: float,
    extra_time_goal_factor: float,
) -> tuple[float, float]:
    regulation = _summarize_matrix(_score_matrix(home_xg, away_xg))
    extra_time = _summarize_matrix(
        _score_matrix(
            home_xg * extra_time_goal_factor,
            away_xg * extra_time_goal_factor,
        )
    )
    home_advance = regulation["prob_home_win"] + regulation["prob_draw"] * (
        extra_time["prob_home_win"] + extra_time["prob_draw"] * penalty_home
    )
    return float(home_advance), float(1.0 - home_advance)


def _prediction_inputs(
    prediction: pd.Series,
    extra_time_goal_factor: float,
) -> dict[str, float] | None:
    home_xg = _safe_xg(prediction.get("expected_home_goals"))
    away_xg = _safe_xg(prediction.get("expected_away_goals"))
    if home_xg is None or away_xg is None:
        return None

    penalty_home = penalty_home_probability(prediction)
    pre_home = _safe_probability(prediction.get("prob_home_advance"))
    pre_away = _safe_probability(prediction.get("prob_away_advance"))
    if pre_home is None or pre_away is None or abs((pre_home + pre_away) - 1.0) > 0.02:
        pre_home, pre_away = _computed_prematch_advance(
            home_xg,
            away_xg,
            penalty_home,
            extra_time_goal_factor,
        )

    return {
        "home_xg": home_xg,
        "away_xg": away_xg,
        "penalty_home": penalty_home,
        "prematch_home_advance": pre_home,
        "prematch_away_advance": pre_away,
    }


def _simulate_one(
    *,
    current_home: int,
    current_away: int,
    minute: int,
    home_xg: float,
    away_xg: float,
    penalty_home: float,
    extra_time_goal_factor: float,
    rng: np.random.Generator,
) -> tuple[str, int, int, str]:
    home_goals = current_home
    away_goals = current_away

    if minute <= 90:
        remaining_fraction = max(0.0, 90 - minute) / 90.0
        home_goals += int(rng.poisson(home_xg * remaining_fraction))
        away_goals += int(rng.poisson(away_xg * remaining_fraction))
        if home_goals > away_goals:
            return "HOME", home_goals, away_goals, "normal_time"
        if away_goals > home_goals:
            return "AWAY", home_goals, away_goals, "normal_time"

        home_goals += int(rng.poisson(home_xg * extra_time_goal_factor))
        away_goals += int(rng.poisson(away_xg * extra_time_goal_factor))
        if home_goals > away_goals:
            return "HOME", home_goals, away_goals, "extra_time"
        if away_goals > home_goals:
            return "AWAY", home_goals, away_goals, "extra_time"

    elif minute < 120:
        remaining_extra = max(0.0, 120 - minute) / 30.0
        home_goals += int(
            rng.poisson(home_xg * extra_time_goal_factor * remaining_extra)
        )
        away_goals += int(
            rng.poisson(away_xg * extra_time_goal_factor * remaining_extra)
        )
        if home_goals > away_goals:
            return "HOME", home_goals, away_goals, "extra_time"
        if away_goals > home_goals:
            return "AWAY", home_goals, away_goals, "extra_time"
    else:
        if home_goals > away_goals:
            return "HOME", home_goals, away_goals, "extra_time"
        if away_goals > home_goals:
            return "AWAY", home_goals, away_goals, "extra_time"

    if rng.random() < penalty_home:
        return "HOME", home_goals, away_goals, "penalties"
    return "AWAY", home_goals, away_goals, "penalties"


def _project_match(
    match: pd.Series,
    prediction: pd.Series,
    n_simulations: int,
    random_seed: int,
    extra_time_goal_factor: float,
) -> dict[str, Any] | None:
    inputs = _prediction_inputs(prediction, extra_time_goal_factor)
    if inputs is None:
        return None

    match_id = int(match.get("match_id"))
    current_home = _score_value(match, "home")
    current_away = _score_value(match, "away")
    minute_detail = _resolve_minute_detail(match, allow_extra_time=True)
    minute = minute_detail.minute
    rng = np.random.default_rng(random_seed + match_id)

    advances = Counter()
    scorelines: Counter[tuple[int, int]] = Counter()
    methods = Counter()
    for _ in range(n_simulations):
        winner, home_goals, away_goals, method = _simulate_one(
            current_home=current_home,
            current_away=current_away,
            minute=minute,
            home_xg=inputs["home_xg"],
            away_xg=inputs["away_xg"],
            penalty_home=inputs["penalty_home"],
            extra_time_goal_factor=extra_time_goal_factor,
            rng=rng,
        )
        advances[winner] += 1
        scorelines[(home_goals, away_goals)] += 1
        methods[method] += 1

    likely_scorelines = [
        {
            "score": f"{home}-{away}",
            "probability": count / n_simulations,
        }
        for (home, away), count in scorelines.most_common(5)
    ]
    method_probabilities = {
        "normal_time": methods["normal_time"] / n_simulations,
        "extra_time": methods["extra_time"] / n_simulations,
        "penalties": methods["penalties"] / n_simulations,
    }
    return {
        "match_id": match_id,
        "stage": clean_text(match.get("stage")),
        "home_team": clean_text(match.get("home_team")),
        "away_team": clean_text(match.get("away_team")),
        "current_score": f"{current_home}-{current_away}",
        "minute": minute,
        "minute_source": minute_detail.source,
        "raw_status": minute_detail.raw_status,
        "kickoff_utc": minute_detail.kickoff_utc,
        "expected_home_goals": inputs["home_xg"],
        "expected_away_goals": inputs["away_xg"],
        "home_advance_probability": advances["HOME"] / n_simulations,
        "away_advance_probability": advances["AWAY"] / n_simulations,
        "prematch_home_advance_probability": inputs["prematch_home_advance"],
        "prematch_away_advance_probability": inputs["prematch_away_advance"],
        "penalty_home_probability": inputs["penalty_home"],
        "likely_final_scorelines": likely_scorelines,
        "method_probabilities": method_probabilities,
        "method_note": (
            "Current score and minute are fixed. Remaining normal time is simulated "
            "from the saved pre-match expected goals; tied knockouts then go through "
            "extra time and an Elo-bounded penalty model."
        ),
    }


def live_knockout_matches(matches: pd.DataFrame) -> pd.DataFrame:
    if matches.empty or "status" not in matches.columns or "stage" not in matches.columns:
        return pd.DataFrame()
    mask = matches.apply(is_live_knockout_match, axis=1)
    return matches.loc[mask].copy()


def run_live_knockout_projection(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    match_id: int | None = None,
    n_simulations: int = 3000,
    random_seed: int = 2026,
    extra_time_goal_factor: float = EXTRA_TIME_GOAL_FACTOR,
) -> dict[str, Any]:
    if n_simulations < 100:
        raise ValueError("n_simulations must be at least 100.")

    live_matches = live_knockout_matches(matches)
    if live_matches.empty or "match_id" not in live_matches.columns:
        return {
            "available": False,
            "reason": "No knockout match is currently in play.",
        }
    if match_id is not None:
        live_matches = live_matches[
            pd.to_numeric(live_matches["match_id"], errors="coerce") == int(match_id)
        ]
    if live_matches.empty:
        return {
            "available": False,
            "reason": "No knockout match is currently in play.",
        }

    prediction_lookup = _prediction_rows(predictions)
    projected: dict[int, dict[str, Any]] = {}
    skipped = []
    for row in live_matches.itertuples(index=False):
        match = pd.Series(row._asdict())
        current_match_id = int(match.get("match_id"))
        prediction = prediction_lookup.get(current_match_id)
        if prediction is None:
            skipped.append(
                {
                    "match_id": current_match_id,
                    "reason": "missing_pre_match_prediction",
                }
            )
            continue
        projection = _project_match(
            match,
            prediction,
            n_simulations,
            random_seed,
            extra_time_goal_factor,
        )
        if projection is None:
            skipped.append(
                {
                    "match_id": current_match_id,
                    "reason": "missing_expected_goals",
                }
            )
            continue
        projected[current_match_id] = projection

    if not projected:
        return {
            "available": False,
            "reason": "No saved pre-match knockout prediction is available for the live match.",
            "skipped": skipped,
        }

    return {
        "available": True,
        "n_simulations": n_simulations,
        "matches": projected,
        "skipped": skipped,
        "method_note": (
            "Live knockout advancement is simulated separately from group-stage "
            "qualification. It uses saved xG, current score, minute, extra time "
            "and an Elo-bounded penalty model."
        ),
    }


def next_stage_probability_column(stage) -> str | None:
    key = clean_text(stage).upper()
    if key in {"LAST_32", "ROUND_OF_32", "R32"}:
        return "prob_reach_round_16"
    if key in {"LAST_16", "ROUND_OF_16", "R16"}:
        return "prob_reach_quarter_final"
    if key in {"QUARTER_FINALS", "QUARTER_FINAL", "QF"}:
        return "prob_reach_semi_final"
    if key in {"SEMI_FINALS", "SEMI_FINAL", "SF"}:
        return "prob_reach_final"
    if key == "FINAL":
        return "prob_champion"
    return None
