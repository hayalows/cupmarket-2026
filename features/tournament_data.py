from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
STATE_DIR = ROOT / "backend" / "state"
HISTORY_DIR = DATA_DIR / "market_history"


def _version(path: Path) -> int:
    return path.stat().st_mtime_ns if path.exists() else 0


@st.cache_data(show_spinner=False)
def _read_csv(path_text: str, version: int) -> pd.DataFrame:
    path = Path(path_text)
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    for column in [
        "utc_date",
        "generated_at_utc",
        "processed_at_utc",
        "last_updated",
        "prediction_created_at",
    ]:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce", utc=True)
    return frame


def load_csv(path: Path) -> pd.DataFrame:
    return _read_csv(str(path), _version(path))


@st.cache_data(show_spinner=False)
def _history_manifest(directory_text: str, manifest: tuple[tuple[str, int], ...]) -> pd.DataFrame:
    directory = Path(directory_text)
    rows: list[pd.DataFrame] = []
    for filename, _ in manifest:
        path = directory / filename
        frame = pd.read_csv(path)
        timestamp_match = re.search(r"(\d{8}T\d{6}Z)", filename)
        fallback_time = (
            pd.to_datetime(
                timestamp_match.group(1),
                format="%Y%m%dT%H%M%SZ",
                utc=True,
                errors="coerce",
            )
            if timestamp_match
            else pd.NaT
        )
        if "generated_at_utc" not in frame.columns:
            frame["generated_at_utc"] = fallback_time
        frame["generated_at_utc"] = pd.to_datetime(
            frame["generated_at_utc"], errors="coerce", utc=True
        )
        rows.append(frame)
    if not rows:
        return pd.DataFrame()
    history = pd.concat(rows, ignore_index=True, sort=False)
    required = ["team", "cupmarket_price", "generated_at_utc"]
    if not set(required).issubset(history.columns):
        return pd.DataFrame()
    return (
        history.dropna(subset=required)
        .drop_duplicates(["team", "generated_at_utc"], keep="last")
        .sort_values(["generated_at_utc", "team"])
        .reset_index(drop=True)
    )


def load_market_history() -> pd.DataFrame:
    if not HISTORY_DIR.exists():
        return pd.DataFrame()
    manifest = tuple(
        (path.name, path.stat().st_mtime_ns)
        for path in sorted(HISTORY_DIR.glob("cupmarket_prices_*.csv"))
    )
    history = _history_manifest(str(HISTORY_DIR), manifest)
    current = load_csv(DATA_DIR / "cupmarket_prices_latest.csv")
    if current.empty:
        return history
    combined = pd.concat([history, current], ignore_index=True, sort=False)
    return (
        combined.dropna(subset=["team", "cupmarket_price", "generated_at_utc"])
        .drop_duplicates(["team", "generated_at_utc"], keep="last")
        .sort_values(["generated_at_utc", "team"])
        .reset_index(drop=True)
    )


def load_static_data() -> dict[str, pd.DataFrame]:
    return {
        "prices": load_csv(DATA_DIR / "cupmarket_prices_latest.csv"),
        "latest_predictions": load_csv(DATA_DIR / "world_cup_live_predictions_latest.csv"),
        "prediction_ledger": load_csv(STATE_DIR / "world_cup_prediction_ledger.csv"),
        "processed_ledger": load_csv(STATE_DIR / "world_cup_processed_match_ledger.csv"),
        "history": load_market_history(),
    }


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
    if "created_before_kickoff" in rows.columns:
        rows["_before"] = rows["created_before_kickoff"].map(_as_bool)
    else:
        rows["_before"] = False

    true_pre = rows[rows["_before"]].copy()
    if pd.notna(kickoff):
        true_pre = true_pre[
            true_pre["generated_at_utc"].isna()
            | (true_pre["generated_at_utc"] <= kickoff)
        ]
    if not true_pre.empty:
        true_pre = true_pre.sort_values("generated_at_utc")
        return true_pre.iloc[-1], "Saved pre-match forecast"

    retrospective = rows[
        rows.get("prediction_type", pd.Series(index=rows.index, dtype=str))
        .astype(str)
        .str.contains("retrospective", case=False, na=False)
    ]
    if not retrospective.empty:
        retrospective = retrospective.sort_values("generated_at_utc")
        return retrospective.iloc[-1], "Retrospective baseline"

    rows = rows.sort_values("generated_at_utc")
    return rows.iloc[-1], "Latest available model record"


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
    mapping = {
        "HOME_WIN": "prob_home_win",
        "DRAW": "prob_draw",
        "AWAY_WIN": "prob_away_win",
    }
    column = mapping.get(outcome or "")
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
    name = {
        "HOME_WIN": f"{match.get('home_team', 'Home')} win",
        "DRAW": "Draw",
        "AWAY_WIN": f"{match.get('away_team', 'Away')} win",
    }[outcome]
    return f"{name} · {100 * valid[outcome]:.1f}%"


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
        times = (
            history.loc[history["generated_at_utc"] >= processed_at, "generated_at_utc"]
            .dropna()
            .sort_values()
            .unique()
        )
        if len(times):
            snapshot_time = pd.Timestamp(times[0])
            if snapshot_time - processed_at <= pd.Timedelta(hours=2):
                snapshot = history[history["generated_at_utc"] == snapshot_time].copy()
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
    return ledger[ledger["processed_at_utc"].dt.floor("s") == latest_second].copy()
