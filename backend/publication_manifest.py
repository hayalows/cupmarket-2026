"""Publish a compact, durable status record for the Streamlit product."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _latest_timestamp(frame: pd.DataFrame, column: str) -> str | None:
    if frame.empty or column not in frame.columns:
        return None
    values = pd.to_datetime(frame[column], errors="coerce", utc=True).dropna()
    return None if values.empty else values.max().isoformat()


def _archive_manifest(repo_root: Path) -> dict:
    return _read_json(repo_root / "data" / "archive_manifest.json")


def is_archive_finalized(repo_root: Path) -> bool:
    """Return true only after the immutable archive bundle has been written."""
    archive = _archive_manifest(repo_root)
    return archive.get("status") == "finalized" and bool(archive.get("archive_id"))


def load_publication_manifest(repo_root: Path) -> dict:
    return _read_json(repo_root / "data" / "publication_manifest.json")


def load_archive_manifest(repo_root: Path) -> dict:
    return _archive_manifest(repo_root)


def finalized_run_summary(repo_root: Path, *, pipeline_phase: str = "archive") -> dict:
    archive = _archive_manifest(repo_root)
    checked_at = datetime.now(timezone.utc).isoformat()
    return {
        "status": "final_archive_locked",
        "pipeline_phase": pipeline_phase,
        "checked_at_utc": checked_at,
        "completed_at_utc": checked_at,
        "new_finished_matches": 0,
        "archive_id": archive.get("archive_id"),
        "message": (
            "The tournament archive is finalized. This run performed a read-only "
            "health check and did not call the score feed or rewrite published data."
        ),
    }


def build_publication_manifest(repo_root: Path) -> dict:
    data_dir = repo_root / "data"
    state_dir = repo_root / "backend" / "state"
    prices = pd.read_csv(data_dir / "cupmarket_prices_latest.csv")
    matches = pd.read_csv(data_dir / "world_cup_2026_matches_latest.csv")
    metadata = _read_json(data_dir / "phase5_simulation_metadata.json")
    run_summary = _read_json(state_dir / "last_automation_run.json")
    adaptive_health = _read_json(data_dir / "adaptive_model_health.json")
    archive_manifest = _archive_manifest(repo_root)
    final_rows = matches.loc[
        matches.get("stage", pd.Series(dtype=str)).astype(str).eq("FINAL")
        & matches.get("status", pd.Series(dtype=str)).astype(str).isin({"FINISHED", "AWARDED"})
    ]
    champion = None
    if not final_rows.empty:
        final = final_rows.iloc[-1]
        winner = str(final.get("winner") or "")
        if winner == "HOME_TEAM":
            champion = final.get("home_team")
        elif winner == "AWAY_TEAM":
            champion = final.get("away_team")
    if not champion and "prob_champion" in prices.columns:
        locked = prices.loc[pd.to_numeric(prices["prob_champion"], errors="coerce") >= 0.999]
        if not locked.empty:
            champion = str(locked.iloc[0].get("team"))
    finished = matches.get("status", pd.Series(dtype=str)).astype(str).isin({"FINISHED", "AWARDED"})
    published_at = _latest_timestamp(prices, "generated_at_utc")
    checked_at = (
        run_summary.get("completed_at_utc")
        or run_summary.get("checked_at_utc")
        or datetime.now(timezone.utc).isoformat()
    )
    publication_status = (
        "final_archive_locked"
        if archive_manifest.get("status") == "finalized"
        else str(run_summary.get("status") or "unknown")
    )
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "publication": {
            "status": publication_status,
            "last_checked_at_utc": checked_at,
            "model_generated_at_utc": published_at,
            "model_version": str(metadata.get("model_version") or "unknown"),
            "bracket_mode": str(metadata.get("bracket_mode") or "unknown"),
            "source_commit": archive_manifest.get("source_commit"),
            "new_finished_matches": int(run_summary.get("new_finished_matches", 0) or 0),
            "active_match_deferral": str(run_summary.get("status", "")).startswith("deferred_"),
            "api": run_summary.get("api") or metadata.get("api") or {},
        },
        "tournament": {
            "matches_total": int(len(matches)),
            "matches_finished": int(finished.sum()),
            "teams_tracked": int(prices["team"].nunique()) if "team" in prices.columns else 0,
            "actual_knockout_results_used": int(metadata.get("actual_knockout_results_used", 0) or 0),
            "number_of_simulations": int(metadata.get("number_of_simulations", 0) or 0),
        },
        "adaptive_guardrail": adaptive_health,
        "archive": {
            "status": str(archive_manifest.get("status") or ("finalized" if champion else "collecting")),
            "final_completed": bool(archive_manifest.get("status") == "finalized" or champion),
            "champion": archive_manifest.get("champion") or champion,
            "archive_id": archive_manifest.get("archive_id"),
            "release_tag": archive_manifest.get("release_tag"),
            "finalized_at_utc": archive_manifest.get("finalized_at_utc"),
            "source_commit": archive_manifest.get("source_commit"),
            "artifact_count": archive_manifest.get("artifact_count"),
            "history_snapshot_count": int(
                pd.read_csv(data_dir / "history" / "team_snapshots.csv")["snapshot_id"].nunique()
            ) if (data_dir / "history" / "team_snapshots.csv").exists() else 0,
        },
    }


def write_publication_manifest(repo_root: Path) -> dict:
    existing_path = repo_root / "data" / "publication_manifest.json"
    existing = _read_json(existing_path)
    archive = _archive_manifest(repo_root)
    if (
        is_archive_finalized(repo_root)
        and existing.get("archive", {}).get("archive_id")
        and existing.get("archive", {}).get("release_tag") == archive.get("release_tag")
        and existing.get("archive", {}).get("source_commit") == archive.get("source_commit")
        and existing.get("publication", {}).get("status") == "final_archive_locked"
    ):
        return existing
    payload = build_publication_manifest(repo_root)
    path = existing_path
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
    return payload
