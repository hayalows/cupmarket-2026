"""Derive trustworthy workflow and match-event market movements.

The calculations use the previous archived team snapshot as the primary anchor.
The live prices file is read-only and remains unchanged.
"""

from __future__ import annotations

from pathlib import Path
import json
import os

import numpy as np
import pandas as pd


MOVEMENT_KEYS = ["event_id", "team"]


def market_impact_is_enabled() -> bool:
    return os.environ.get("ENABLE_MARKET_IMPACT_ARCHIVE", "true").lower() in {
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


def _read_summary(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Run summary is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _publication_label(summary: dict) -> str:
    phase = str(summary.get("pipeline_phase") or "").strip()
    if phase == "knockout_stage":
        return "Official knockout model refresh"
    return "Official model refresh"


def _movement_details(summary: dict) -> tuple[str, str, str, str, str]:
    matches = summary.get("new_matches") or []
    ids = sorted(
        str(int(match["match_id"]))
        for match in matches
        if match.get("match_id") is not None
    )
    if not ids:
        completed_at = str(summary.get("completed_at_utc", "")).strip()
        if not completed_at:
            raise ValueError("Updated run has no completed_at_utc value")
        return (
            "publication:" + completed_at,
            "",
            _publication_label(summary),
            "publication_refresh",
            "publication_refresh",
        )
    labels = [
        f"{match.get('home_team')} {match.get('home_score')}-"
        f"{match.get('away_score')} {match.get('away_team')}"
        for match in matches
    ]
    scope = "single_match" if len(ids) == 1 else "match_batch"
    event_id = "matches:" + "|".join(ids)
    return event_id, "|".join(ids), " | ".join(labels), scope, "match_event"


def _latest_prior_snapshot(
    snapshots: pd.DataFrame,
    current_snapshot_id: str,
) -> pd.DataFrame:
    if snapshots.empty:
        return pd.DataFrame()
    required = {"snapshot_id", "team", "cupmarket_price"}
    if not required.issubset(snapshots.columns):
        return pd.DataFrame()

    current_time = pd.to_datetime(current_snapshot_id, errors="coerce", utc=True)
    candidates = snapshots.copy()
    candidates["_snapshot_time"] = pd.to_datetime(
        candidates["snapshot_id"], errors="coerce", utc=True
    )
    if pd.notna(current_time):
        candidates = candidates.loc[candidates["_snapshot_time"] < current_time]
    else:
        candidates = candidates.loc[
            candidates["snapshot_id"].astype(str) != str(current_snapshot_id)
        ]
    if candidates.empty:
        return pd.DataFrame()

    candidates = candidates.loc[candidates["_snapshot_time"].notna()]
    if candidates.empty:
        return pd.DataFrame()

    latest_time = candidates["_snapshot_time"].max()
    return candidates.loc[candidates["_snapshot_time"] == latest_time].copy()


def _prior_lookup(prior: pd.DataFrame, column: str) -> dict[str, float]:
    if prior.empty or column not in prior.columns:
        return {}
    return dict(
        zip(
            prior["team"].astype(str),
            pd.to_numeric(prior[column], errors="coerce"),
        )
    )


def _safe_percent(change: pd.Series, before: pd.Series) -> pd.Series:
    return np.where(
        before.abs() > 1e-12,
        100.0 * change / before,
        np.nan,
    )


def build_market_movements(
    prices: pd.DataFrame,
    summary: dict,
    prior_snapshots: pd.DataFrame,
) -> pd.DataFrame:
    completed_at = str(summary.get("completed_at_utc", "")).strip()
    if not completed_at:
        raise ValueError("Updated run summary has no completed_at_utc value")

    event_id, trigger_ids, trigger_matches, scope, movement_type = (
        _movement_details(summary)
    )
    prior = _latest_prior_snapshot(prior_snapshots, completed_at)
    prior_price = _prior_lookup(prior, "cupmarket_price")
    prior_elo = _prior_lookup(prior, "live_elo")
    prior_r32 = _prior_lookup(prior, "prob_reach_round_32")
    prior_champion = _prior_lookup(prior, "prob_champion")

    result = prices[
        [
            "team",
            "group",
            "live_elo",
            "cupmarket_price",
            "previous_price",
            "prob_reach_round_32",
            "prob_champion",
            "model_version",
            "bracket_mode",
        ]
    ].copy()

    teams = result["team"].astype(str)
    archived_before = teams.map(prior_price)
    fallback_before = pd.to_numeric(result["previous_price"], errors="coerce")
    result["price_before"] = archived_before.fillna(fallback_before)
    result["price_after"] = pd.to_numeric(
        result["cupmarket_price"], errors="coerce"
    )
    result["price_change"] = result["price_after"] - result["price_before"]
    result["price_change_percent"] = _safe_percent(
        result["price_change"], result["price_before"]
    )

    result["elo_before"] = teams.map(prior_elo)
    result["elo_after"] = pd.to_numeric(result["live_elo"], errors="coerce")
    result["elo_change"] = result["elo_after"] - result["elo_before"]

    result["round_32_probability_before"] = teams.map(prior_r32)
    result["round_32_probability_after"] = pd.to_numeric(
        result["prob_reach_round_32"], errors="coerce"
    )
    result["round_32_probability_change"] = (
        result["round_32_probability_after"]
        - result["round_32_probability_before"]
    )

    result["champion_probability_before"] = teams.map(prior_champion)
    result["champion_probability_after"] = pd.to_numeric(
        result["prob_champion"], errors="coerce"
    )
    result["champion_probability_change"] = (
        result["champion_probability_after"]
        - result["champion_probability_before"]
    )

    result.insert(0, "event_id", event_id)
    result["snapshot_id"] = completed_at
    result["trigger_match_ids"] = trigger_ids
    result["trigger_matches"] = trigger_matches
    result["attribution_scope"] = scope
    result["movement_type"] = movement_type
    result["before_source"] = np.where(
        archived_before.notna(),
        "previous_archived_snapshot",
        "prices_previous_price_fallback",
    )
    result["individual_match_attribution_available"] = (
        movement_type == "match_event" and scope == "single_match"
    )

    played = {
        str(team)
        for match in summary.get("new_matches") or []
        for team in (match.get("home_team"), match.get("away_team"))
        if team
    }
    team_group = dict(zip(result["team"].astype(str), result["group"].astype(str)))
    played_groups = {team_group[team] for team in played if team in team_group}
    if movement_type == "match_event":
        result["relationship_to_event"] = [
            "played"
            if str(team) in played
            else "same_group"
            if str(group) in played_groups
            else "other"
            for team, group in zip(result["team"], result["group"])
        ]
    else:
        result["relationship_to_event"] = "publication_refresh"

    drop_columns = [
        "cupmarket_price",
        "previous_price",
        "prob_reach_round_32",
        "prob_champion",
        "live_elo",
    ]
    return result.drop(columns=drop_columns)


def _append_unique(path: Path, rows: pd.DataFrame) -> int:
    if path.exists():
        existing = pd.read_csv(path)
        combined = pd.concat([existing, rows], ignore_index=True, sort=False)
    else:
        combined = rows.copy()
    old_count = len(combined) - len(rows)
    combined = combined.drop_duplicates(subset=MOVEMENT_KEYS, keep="first")
    added = max(0, len(combined) - old_count)
    _atomic_csv(combined, path)
    return int(added)


def _has_meaningful_movement(rows: pd.DataFrame) -> bool:
    for column in [
        "price_change",
        "elo_change",
        "round_32_probability_change",
        "champion_probability_change",
    ]:
        if column not in rows.columns:
            continue
        values = pd.to_numeric(rows[column], errors="coerce").abs()
        if values.gt(1e-9).any():
            return True
    return False


def archive_market_movements(repo_root: Path) -> dict:
    if not market_impact_is_enabled():
        return {"status": "disabled"}

    data_dir = repo_root / "data"
    state_dir = repo_root / "backend" / "state"
    summary = _read_summary(state_dir / "last_automation_run.json")
    if summary.get("status") != "updated":
        return {"status": "skipped", "reason": str(summary.get("status"))}

    prices_path = data_dir / "cupmarket_prices_latest.csv"
    if not prices_path.exists():
        raise FileNotFoundError(f"Prices file is missing: {prices_path}")
    prices = pd.read_csv(prices_path)

    history_dir = data_dir / "history"
    snapshots_path = history_dir / "team_snapshots.csv"
    snapshots = (
        pd.read_csv(snapshots_path)
        if snapshots_path.exists()
        else pd.DataFrame()
    )
    movements = build_market_movements(prices, summary, snapshots)
    movement_type = str(movements["movement_type"].iloc[0])
    if movement_type != "match_event" and not _has_meaningful_movement(movements):
        return {"status": "skipped", "reason": "no_meaningful_price_movement"}

    archive_path = history_dir / "market_movements.csv"
    latest_path = data_dir / "market_movements_latest.csv"
    added = _append_unique(archive_path, movements)
    _atomic_csv(movements, latest_path)

    return {
        "status": "archived",
        "rows_added": added,
        "event_id": str(movements["event_id"].iloc[0]),
        "attribution_scope": str(movements["attribution_scope"].iloc[0]),
        "latest_path": str(latest_path),
    }
