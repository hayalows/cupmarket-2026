"""Run bracket locking and knockout-stage processing after the group pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re

import pandas as pd

try:
    from . import (
        bracket_lock_execution,
        history_store,
        knockout_stage,
        market_impact_store,
        update_pipeline,
    )
except ImportError:
    import bracket_lock_execution
    import history_store
    import knockout_stage
    import market_impact_store
    import update_pipeline


STATE_PATH = update_pipeline.STATE_DIR / "knockout_pipeline_state.json"
PROGRESS_PATH = update_pipeline.DATA_DIR / "knockout_progress_latest.csv"
OFFICIAL_KNOCKOUT_MODEL_VERSION = "phase6_knockout_progression_v1"
OFFICIAL_KNOCKOUT_BRACKET_MODE = "official_api_locked_knockout_progression"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv_safely(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.ParserError):
        return pd.DataFrame()


def _is_official_knockout_frame(frame: pd.DataFrame) -> bool:
    if frame.empty:
        return False
    if "model_version" in frame.columns and frame["model_version"].astype(str).eq(
        OFFICIAL_KNOCKOUT_MODEL_VERSION
    ).any():
        return True
    if "bracket_mode" in frame.columns and frame["bracket_mode"].astype(str).eq(
        OFFICIAL_KNOCKOUT_BRACKET_MODE
    ).any():
        return True
    return False


def _history_timestamp(path: Path, frame: pd.DataFrame) -> pd.Timestamp:
    if "generated_at_utc" in frame.columns:
        values = pd.to_datetime(
            frame["generated_at_utc"], errors="coerce", utc=True
        ).dropna()
        if not values.empty:
            return values.max()

    match = re.search(r"(\d{8}T\d{6}Z)", path.name)
    if match:
        return pd.to_datetime(
            match.group(1),
            format="%Y%m%dT%H%M%SZ",
            utc=True,
            errors="coerce",
        )
    return pd.NaT


def _load_previous_official_knockout_prices() -> pd.DataFrame | None:
    """Return the last public knockout price sheet before this settlement run."""
    frames = []
    for path in sorted(update_pipeline.HISTORY_DIR.glob("cupmarket_prices_*.csv")):
        frame = _read_csv_safely(path)
        if not _is_official_knockout_frame(frame):
            continue
        timestamp = _history_timestamp(path, frame)
        if pd.isna(timestamp):
            continue
        frame = frame.copy()
        frame["_publication_time"] = timestamp
        frames.append(frame)

    if frames:
        history = pd.concat(frames, ignore_index=True, sort=False)
        latest_time = history["_publication_time"].max()
        latest = history.loc[history["_publication_time"].eq(latest_time)].copy()
        return latest.drop(columns=["_publication_time"], errors="ignore")

    current = _read_csv_safely(update_pipeline.PRICES_OUTPUT_PATH)
    if _is_official_knockout_frame(current):
        return current
    if current.empty:
        return None
    return current


def _archive_history_safely() -> None:
    for label, operation in (
        ("History archive", history_store.archive_latest_outputs),
        ("Market impact archive", market_impact_store.archive_market_movements),
    ):
        try:
            result = operation(update_pipeline.REPO_ROOT)
        except Exception as error:
            print(f"{label} warning: {type(error).__name__}: {error}")
        else:
            print(f"{label}:", json.dumps(result, sort_keys=True))


def run() -> dict:
    started_at = datetime.now(timezone.utc)
    matches, api_metadata = knockout_stage.fetch_enhanced_matches(update_pipeline)
    lock_result = bracket_lock_execution.lock_official_bracket_from_matches(
        update_pipeline.REPO_ROOT,
        matches,
    )
    print("Exact bracket lock:", json.dumps(lock_result, sort_keys=True))
    if lock_result.get("status") not in {"locked", "already_locked"}:
        return {
            "status": "waiting_for_exact_bracket",
            "bracket_lock": lock_result,
            "checked_at_utc": started_at.isoformat(),
        }

    locked_path = update_pipeline.DATA_DIR / "official_round_32_bracket_locked.csv"
    locked_bracket = pd.read_csv(locked_path)

    active = knockout_stage.active_knockout_matches(matches)
    if not active.empty:
        progress = knockout_stage.build_knockout_progress(matches, locked_bracket)
        result = {
            "status": "deferred_active_knockout_matches",
            "pipeline_phase": "knockout_stage",
            "checked_at_utc": started_at.isoformat(),
            "new_finished_matches": 0,
            "active_match_ids": active["match_id"].astype(int).tolist(),
            "message": (
                "Official knockout prices were not changed while a knockout match "
                "was active. The next scheduled run will retry after full time."
            ),
        }
        knockout_stage.atomic_csv(matches, update_pipeline.MATCHES_OUTPUT_PATH)
        knockout_stage.atomic_csv(progress, PROGRESS_PATH)
        knockout_stage.atomic_json(result, update_pipeline.RUN_SUMMARY_PATH)
        print(result["message"])
        return result

    (
        home_model,
        away_model,
        team_map,
        live_elo,
        live_team_state,
        processed_ledger,
        prediction_ledger,
    ) = update_pipeline.load_state()

    (
        live_elo_updated,
        live_state_updated,
        processed_ledger_updated,
        new_finished_matches,
        audit_rows,
    ) = knockout_stage.apply_new_finished_knockout_matches(
        matches,
        team_map,
        live_elo,
        live_team_state,
        processed_ledger,
        update_pipeline,
    )

    fingerprint = knockout_stage.input_fingerprint(
        matches,
        locked_bracket,
        live_elo_updated,
    )
    previous_state = _load_json(STATE_PATH)
    force_run = os.environ.get("FORCE_RUN", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    required_outputs_exist = all(
        path.exists()
        for path in (
            update_pipeline.TOURNAMENT_OUTPUT_PATH,
            update_pipeline.PRICES_OUTPUT_PATH,
            PROGRESS_PATH,
        )
    )
    if (
        not force_run
        and new_finished_matches.empty
        and previous_state.get("input_fingerprint") == fingerprint
        and required_outputs_exist
    ):
        print("No knockout result or fixture change required recomputation.")
        return {
            "status": "no_knockout_change",
            "checked_at_utc": started_at.isoformat(),
            "input_fingerprint": fingerprint,
            "bracket_lock": lock_result,
        }

    live_predictions, prediction_ledger_updated = (
        knockout_stage.generate_knockout_predictions(
            matches,
            home_model,
            away_model,
            team_map,
            live_elo_updated,
            live_state_updated,
            processed_ledger_updated,
            prediction_ledger,
            update_pipeline,
        )
    )
    current_tables = pd.read_csv(update_pipeline.CURRENT_TABLES_OUTPUT_PATH)
    previous_prices = _load_previous_official_knockout_prices()
    simulations = int(
        os.environ.get("KNOCKOUT_SIMULATIONS", str(update_pipeline.N_SIMULATIONS))
    )
    seed = int(
        os.environ.get(
            "KNOCKOUT_RANDOM_SEED",
            str(update_pipeline.RANDOM_SEED + 606),
        )
    )
    probabilities, prices, metadata = knockout_stage.run_progressive_simulation(
        matches,
        locked_bracket,
        current_tables,
        home_model,
        away_model,
        team_map,
        live_elo_updated,
        live_state_updated,
        previous_prices,
        update_pipeline,
        simulations,
        seed,
    )
    generated_at = datetime.now(timezone.utc)
    generated_iso = generated_at.isoformat()
    timestamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    for frame in (probabilities, prices):
        frame["generated_at_utc"] = generated_iso
        frame["model_version"] = knockout_stage.MODEL_VERSION
        frame["bracket_mode"] = knockout_stage.BRACKET_MODE
    metadata["generated_at_utc"] = generated_iso
    metadata["new_finished_matches_processed"] = int(len(new_finished_matches))
    metadata["api"] = api_metadata
    progress = knockout_stage.build_knockout_progress(matches, locked_bracket)

    knockout_stage.atomic_csv(matches, update_pipeline.MATCHES_OUTPUT_PATH)
    knockout_stage.atomic_csv(
        live_predictions,
        update_pipeline.LIVE_PREDICTIONS_OUTPUT_PATH,
    )
    knockout_stage.atomic_csv(probabilities, update_pipeline.TOURNAMENT_OUTPUT_PATH)
    knockout_stage.atomic_csv(prices, update_pipeline.PRICES_OUTPUT_PATH)
    knockout_stage.atomic_json(
        metadata,
        update_pipeline.SIMULATION_METADATA_OUTPUT_PATH,
    )
    knockout_stage.atomic_csv(progress, PROGRESS_PATH)
    knockout_stage.atomic_csv(live_elo_updated, update_pipeline.LIVE_ELO_PATH)
    knockout_stage.atomic_csv(
        live_state_updated,
        update_pipeline.LIVE_TEAM_STATE_PATH,
    )
    knockout_stage.atomic_csv(
        processed_ledger_updated,
        update_pipeline.PROCESSED_LEDGER_PATH,
    )
    knockout_stage.atomic_csv(
        prediction_ledger_updated,
        update_pipeline.PREDICTION_LEDGER_PATH,
    )
    knockout_stage.atomic_csv(
        prices,
        update_pipeline.HISTORY_DIR / f"cupmarket_prices_{timestamp}.csv",
    )

    summary = {
        "status": "updated",
        "pipeline_phase": "knockout_stage",
        "started_at_utc": started_at.isoformat(),
        "completed_at_utc": generated_iso,
        "new_finished_matches": int(len(new_finished_matches)),
        "new_matches": audit_rows,
        "number_of_simulations": simulations,
        "api": api_metadata,
        "bracket_lock": lock_result,
    }
    knockout_stage.atomic_json(summary, update_pipeline.RUN_SUMMARY_PATH)
    state = {
        "status": "updated",
        "completed_at_utc": generated_iso,
        "input_fingerprint": fingerprint,
        "new_finished_matches": int(len(new_finished_matches)),
        "actual_knockout_results_used": metadata[
            "actual_knockout_results_used"
        ],
        "upcoming_predictions": int(len(live_predictions)),
        "bracket_lock": lock_result,
    }
    knockout_stage.atomic_json(state, STATE_PATH)
    _archive_history_safely()
    print("Knockout-stage update completed:", json.dumps(state, sort_keys=True))
    return state


if __name__ == "__main__":
    run()
