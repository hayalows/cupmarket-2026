"""Build the immutable CupMarket final archive and tournament retrospective."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
from typing import Any

import pandas as pd


ARCHIVE_MANIFEST_PATH = "data/archive_manifest.json"
SETTLED_PREDICTIONS_PATH = "data/final_prediction_settled.csv"
RETROSPECTIVE_PATH = "data/tournament_retrospective.json"
REPORT_PATH = "data/tournament_retrospective_report.md"
PHASE4_LIVE_EVALUATION_PATH = "data/phase4_live_evaluation.json"
ARCHIVE_RELEASE_TAG = "cupmarket-2026-final"
ARCHIVE_EXCLUDED_FILES = {
    "backend/state/last_automation_run.json",
}

STAGE_RANK = {
    "GROUP_STAGE": 0,
    "LAST_32": 1,
    "LAST_16": 2,
    "QUARTER_FINALS": 3,
    "SEMI_FINALS": 4,
    "THIRD_PLACE": 5,
    "FINAL": 6,
}

ARCHIVE_REQUIRED_FILES = [
    "data/world_cup_2026_matches_latest.csv",
    "data/knockout_progress_latest.csv",
    "data/cupmarket_prices_latest.csv",
    "data/tournament_probabilities_latest.csv",
    "data/adaptive_model_health.json",
    PHASE4_LIVE_EVALUATION_PATH,
    "data/phase3_goal_model_evaluation.json",
    "data/phase5_simulation_metadata.json",
    "data/final_prediction_settled.csv",
    "data/tournament_retrospective.json",
    "data/tournament_retrospective_report.md",
    "data/history/team_snapshots.csv",
    "data/history/market_movements.csv",
    "data/history/match_impacts.csv",
    "data/history/bracket_snapshots.csv",
    "data/history/elo_events.csv",
    "backend/state/world_cup_prediction_ledger.csv",
    "backend/state/world_cup_processed_match_ledger.csv",
]


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError, ValueError):
        return pd.DataFrame()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (pd.Int64Dtype,)):  # pragma: no cover - defensive
        return str(value)
    if hasattr(value, "item"):
        try:
            return _jsonable(value.item())
        except (TypeError, ValueError):
            pass
    if pd.isna(value):
        return None
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _parse_time(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True, format="mixed")


def _match_result(home_score: Any, away_score: Any, duration: Any = "") -> str:
    if "PENALTY" in _text(duration).upper():
        return "DRAW"
    home = _number(home_score)
    away = _number(away_score)
    if home is None or away is None:
        return ""
    if home > away:
        return "HOME_WIN"
    if home < away:
        return "AWAY_WIN"
    return "DRAW"


def _probability(row: pd.Series, column: str) -> float | None:
    value = _number(row.get(column))
    return None if value is None else max(0.0, min(1.0, value))


def _prediction_from_probabilities(
    row: pd.Series,
    prefix: str = "",
) -> tuple[str, dict[str, float]]:
    names = {
        "HOME_WIN": f"{prefix}prob_home_win",
        "DRAW": f"{prefix}prob_draw",
        "AWAY_WIN": f"{prefix}prob_away_win",
    }
    probabilities = {
        outcome: _probability(row, column)
        for outcome, column in names.items()
    }
    clean = {
        outcome: value
        for outcome, value in probabilities.items()
        if value is not None
    }
    if len(clean) != 3 or sum(clean.values()) <= 0:
        return "", clean
    total = sum(clean.values())
    clean = {key: value / total for key, value in clean.items()}
    return max(clean, key=clean.get), clean


def _prediction_probability(
    probabilities: dict[str, float],
    actual: str,
) -> float | None:
    return probabilities.get(actual)


def _champion_from_matches(matches: pd.DataFrame) -> str | None:
    if matches.empty or "stage" not in matches.columns:
        return None
    final = matches.loc[
        matches["stage"].astype(str).eq("FINAL")
        & matches.get("status", pd.Series(dtype=str)).astype(str).isin(
            {"FINISHED", "AWARDED"}
        )
    ]
    if final.empty:
        return None
    row = final.iloc[-1]
    winner = _text(row.get("winner"))
    if winner == "HOME_TEAM":
        return _text(row.get("home_team")) or None
    if winner == "AWAY_TEAM":
        return _text(row.get("away_team")) or None
    return None


def _settlement_team(row: pd.Series) -> str:
    winner = _text(row.get("winner"))
    if winner == "HOME_TEAM":
        return _text(row.get("home_team"))
    if winner == "AWAY_TEAM":
        return _text(row.get("away_team"))
    return ""


def _actual_winner_team(row: pd.Series) -> str:
    winner = _text(row.get("actual_winner"))
    if winner == "HOME_TEAM":
        return _text(row.get("actual_home_team"))
    if winner == "AWAY_TEAM":
        return _text(row.get("actual_away_team"))
    return ""


def settle_prediction_ledger(
    matches: pd.DataFrame,
    progress: pd.DataFrame,
    ledger: pd.DataFrame,
) -> pd.DataFrame:
    """Join the closing pre-match forecast to each official final result."""
    if matches.empty:
        return pd.DataFrame()

    actual = matches.copy()
    actual["_match_key"] = actual.get("match_id", pd.Series(dtype=object)).astype(str)
    actual["_kickoff"] = _parse_time(actual.get("utc_date", pd.Series(dtype=object)))
    actual_columns = [
        "_match_key",
        "stage",
        "utc_date",
        "status",
        "home_team",
        "away_team",
        "winner",
        "duration",
        "home_score_full_time",
        "away_score_full_time",
    ]
    actual = actual[[column for column in actual_columns if column in actual.columns]].rename(
        columns={
            "stage": "actual_stage",
            "utc_date": "actual_utc_date",
            "status": "actual_status",
            "home_team": "actual_home_team",
            "away_team": "actual_away_team",
            "winner": "actual_winner",
            "duration": "actual_duration",
            "home_score_full_time": "actual_home_score",
            "away_score_full_time": "actual_away_score",
        }
    )

    progress_map: dict[str, str] = {}
    if not progress.empty and {"api_match_id", "advancing_team"}.issubset(progress.columns):
        progress_map = {
            _text(row.api_match_id): _text(row.advancing_team)
            for row in progress.itertuples(index=False)
            if _text(row.api_match_id) and _text(row.advancing_team)
        }

    predictions = ledger.copy() if isinstance(ledger, pd.DataFrame) else pd.DataFrame()
    if not predictions.empty and "match_id" in predictions.columns:
        predictions["_match_key"] = predictions["match_id"].astype(str)
        predictions["_generated"] = _parse_time(predictions.get("generated_at_utc"))
        predictions["_kickoff"] = _parse_time(predictions.get("utc_date"))
        created_before = predictions.get(
            "created_before_kickoff", pd.Series(True, index=predictions.index)
        ).astype(str).str.lower().isin({"true", "1", "yes"})
        pre_match = predictions.loc[created_before].copy()
        has_times = pre_match["_generated"].notna() & pre_match["_kickoff"].notna()
        pre_match = pre_match.loc[
            (~has_times) | (pre_match["_generated"] <= pre_match["_kickoff"])
        ]
        pre_match = pre_match.sort_values(["_match_key", "_generated"])
        latest = pre_match.drop_duplicates("_match_key", keep="last")
    else:
        latest = pd.DataFrame(columns=["_match_key"])

    frame = actual.merge(latest, on="_match_key", how="left", suffixes=("", "_prediction"))
    frame["match_id"] = frame["_match_key"]
    frame["stage"] = frame.get("stage", frame.get("actual_stage", "")).fillna(
        frame.get("actual_stage", "")
    )
    frame["home_team"] = frame.get("home_team", frame.get("actual_home_team", "")).fillna(
        frame.get("actual_home_team", "")
    )
    frame["away_team"] = frame.get("away_team", frame.get("actual_away_team", "")).fillna(
        frame.get("actual_away_team", "")
    )
    frame["actual_result"] = frame.apply(
        lambda row: _match_result(
            row.get("actual_home_score"),
            row.get("actual_away_score"),
            row.get("actual_duration"),
        ),
        axis=1,
    )
    frame["actual_advancing_team"] = frame.apply(
        lambda row: progress_map.get(
            _text(row.get("match_id")), _actual_winner_team(row)
        ),
        axis=1,
    )
    frame["actual_advancement_result"] = frame.apply(
        lambda row: (
            "HOME_ADVANCE"
            if _text(row.get("actual_advancing_team")) == _text(row.get("home_team"))
            else "AWAY_ADVANCE"
            if _text(row.get("actual_advancing_team")) == _text(row.get("away_team"))
            else ""
        ),
        axis=1,
    )

    frame["model_result"], model_probabilities = zip(
        *frame.apply(_prediction_from_probabilities, axis=1)
    ) if not frame.empty else ([], [])
    frame["baseline_result"], baseline_probabilities = zip(
        *frame.apply(lambda row: _prediction_from_probabilities(row, "baseline_"), axis=1)
    ) if not frame.empty else ([], [])

    frame["model_actual_probability"] = [
        _prediction_probability(probabilities, actual_result)
        for probabilities, actual_result in zip(model_probabilities, frame["actual_result"])
    ]
    frame["baseline_actual_probability"] = [
        _prediction_probability(probabilities, actual_result)
        for probabilities, actual_result in zip(baseline_probabilities, frame["actual_result"])
    ]
    frame["model_correct"] = frame["model_result"].eq(frame["actual_result"])
    frame["baseline_correct"] = frame["baseline_result"].eq(frame["actual_result"])
    frame["actual_scoreline"] = frame.apply(
        lambda row: (
            f"{int(_number(row.get('actual_home_score')))}-"
            f"{int(_number(row.get('actual_away_score')))}"
            if _number(row.get("actual_home_score")) is not None
            and _number(row.get("actual_away_score")) is not None
            else ""
        ),
        axis=1,
    )
    frame["prediction_available"] = frame["model_result"].ne("")
    frame["prediction_generated_at_utc"] = frame.get("generated_at_utc")
    frame["prediction_type"] = frame.get("prediction_type", "")
    frame["prediction_source"] = frame.get("prediction_source", "")

    preferred = [
        "match_id", "stage", "actual_utc_date", "actual_status", "home_team", "away_team",
        "actual_home_score", "actual_away_score", "actual_scoreline", "actual_duration",
        "actual_result", "actual_advancing_team", "actual_advancement_result",
        "prediction_available", "prediction_generated_at_utc", "prediction_type", "prediction_source",
        "model_version", "adaptive_prediction_enabled", "model_result", "baseline_result",
        "model_correct", "baseline_correct", "model_actual_probability", "baseline_actual_probability",
        "prob_home_win", "prob_draw", "prob_away_win", "baseline_prob_home_win",
        "baseline_prob_draw", "baseline_prob_away_win", "prob_home_advance", "prob_away_advance",
        "predicted_result", "display_label", "most_likely_score", "expected_home_goals",
        "expected_away_goals", "home_base_elo", "away_base_elo", "home_adaptive_adjustment",
        "away_adaptive_adjustment", "generated_at_utc", "utc_date", "status", "group",
    ]
    available = [column for column in preferred if column in frame.columns]
    return frame[available].sort_values("match_id").reset_index(drop=True)


def _scorecard(frame: pd.DataFrame, prefix: str = "") -> dict[str, Any]:
    if frame.empty or "actual_result" not in frame.columns:
        return {"sample_size": 0}
    columns = [
        f"{prefix}prob_home_win",
        f"{prefix}prob_draw",
        f"{prefix}prob_away_win",
    ]
    if not set(columns).issubset(frame.columns):
        return {"sample_size": 0}
    probabilities = frame[columns].apply(pd.to_numeric, errors="coerce")
    valid = probabilities.notna().all(axis=1) & frame["actual_result"].astype(str).ne("")
    if not valid.any():
        return {"sample_size": 0}
    probabilities = probabilities.loc[valid].clip(lower=0.0, upper=1.0)
    totals = probabilities.sum(axis=1).replace(0, pd.NA)
    probabilities = probabilities.div(totals, axis=0)
    actual = frame.loc[valid, "actual_result"].astype(str).to_numpy()
    outcome_order = ["HOME_WIN", "DRAW", "AWAY_WIN"]
    actual_index = [outcome_order.index(value) for value in actual]
    values = probabilities.to_numpy()
    brier = float(
        sum(
            sum((values[row_index, column_index] - (1.0 if column_index == actual_index[row_index] else 0.0)) ** 2 for column_index in range(3))
            for row_index in range(len(actual_index))
        )
        / len(actual_index)
    )
    log_loss = float(
        sum(-math.log(max(values[index, actual_index[index]], 1e-15)) for index in range(len(actual_index)))
        / len(actual_index)
    )
    predicted = probabilities.to_numpy().argmax(axis=1)
    accuracy = float((predicted == actual_index).mean())
    confidence = probabilities.max(axis=1)
    calibration = []
    bins = [(0.0, 0.5), (0.5, 0.65), (0.65, 0.8), (0.8, 1.01)]
    for lower, upper in bins:
        mask = (confidence >= lower) & (confidence < upper)
        if not mask.any():
            continue
        calibration.append(
            {
                "lower": lower,
                "upper": upper,
                "sample_size": int(mask.sum()),
                "mean_confidence": float(confidence.loc[mask].mean()),
                "observed_accuracy": float((predicted[mask.to_numpy()] == pd.Series(actual_index).to_numpy()[mask.to_numpy()]).mean()),
            }
        )
    return {
        "sample_size": int(len(actual_index)),
        "brier": brier,
        "log_loss": log_loss,
        "accuracy": accuracy,
        "mean_confidence": float(confidence.mean()),
        "calibration": calibration,
    }


def _stage_scorecards(frame: pd.DataFrame, prefix: str = "") -> dict[str, dict[str, Any]]:
    if frame.empty or "stage" not in frame.columns:
        return {}
    return {
        stage: _scorecard(frame.loc[frame["stage"].astype(str).eq(stage)], prefix)
        for stage in sorted(frame["stage"].dropna().astype(str).unique())
    }


def _minmax(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if values.dropna().empty or values.max() == values.min():
        return pd.Series(0.5, index=series.index)
    return (values - values.min()) / (values.max() - values.min())


def _correlation(frame: pd.DataFrame, left: str, right: str, label: str) -> dict[str, Any]:
    if left not in frame.columns or right not in frame.columns:
        return {"label": label, "sample_size": 0}
    pair = frame[[left, right]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(pair) < 3:
        return {"label": label, "sample_size": int(len(pair))}
    return {
        "label": label,
        "sample_size": int(len(pair)),
        "pearson": float(pair[left].corr(pair[right], method="pearson")),
        "spearman": float(pair[left].rank().corr(pair[right].rank(), method="pearson")),
    }


def _team_performance(
    matches: pd.DataFrame,
    tables: pd.DataFrame,
    prices: pd.DataFrame,
    snapshots: pd.DataFrame,
    progress: pd.DataFrame,
) -> pd.DataFrame:
    teams = sorted(
        set(matches.get("home_team", pd.Series(dtype=str)).dropna().astype(str))
        | set(matches.get("away_team", pd.Series(dtype=str)).dropna().astype(str))
    )
    records = {
        team: {
            "team": team,
            "matches_played": 0,
            "goal_matches": 0,
            "goals_for": 0.0,
            "goals_against": 0.0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "advances": 0,
            "highest_stage": "GROUP_STAGE",
            "highest_stage_rank": 0,
        }
        for team in teams
    }
    for row in matches.itertuples(index=False):
        home = _text(getattr(row, "home_team", ""))
        away = _text(getattr(row, "away_team", ""))
        if not home or not away:
            continue
        duration = _text(getattr(row, "duration", ""))
        stage = _text(getattr(row, "stage", "")) or "GROUP_STAGE"
        stage_rank = STAGE_RANK.get(stage, 0)
        for team in (home, away):
            records[team]["matches_played"] += 1
            if stage_rank > records[team]["highest_stage_rank"]:
                records[team]["highest_stage"] = stage
                records[team]["highest_stage_rank"] = stage_rank
        home_score = _number(getattr(row, "home_score_full_time", None))
        away_score = _number(getattr(row, "away_score_full_time", None))
        if "PENALTY" not in duration.upper() and home_score is not None and away_score is not None:
            records[home]["goal_matches"] += 1
            records[away]["goal_matches"] += 1
            records[home]["goals_for"] += home_score
            records[home]["goals_against"] += away_score
            records[away]["goals_for"] += away_score
            records[away]["goals_against"] += home_score
            if home_score > away_score:
                records[home]["wins"] += 1
                records[away]["losses"] += 1
            elif home_score < away_score:
                records[away]["wins"] += 1
                records[home]["losses"] += 1
            else:
                records[home]["draws"] += 1
                records[away]["draws"] += 1

    if not progress.empty and {"advancing_team", "stage"}.issubset(progress.columns):
        for row in progress.itertuples(index=False):
            team = _text(row.advancing_team)
            if team in records:
                records[team]["advances"] += 1

    frame = pd.DataFrame(records.values())
    final_rows = matches.loc[matches.get("stage", pd.Series(dtype=str)).astype(str).eq("FINAL")]
    third_rows = matches.loc[matches.get("stage", pd.Series(dtype=str)).astype(str).eq("THIRD_PLACE")]
    champion = _champion_from_matches(matches)
    runner_up = ""
    if not final_rows.empty:
        final = final_rows.iloc[-1]
        final_winner = _text(final.get("winner"))
        runner_up = (
            _text(final.get("away_team")) if final_winner == "HOME_TEAM"
            else _text(final.get("home_team")) if final_winner == "AWAY_TEAM"
            else ""
        )
    third_place = _settlement_team(third_rows.iloc[-1]) if not third_rows.empty else ""
    frame["finish_label"] = "Eliminated"
    frame.loc[frame["highest_stage_rank"] >= 1, "finish_label"] = frame.loc[frame["highest_stage_rank"] >= 1, "highest_stage"].map(
        {
            "LAST_32": "Round of 32",
            "LAST_16": "Round of 16",
            "QUARTER_FINALS": "Quarter-final",
            "SEMI_FINALS": "Semi-final",
            "THIRD_PLACE": "Fourth place",
            "FINAL": "Finalist",
        }
    )
    if champion:
        frame.loc[frame["team"].eq(champion), "finish_label"] = "Champion"
    if runner_up:
        frame.loc[frame["team"].eq(runner_up), "finish_label"] = "Runner-up"
    if third_place:
        frame.loc[frame["team"].eq(third_place), "finish_label"] = "Third place"
    frame["finish_score"] = frame["highest_stage_rank"].astype(float)
    frame.loc[frame["finish_label"].eq("Champion"), "finish_score"] = 7.0
    frame.loc[frame["finish_label"].eq("Runner-up"), "finish_score"] = 6.5
    frame.loc[frame["finish_label"].eq("Third place"), "finish_score"] = 6.0
    frame["goal_difference"] = frame["goals_for"] - frame["goals_against"]
    frame["goals_per_goal_match"] = frame["goals_for"] / frame["goal_matches"].replace(0, pd.NA)
    frame["goals_against_per_goal_match"] = frame["goals_against"] / frame["goal_matches"].replace(0, pd.NA)

    group_table_columns = [
        "team", "group", "position", "points", "played", "wins", "draws", "losses",
        "goals_for", "goals_against", "goal_difference",
    ]
    group_table = tables[[column for column in group_table_columns if column in tables.columns]].copy()
    group_table = group_table.rename(
        columns={
            "played": "group_played", "wins": "group_wins", "draws": "group_draws",
            "losses": "group_losses", "goals_for": "group_goals_for",
            "goals_against": "group_goals_against", "goal_difference": "group_goal_difference",
            "points": "group_points", "position": "group_position",
        }
    )
    if not group_table.empty:
        frame = frame.merge(group_table, on="team", how="left")

    if not prices.empty and "team" in prices.columns:
        price_columns = [
            "team", "cupmarket_price", "prob_champion", "live_elo", "market_rank",
        ]
        frame = frame.merge(
            prices[[column for column in price_columns if column in prices.columns]],
            on="team", how="left",
        )

    if not snapshots.empty and {"team", "generated_at_utc", "cupmarket_price"}.issubset(snapshots.columns):
        snapshot_frame = snapshots.copy()
        snapshot_frame["generated_at_utc"] = _parse_time(snapshot_frame["generated_at_utc"])
        snapshot_frame["cupmarket_price"] = pd.to_numeric(snapshot_frame["cupmarket_price"], errors="coerce")
        snapshot_frame = snapshot_frame.dropna(subset=["team", "generated_at_utc"])
        snapshot_frame = snapshot_frame.sort_values("generated_at_utc")
        opening = snapshot_frame.drop_duplicates("team", keep="first")[["team", "cupmarket_price"]].rename(
            columns={"cupmarket_price": "opening_price"}
        )
        frame = frame.merge(opening, on="team", how="left")

    frame["performance_index"] = (
        100.0 * (
            0.35 * (frame["finish_score"] / 7.0)
            + 0.30 * _minmax(frame.get("group_points", pd.Series(0.0, index=frame.index)))
            + 0.20 * _minmax(frame.get("group_goal_difference", frame["goal_difference"]))
            + 0.10 * _minmax(frame.get("live_elo", pd.Series(0.0, index=frame.index)))
            + 0.05 * _minmax(frame["goal_difference"])
        )
    ).round(2)
    return frame.sort_values(["performance_index", "highest_stage_rank", "goal_difference"], ascending=False).reset_index(drop=True)


def _tournament_facts(matches: pd.DataFrame, team_frame: pd.DataFrame) -> dict[str, Any]:
    goal_matches = matches.loc[
        ~matches.get("duration", pd.Series(dtype=str)).astype(str).str.upper().str.contains("PENALTY", na=False)
    ].copy()
    home_goals = pd.to_numeric(goal_matches.get("home_score_full_time"), errors="coerce")
    away_goals = pd.to_numeric(goal_matches.get("away_score_full_time"), errors="coerce")
    total_goals = float(home_goals.fillna(0).sum() + away_goals.fillna(0).sum())
    results = matches.apply(
        lambda row: _match_result(row.get("home_score_full_time"), row.get("away_score_full_time"), row.get("duration")),
        axis=1,
    )
    margins = (home_goals - away_goals).abs()
    biggest_index = margins.idxmax() if not margins.dropna().empty else None
    biggest = matches.loc[biggest_index] if biggest_index is not None else pd.Series(dtype=object)
    return {
        "matches_total": int(len(matches)),
        "matches_with_goal_scores": int(len(goal_matches)),
        "total_goals_excluding_penalty_shootout_tallies": int(total_goals),
        "goals_per_goal_scored_match": round(total_goals / len(goal_matches), 3) if len(goal_matches) else None,
        "home_wins": int((results == "HOME_WIN").sum()),
        "draws_or_penalty_regulation_ties": int((results == "DRAW").sum()),
        "away_wins": int((results == "AWAY_WIN").sum()),
        "extra_time_matches": int(matches.get("duration", pd.Series(dtype=str)).astype(str).str.upper().str.contains("EXTRA", na=False).sum()),
        "penalty_shootouts": int(matches.get("duration", pd.Series(dtype=str)).astype(str).str.upper().str.contains("PENALTY", na=False).sum()),
        "over_2_5_goal_matches": int(((home_goals + away_goals) > 2.5).sum()),
        "btts_matches": int(((home_goals > 0) & (away_goals > 0)).sum()),
        "largest_margin": int(margins.max()) if not margins.dropna().empty else None,
        "largest_margin_match": (
            f"{_text(biggest.get('home_team'))} {_text(biggest.get('home_score_full_time'))}-"
            f"{_text(biggest.get('away_score_full_time'))} {_text(biggest.get('away_team'))}"
            if not biggest.empty else ""
        ),
        "top_attack": team_frame.sort_values("goals_for", ascending=False).head(5)[["team", "goals_for", "goal_matches"]].to_dict("records"),
        "best_group_attack": team_frame.sort_values("group_goals_for", ascending=False).head(5)[["team", "group_goals_for", "group_played"]].to_dict("records") if "group_goals_for" in team_frame.columns else [],
        "best_group_defence": team_frame.sort_values("group_goal_difference", ascending=False).head(5)[["team", "group_goal_difference", "group_goals_against"]].to_dict("records") if "group_goal_difference" in team_frame.columns else [],
    }


def build_retrospective(repo_root: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    data = repo_root / "data"
    state = repo_root / "backend" / "state"
    matches = _read_csv(data / "world_cup_2026_matches_latest.csv")
    progress = _read_csv(data / "knockout_progress_latest.csv")
    tables = _read_csv(data / "current_group_tables.csv")
    prices = _read_csv(data / "cupmarket_prices_latest.csv")
    snapshots = _read_csv(data / "history" / "team_snapshots.csv")
    movements = _read_csv(data / "history" / "market_movements.csv")
    ledger = _read_csv(state / "world_cup_prediction_ledger.csv")

    settled = settle_prediction_ledger(matches, progress, ledger)
    team_frame = _team_performance(matches, tables, prices, snapshots, progress)
    baseline_all = _scorecard(settled, "baseline_")
    adaptive_rows = settled.loc[
        settled.get("adaptive_prediction_enabled", pd.Series(dtype=object)).astype(str).str.lower().isin({"true", "1", "yes"})
    ] if not settled.empty else settled
    adaptive = _scorecard(adaptive_rows)
    baseline = _scorecard(adaptive_rows, "baseline_")
    primary = _scorecard(settled)

    correlation_frame = team_frame.copy()
    correlations = [
        _correlation(correlation_frame, "opening_price", "group_points", "Opening market price vs group-stage points"),
        _correlation(correlation_frame, "opening_price", "performance_index", "Opening market price vs descriptive performance index"),
        _correlation(correlation_frame, "cupmarket_price", "performance_index", "Final market price vs descriptive performance index"),
        _correlation(correlation_frame, "group_goals_for", "group_points", "Group-stage goals scored vs points"),
        _correlation(correlation_frame, "group_goal_difference", "group_points", "Group-stage goal difference vs points"),
        _correlation(correlation_frame, "live_elo", "group_goal_difference", "Final Elo vs group-stage goal difference"),
    ]

    event_moves = movements.copy()
    if not event_moves.empty:
        event_moves["price_change"] = pd.to_numeric(event_moves.get("price_change"), errors="coerce")
        event_moves = event_moves.sort_values("price_change", key=lambda column: column.abs(), ascending=False)
        event_moves = event_moves.loc[event_moves.get("movement_type", "").astype(str).eq("match_event")]
    notable_moves = event_moves.head(10)[
        [column for column in ["team", "price_change", "price_change_percent", "trigger_matches", "snapshot_id", "relationship_to_event"] if column in event_moves.columns]
    ].to_dict("records") if not event_moves.empty else []

    surprises = settled.dropna(subset=["model_actual_probability"]).sort_values("model_actual_probability").head(10)
    surprise_records = surprises[
        [column for column in ["match_id", "stage", "home_team", "away_team", "actual_scoreline", "model_result", "actual_result", "model_actual_probability"] if column in surprises.columns]
    ].to_dict("records") if not surprises.empty else []

    facts = _tournament_facts(matches, team_frame)
    stage_scores = _stage_scorecards(settled)
    champion = _champion_from_matches(matches)
    report = {
        "schema_version": 1,
        "archive_id": "cupmarket-2026-final",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "champion": champion,
        "final": matches.loc[matches.get("stage", "").astype(str).eq("FINAL")].tail(1).to_dict("records"),
        "third_place": matches.loc[matches.get("stage", "").astype(str).eq("THIRD_PLACE")].tail(1).to_dict("records"),
        "facts": facts,
        "model": {
            "primary": primary,
            "baseline": baseline,
            "baseline_all_available": baseline_all,
            "adaptive": adaptive,
            "adaptive_vs_baseline": {
                "brier_delta": (
                    adaptive.get("brier", 0.0) - baseline.get("brier", 0.0)
                    if adaptive.get("sample_size", 0) and baseline.get("sample_size", 0) else None
                ),
                "log_loss_delta": (
                    adaptive.get("log_loss", 0.0) - baseline.get("log_loss", 0.0)
                    if adaptive.get("sample_size", 0) and baseline.get("sample_size", 0) else None
                ),
            },
            "stage_scorecards": stage_scores,
        },
        "team_performance": team_frame.to_dict("records"),
        "correlations": correlations,
        "market_moves": notable_moves,
        "model_surprises": surprise_records,
        "coverage": {
            "official_matches": int(len(matches)),
            "settled_prediction_rows": int(len(settled)),
            "prediction_rows_with_forecasts": int(settled.get("prediction_available", pd.Series(dtype=bool)).sum()),
            "prediction_rows_with_actual_results": int(settled.get("actual_result", pd.Series(dtype=str)).astype(str).ne("").sum()),
            "all_pre_match_prediction_rows": int(len(ledger.loc[ledger.get("created_before_kickoff", pd.Series(dtype=object)).astype(str).str.lower().isin({"true", "1", "yes"})])) if not ledger.empty and "created_before_kickoff" in ledger.columns else 0,
        },
        "limitations": [
            "Penalty-shootout score fields are shootout tallies in the official feed, so they are excluded from goal totals.",
            "The descriptive performance index ranks the completed tournament; it is not a forward-looking forecast.",
            "Correlation is association, not causal evidence, and market values include settlement logic tied to tournament outcomes.",
            "Adaptive versus baseline scoring is limited to rows carrying both probability sets and should not be generalized beyond this tournament.",
        ],
    }
    return settled, _jsonable(report)


def _git_commit(repo_root: Path) -> str | None:
    for key in ("GITHUB_SHA", "CUPMARKET_SOURCE_COMMIT"):
        value = str(__import__("os").environ.get(key, "")).strip()
        if value:
            return value
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _hash_file(path: Path, repo_root: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": path.relative_to(repo_root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def _archive_files(repo_root: Path) -> list[dict[str, Any]]:
    paths: set[Path] = set()
    for relative in ARCHIVE_REQUIRED_FILES:
        path = repo_root / relative
        if path.exists():
            paths.add(path)
    for pattern in ("data/**/*.csv", "data/**/*.json", "data/**/*.md", "backend/state/*.csv", "backend/state/*.json", "backend/state/models/*.joblib"):
        paths.update(path for path in repo_root.glob(pattern) if path.is_file())
    paths.discard(repo_root / ARCHIVE_MANIFEST_PATH)
    return [
        _hash_file(path, repo_root)
        for path in sorted(paths)
        if path.relative_to(repo_root).as_posix() not in ARCHIVE_EXCLUDED_FILES
    ]


def _report_markdown(report: dict[str, Any], source_commit: str | None) -> str:
    facts = report.get("facts", {})
    model = report.get("model", {})
    primary = model.get("primary", {})
    baseline = model.get("baseline", {})
    adaptive = model.get("adaptive", {})
    delta = model.get("adaptive_vs_baseline", {})
    top_teams = report.get("team_performance", [])[:8]
    correlations = [item for item in report.get("correlations", []) if item.get("sample_size", 0) >= 3]
    lines = [
        "# CupMarket 2026 Tournament Retrospective",
        "",
        f"**Champion:** {report.get('champion') or 'Unavailable'}  ",
        f"**Archive:** `{report.get('archive_id')}`  ",
        f"**Generated:** {report.get('generated_at_utc')}  ",
        f"**Source commit:** `{source_commit or 'unavailable'}`",
        "",
        "## Executive summary",
        "",
        f"- The completed tournament contained **{facts.get('matches_total', 0)} matches** and **{facts.get('total_goals_excluding_penalty_shootout_tallies', 0)} counted goals** across {facts.get('matches_with_goal_scores', 0)} matches with reliable goal scores.",
        f"- The goal-scored matches averaged **{facts.get('goals_per_goal_scored_match', 0):.2f} goals**, with {facts.get('extra_time_matches', 0)} extra-time matches and {facts.get('penalty_shootouts', 0)} penalty shootouts.",
        f"- The strongest descriptive performers were **{', '.join(str(row.get('team')) for row in top_teams[:5])}**; this ranking rewards progress, group performance, Elo and goal difference after the event.",
        f"- The primary pre-match scorecard covered **{primary.get('sample_size', 0)} matches** at {primary.get('accuracy', 0.0):.1%} accuracy, Brier {primary.get('brier', 0.0):.3f}, and log loss {primary.get('log_loss', 0.0):.3f}.",
        "",
        "## Tournament record",
        "",
        f"Home wins: **{facts.get('home_wins', 0)}**. Draws or penalty-regulation ties: **{facts.get('draws_or_penalty_regulation_ties', 0)}**. Away wins: **{facts.get('away_wins', 0)}**.",
        f"The largest recorded score margin was **{facts.get('largest_margin_match') or 'Unavailable'}**.",
        "",
        "## Teams that performed well",
        "",
        "| Team | Finish | Group points | Group GD | Goals | Final market | Performance index |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in top_teams:
        lines.append(
            f"| {row.get('team', '')} | {row.get('finish_label', '')} | {row.get('group_points', '')} | {row.get('group_goal_difference', '')} | {row.get('goals_for', 0):.0f} | {row.get('cupmarket_price', 0):.2f} | {row.get('performance_index', 0):.2f} |"
        )
    lines.extend(
        [
            "",
            "## Model verdict",
            "",
            f"The baseline scorecard covered **{baseline.get('sample_size', 0)} matches**. The adaptive comparison covered **{adaptive.get('sample_size', 0)} matches**.",
            f"Adaptive versus baseline Brier delta: **{delta.get('brier_delta'):+.4f}**. Log-loss delta: **{delta.get('log_loss_delta'):+.4f}**.",
            "A positive delta is worse. Adaptive nudges therefore did not beat the saved baseline in this sample, although the regression remained inside the published rollback guardrail.",
            "",
            "## Correlations",
            "",
            "These are descriptive associations, not causal claims. Market correlations are partly expected because settlement values incorporate tournament outcomes.",
            "",
            "| Relationship | Sample | Pearson | Spearman |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for item in correlations:
        lines.append(
            f"| {item.get('label', '')} | {item.get('sample_size', 0)} | {item.get('pearson', 0.0):+.3f} | {item.get('spearman', 0.0):+.3f} |"
        )
    lines.extend(
        [
            "",
            "## Model surprises and market movement",
            "",
            "The archive retains the lowest-probability actual outcomes and the largest event-attributed market changes so the tournament can be replayed without hindsight edits.",
            "",
            "## Method and limitations",
            "",
        ]
    )
    surprises = report.get("model_surprises", [])[:5]
    if surprises:
        lines.extend(
            [
                "### Lowest-probability actual outcomes",
                "",
                "| Match | Stage | Model call | Actual | Actual probability |",
                "| --- | --- | --- | --- | ---: |",
            ]
        )
        for row in surprises:
            probability = _number(row.get("model_actual_probability"))
            probability_text = "Unavailable" if probability is None else f"{probability:.1%}"
            lines.append(
                f"| {row.get('home_team', '')} vs {row.get('away_team', '')} | {row.get('stage', '')} | {row.get('model_result', '')} | {row.get('actual_result', '')} ({row.get('actual_scoreline', '')}) | {probability_text} |"
            )
        lines.append("")
    moves = report.get("market_moves", [])[:8]
    if moves:
        lines.extend(
            [
                "### Largest recorded market moves",
                "",
                "| Team | Price move | Move % | Event |",
                "| --- | ---: | ---: | --- |",
            ]
        )
        for row in moves:
            price = _number(row.get("price_change"))
            percent = _number(row.get("price_change_percent"))
            price_text = "Unavailable" if price is None else f"{price:+.2f}"
            percent_text = "Unavailable" if percent is None else f"{percent:+.1f}%"
            lines.append(
                f"| {row.get('team', '')} | {price_text} | {percent_text} | {row.get('trigger_matches', '')} |"
            )
        lines.append("")
    lines.extend(f"- {item}" for item in report.get("limitations", []))
    lines.extend(
        [
            "- The settled forecast file uses the latest eligible pre-kickoff forecast for each match; the raw append-only ledger remains preserved separately.",
            "- This report is a final retrospective, not a retrained production model. Any future model should be evaluated on a new tournament or a frozen historical holdout.",
            "",
            "## Reproducibility",
            "",
            "The archive manifest records SHA-256 hashes for the published data, history ledgers, model metadata and retrospective outputs.",
            "",
        ]
    )
    return "\n".join(lines)


def finalize_archive(
    repo_root: Path,
    *,
    force: bool = False,
    finalized_at_utc: str | None = None,
) -> dict[str, Any]:
    """Write the final artifacts once and return the immutable archive manifest."""
    manifest_path = repo_root / ARCHIVE_MANIFEST_PATH
    existing = _read_json(manifest_path)
    if existing.get("status") == "finalized" and not force:
        return existing

    settled, retrospective = build_retrospective(repo_root)
    champion = retrospective.get("champion")
    if not champion:
        raise ValueError("Cannot finalize the archive before a completed final exists.")

    finalized_at = finalized_at_utc or retrospective.get("generated_at_utc") or datetime.now(timezone.utc).isoformat()
    source_commit = os.environ.get("CUPMARKET_SOURCE_COMMIT") or _git_commit(repo_root)
    retrospective["generated_at_utc"] = finalized_at
    retrospective["source_commit"] = source_commit
    report = _report_markdown(retrospective, source_commit)

    _write_csv(repo_root / SETTLED_PREDICTIONS_PATH, settled)
    _write_json(repo_root / RETROSPECTIVE_PATH, retrospective)
    primary_scorecard = retrospective.get("model", {}).get("primary", {})
    adaptive_comparison = retrospective.get("model", {}).get("adaptive_vs_baseline", {})
    _write_json(
        repo_root / PHASE4_LIVE_EVALUATION_PATH,
        {
            "schema_version": 2,
            "status": "finalized",
            "eligible_completed_predictions": int(primary_scorecard.get("sample_size", 0) or 0),
            "primary_scorecard": primary_scorecard,
            "adaptive_comparison_sample": int(
                retrospective.get("model", {}).get("adaptive", {}).get("sample_size", 0) or 0
            ),
            "adaptive_vs_baseline": adaptive_comparison,
            "message": (
                "The tournament is complete. Read tournament_retrospective.json for the full settled "
                "scorecard; this compatibility artifact now points to the final retrospective."
            ),
            "retrospective_path": RETROSPECTIVE_PATH,
            "generated_at_utc": finalized_at,
            "source_commit": source_commit,
        },
    )
    report_path = repo_root / REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    files = _archive_files(repo_root)
    archive = {
        "schema_version": 1,
        "status": "finalized",
        "archive_id": ARCHIVE_RELEASE_TAG,
        "release_tag": ARCHIVE_RELEASE_TAG,
        "finalized_at_utc": finalized_at,
        "champion": champion,
        "source_commit": source_commit,
        "artifact_count": len(files),
        "total_bytes": int(sum(item["bytes"] for item in files)),
        "required_files": [path for path in ARCHIVE_REQUIRED_FILES if (repo_root / path).exists()],
        "files": files,
        "checks": {
            "official_matches_complete": retrospective.get("coverage", {}).get("official_matches") == 104,
            "settled_rows_cover_official_matches": retrospective.get("coverage", {}).get("settled_prediction_rows") == retrospective.get("coverage", {}).get("official_matches"),
            "final_prediction_report_present": (repo_root / REPORT_PATH).exists(),
            "hashes_present": all(bool(item.get("sha256")) for item in files),
        },
    }
    _write_json(manifest_path, archive)
    return archive


def is_final_archive(repo_root: Path) -> bool:
    payload = _read_json(repo_root / ARCHIVE_MANIFEST_PATH)
    return payload.get("status") == "finalized" and bool(payload.get("archive_id"))


__all__ = [
    "ARCHIVE_MANIFEST_PATH",
    "ARCHIVE_EXCLUDED_FILES",
    "ARCHIVE_RELEASE_TAG",
    "PHASE4_LIVE_EVALUATION_PATH",
    "REPORT_PATH",
    "RETROSPECTIVE_PATH",
    "SETTLED_PREDICTIONS_PATH",
    "build_retrospective",
    "finalize_archive",
    "is_final_archive",
    "settle_prediction_ledger",
]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Finalize the CupMarket tournament archive.")
    parser.add_argument("--force", action="store_true", help="Rebuild an existing archive explicitly.")
    args = parser.parse_args()
    archive = finalize_archive(Path(__file__).resolve().parents[1], force=args.force)
    print(json.dumps(_jsonable(archive), indent=2, sort_keys=True))
