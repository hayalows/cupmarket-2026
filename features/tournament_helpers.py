from __future__ import annotations

from typing import Any

import pandas as pd

OFFICIAL_KNOCKOUT_MODEL_VERSION = "phase6_knockout_progression_v1"
OFFICIAL_KNOCKOUT_BRACKET_MODE = "official_api_locked_knockout_progression"


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def reference_prediction(
    prediction_ledger: pd.DataFrame,
    match: pd.Series,
) -> tuple[pd.Series, str]:
    if prediction_ledger.empty or "match_id" not in prediction_ledger.columns:
        return pd.Series(dtype=object), "Unavailable"

    match_id = int(match["match_id"])
    rows = prediction_ledger[
        pd.to_numeric(prediction_ledger["match_id"], errors="coerce") == match_id
    ].copy()
    if rows.empty:
        return pd.Series(dtype=object), "Unavailable"

    rows["generated_at_utc"] = pd.to_datetime(
        rows.get("generated_at_utc"), errors="coerce", utc=True
    )
    kickoff = pd.to_datetime(match.get("utc_date"), errors="coerce", utc=True)
    rows["_before"] = (
        rows["created_before_kickoff"].map(_as_bool)
        if "created_before_kickoff" in rows.columns
        else False
    )

    true_pre = rows[rows["_before"]].copy()
    if pd.notna(kickoff):
        true_pre = true_pre[
            true_pre["generated_at_utc"].isna()
            | (true_pre["generated_at_utc"] <= kickoff)
        ]
    if not true_pre.empty:
        return (
            true_pre.sort_values("generated_at_utc").iloc[-1],
            "Saved pre-match forecast",
        )

    prediction_type = rows.get(
        "prediction_type", pd.Series(index=rows.index, dtype=str)
    )
    retrospective = rows[
        prediction_type.astype(str).str.contains(
            "retrospective", case=False, na=False
        )
    ]
    if not retrospective.empty:
        return (
            retrospective.sort_values("generated_at_utc").iloc[-1],
            "Retrospective baseline",
        )

    return (
        rows.sort_values("generated_at_utc").iloc[-1],
        "Latest available model record",
    )


def actual_outcome(match: pd.Series) -> str | None:
    home = pd.to_numeric(match.get("home_score_full_time"), errors="coerce")
    away = pd.to_numeric(match.get("away_score_full_time"), errors="coerce")
    if pd.isna(home) or pd.isna(away):
        return None
    if home > away:
        return "HOME_WIN"
    if home < away:
        return "AWAY_WIN"
    return "DRAW"


def outcome_probability(prediction: pd.Series, outcome: str | None) -> float | None:
    column = {
        "HOME_WIN": "prob_home_win",
        "DRAW": "prob_draw",
        "AWAY_WIN": "prob_away_win",
    }.get(outcome or "")
    if not column or prediction.empty:
        return None
    value = pd.to_numeric(prediction.get(column), errors="coerce")
    return None if pd.isna(value) else float(value)


def leading_outcome_label(prediction: pd.Series, match: pd.Series) -> str:
    if prediction.empty:
        return "Forecast unavailable"
    values = {
        "HOME_WIN": pd.to_numeric(prediction.get("prob_home_win"), errors="coerce"),
        "DRAW": pd.to_numeric(prediction.get("prob_draw"), errors="coerce"),
        "AWAY_WIN": pd.to_numeric(prediction.get("prob_away_win"), errors="coerce"),
    }
    valid = {key: float(value) for key, value in values.items() if pd.notna(value)}
    if not valid:
        return "Forecast unavailable"
    outcome = max(valid, key=valid.get)
    label = {
        "HOME_WIN": f"{match.get('home_team', 'Home')} win",
        "DRAW": "Draw",
        "AWAY_WIN": f"{match.get('away_team', 'Away')} win",
    }[outcome]
    return f"{label} · {100 * valid[outcome]:.1f}%"


def batch_context_for_match(
    match_id: int,
    processed_ledger: pd.DataFrame,
    history: pd.DataFrame,
) -> dict[str, Any]:
    if processed_ledger.empty or "match_id" not in processed_ledger.columns:
        return {"available": False}

    ledger = processed_ledger.copy()
    ledger["match_id"] = pd.to_numeric(ledger["match_id"], errors="coerce")
    ledger["processed_at_utc"] = pd.to_datetime(
        ledger["processed_at_utc"], errors="coerce", utc=True
    )
    target = ledger[ledger["match_id"] == int(match_id)]
    if target.empty or pd.isna(target.iloc[-1].get("processed_at_utc")):
        return {"available": False}

    processed_at = target.iloc[-1]["processed_at_utc"]
    batch_second = processed_at.floor("s")
    ledger["_batch_second"] = ledger["processed_at_utc"].dt.floor("s")
    batch = ledger[ledger["_batch_second"] == batch_second].copy()

    snapshot_time = pd.NaT
    snapshot = pd.DataFrame()
    if not history.empty and "generated_at_utc" in history.columns:
        candidates = history.loc[history["generated_at_utc"] >= processed_at].copy()
        if not candidates.empty:
            official_mask = pd.Series(False, index=candidates.index)
            if "model_version" in candidates.columns:
                official_mask = official_mask | candidates["model_version"].astype(
                    str
                ).eq(OFFICIAL_KNOCKOUT_MODEL_VERSION)
            if "bracket_mode" in candidates.columns:
                official_mask = official_mask | candidates["bracket_mode"].astype(
                    str
                ).eq(OFFICIAL_KNOCKOUT_BRACKET_MODE)
            official_candidates = candidates.loc[official_mask].copy()
            if not official_candidates.empty:
                candidates = official_candidates
        times = candidates["generated_at_utc"].dropna().sort_values().unique()
        if len(times):
            snapshot_time = pd.Timestamp(times[0])
            if snapshot_time - processed_at <= pd.Timedelta(hours=2):
                snapshot = history[
                    history["generated_at_utc"] == snapshot_time
                ].copy()
            else:
                snapshot_time = pd.NaT

    return {
        "available": True,
        "processed_at_utc": processed_at,
        "batch_matches": batch.drop(columns=["_batch_second"], errors="ignore"),
        "snapshot_time": snapshot_time,
        "snapshot": snapshot,
    }


def latest_update_matches(
    processed_ledger: pd.DataFrame,
    generated_at: pd.Timestamp | None,
) -> pd.DataFrame:
    if processed_ledger.empty:
        return pd.DataFrame()
    ledger = processed_ledger.copy()
    ledger["processed_at_utc"] = pd.to_datetime(
        ledger["processed_at_utc"], errors="coerce", utc=True
    )
    if generated_at is not None and pd.notna(generated_at):
        ledger = ledger[ledger["processed_at_utc"] <= generated_at]
    ledger = ledger.dropna(subset=["processed_at_utc"])
    if ledger.empty:
        return pd.DataFrame()
    latest_second = ledger["processed_at_utc"].max().floor("s")
    return ledger[
        ledger["processed_at_utc"].dt.floor("s") == latest_second
    ].copy()
