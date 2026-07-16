"""Evaluate the adaptive prediction layer against its saved baseline."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path

import pandas as pd


MIN_COMPARISON_SAMPLE = 20
MAX_BRIER_REGRESSION = 0.015
MAX_LOG_LOSS_REGRESSION = 0.030
OUTCOMES = {
    "HOME_WIN": "prob_home_win",
    "DRAW": "prob_draw",
    "AWAY_WIN": "prob_away_win",
}


def _number(value) -> float | None:
    number = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(number) else float(number)


def _actual_outcome(row: pd.Series) -> str | None:
    home = _number(row.get("home_score_full_time", row.get("home_score")))
    away = _number(row.get("away_score_full_time", row.get("away_score")))
    if home is None or away is None:
        return None
    if home > away:
        return "HOME_WIN"
    if home < away:
        return "AWAY_WIN"
    return "DRAW"


def _pre_match_predictions(prediction_ledger: pd.DataFrame) -> pd.DataFrame:
    required = {"match_id", "generated_at_utc", *OUTCOMES.values()}
    baseline = {f"baseline_{column}" for column in OUTCOMES.values()}
    if prediction_ledger.empty or not (required | baseline).issubset(prediction_ledger.columns):
        return pd.DataFrame()

    rows = prediction_ledger.copy()
    if "created_before_kickoff" in rows.columns:
        created = rows["created_before_kickoff"].astype(str).str.lower().isin(
            {"true", "1", "yes"}
        )
        rows = rows.loc[created].copy()
    if rows.empty:
        return rows
    rows["generated_at_utc"] = pd.to_datetime(
        rows["generated_at_utc"], errors="coerce", utc=True, format="mixed"
    )
    rows = rows.dropna(subset=["match_id", "generated_at_utc"])
    return rows.sort_values("generated_at_utc").drop_duplicates("match_id", keep="first")


def evaluate_adaptive_layer(
    matches: pd.DataFrame,
    prediction_ledger: pd.DataFrame,
) -> dict:
    """Compare saved baseline and adaptive probabilities on finished matches."""
    finished = matches.copy()
    if finished.empty or not {"match_id", "status"}.issubset(finished.columns):
        finished = pd.DataFrame()
    else:
        finished = finished.loc[
            finished["status"].astype(str).isin({"FINISHED", "AWARDED"})
        ].copy()
    predictions = _pre_match_predictions(prediction_ledger)
    if finished.empty or predictions.empty:
        rows = pd.DataFrame()
    else:
        rows = predictions.merge(
            finished[[column for column in [
                "match_id", "home_score_full_time", "away_score_full_time",
                "home_score", "away_score",
            ] if column in finished.columns]],
            on="match_id",
            how="inner",
        )

    adaptive_briers: list[float] = []
    baseline_briers: list[float] = []
    adaptive_log_losses: list[float] = []
    baseline_log_losses: list[float] = []
    for _, row in rows.iterrows():
        actual = _actual_outcome(row)
        if actual is None:
            continue
        adaptive = {name: _number(row.get(column)) for name, column in OUTCOMES.items()}
        baseline = {
            name: _number(row.get(f"baseline_{column}"))
            for name, column in OUTCOMES.items()
        }
        if any(value is None for value in adaptive.values()) or any(
            value is None for value in baseline.values()
        ):
            continue
        adaptive_total = sum(adaptive.values())
        baseline_total = sum(baseline.values())
        if adaptive_total <= 0 or baseline_total <= 0:
            continue
        adaptive = {key: value / adaptive_total for key, value in adaptive.items()}
        baseline = {key: value / baseline_total for key, value in baseline.items()}
        adaptive_briers.append(
            sum((value - (1.0 if key == actual else 0.0)) ** 2 for key, value in adaptive.items())
        )
        baseline_briers.append(
            sum((value - (1.0 if key == actual else 0.0)) ** 2 for key, value in baseline.items())
        )
        adaptive_log_losses.append(-math.log(max(adaptive[actual], 1e-15)))
        baseline_log_losses.append(-math.log(max(baseline[actual], 1e-15)))

    sample_size = len(adaptive_briers)
    result = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "comparison_sample_size": sample_size,
        "minimum_sample_size": MIN_COMPARISON_SAMPLE,
        "thresholds": {
            "max_brier_regression": MAX_BRIER_REGRESSION,
            "max_log_loss_regression": MAX_LOG_LOSS_REGRESSION,
        },
        "baseline": {},
        "adaptive": {},
        "decision": "collecting_evidence",
        "message": "More matched pre-match baseline forecasts are needed before adaptive predictions can be judged.",
    }
    if not sample_size:
        return result

    baseline_brier = float(sum(baseline_briers) / sample_size)
    adaptive_brier = float(sum(adaptive_briers) / sample_size)
    baseline_log_loss = float(sum(baseline_log_losses) / sample_size)
    adaptive_log_loss = float(sum(adaptive_log_losses) / sample_size)
    result["baseline"] = {"brier": baseline_brier, "log_loss": baseline_log_loss}
    result["adaptive"] = {"brier": adaptive_brier, "log_loss": adaptive_log_loss}
    result["delta"] = {
        "brier": adaptive_brier - baseline_brier,
        "log_loss": adaptive_log_loss - baseline_log_loss,
    }
    if sample_size < MIN_COMPARISON_SAMPLE:
        return result
    if (
        result["delta"]["brier"] > MAX_BRIER_REGRESSION
        or result["delta"]["log_loss"] > MAX_LOG_LOSS_REGRESSION
    ):
        result["decision"] = "rollback"
        result["message"] = "Adaptive probabilities underperformed the saved baseline beyond the published guardrail. Future adaptive nudges are disabled until the comparison recovers."
    elif result["delta"]["brier"] <= 0 and result["delta"]["log_loss"] <= 0:
        result["decision"] = "trusted"
        result["message"] = "Adaptive probabilities are matching or improving on the saved baseline in both quality metrics."
    else:
        result["decision"] = "monitor"
        result["message"] = "Adaptive probabilities remain inside the rollback guardrail, but the next completed forecasts should be watched closely."
    return result


def write_adaptive_model_health(
    matches_path: Path,
    prediction_ledger_path: Path,
    output_path: Path,
) -> dict:
    matches = pd.read_csv(matches_path) if matches_path.exists() else pd.DataFrame()
    ledger = (
        pd.read_csv(prediction_ledger_path)
        if prediction_ledger_path.exists()
        else pd.DataFrame()
    )
    payload = evaluate_adaptive_layer(matches, ledger)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(output_path)
    return payload
