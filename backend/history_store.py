"""Append-only analytical history for CupMarket tournament updates.

This module reads published model outputs after a successful update. It never
calculates prices, changes Elo, or writes files used by the Streamlit app.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os

import numpy as np
import pandas as pd


TEAM_SNAPSHOT_KEYS = ["snapshot_id", "team"]
ELO_EVENT_KEYS = ["match_id", "team", "model_version"]
MATCH_IMPACT_KEYS = ["snapshot_id", "affected_team"]
BRACKET_SNAPSHOT_KEYS = ["snapshot_id", "team"]
BASELINE_KEYS = ["team"]


@dataclass(frozen=True)
class HistoryPaths:
    root: Path
    baseline: Path
    team_snapshots: Path
    elo_events: Path
    match_impacts: Path
    bracket_snapshots: Path

    @classmethod
    def under(cls, root: Path) -> "HistoryPaths":
        return cls(
            root=root,
            baseline=root / "tournament_baseline.csv",
            team_snapshots=root / "team_snapshots.csv",
            elo_events=root / "elo_events.csv",
            match_impacts=root / "match_impacts.csv",
            bracket_snapshots=root / "bracket_snapshots.csv",
        )


def history_is_enabled() -> bool:
    return os.environ.get("ENABLE_HISTORY_ARCHIVE", "true").lower() in {
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


def _append_unique(path: Path, rows: pd.DataFrame, keys: list[str]) -> int:
    if rows.empty:
        return 0
    missing = sorted(set(keys) - set(rows.columns))
    if missing:
        raise ValueError(f"History rows for {path.name} are missing keys: {missing}")

    if path.exists():
        existing = pd.read_csv(path)
        combined = pd.concat([existing, rows], ignore_index=True, sort=False)
    else:
        combined = rows.copy()

    before = len(combined)
    combined = combined.drop_duplicates(subset=keys, keep="first")
    added = len(combined) - (before - len(rows))
    _atomic_csv(combined, path)
    return max(0, int(added))


def _read_csv(path: Path, required: set[str]) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"History source is missing: {path}")
    frame = pd.read_csv(path)
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{path.name} is missing columns: {missing}")
    return frame


def _read_summary(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Run summary is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _snapshot_id(summary: dict) -> str:
    completed_at = str(summary.get("completed_at_utc", "")).strip()
    if not completed_at:
        raise ValueError("Updated run summary has no completed_at_utc value")
    return completed_at


def _trigger_details(summary: dict) -> tuple[str, str]:
    matches = summary.get("new_matches") or []
    ids = sorted(
        str(int(match["match_id"]))
        for match in matches
        if match.get("match_id") is not None
    )
    labels = [
        f"{match.get('home_team')} {match.get('home_score')}-"
        f"{match.get('away_score')} {match.get('away_team')}"
        for match in matches
    ]
    return "|".join(ids), " | ".join(labels)


def build_team_snapshots(prices: pd.DataFrame, summary: dict) -> pd.DataFrame:
    snapshot_id = _snapshot_id(summary)
    trigger_ids, trigger_matches = _trigger_details(summary)
    result = prices.copy()
    result.insert(0, "snapshot_id", snapshot_id)
    result["trigger_match_ids"] = trigger_ids
    result["trigger_matches"] = trigger_matches
    result["snapshot_type"] = (
        "post_match_update"
        if int(summary.get("new_finished_matches", 0) or 0) > 0
        else "publication_refresh"
    )
    return result


def build_elo_events(prices: pd.DataFrame, summary: dict) -> pd.DataFrame:
    current_elo = dict(
        zip(
            prices["team"].astype(str),
            pd.to_numeric(prices["live_elo"], errors="coerce"),
        )
    )
    rows: list[dict] = []
    model_version = str(prices["model_version"].iloc[0])
    processed_at = _snapshot_id(summary)

    for match in summary.get("new_matches") or []:
        participants = (
            ("home", match.get("home_team"), match.get("away_team")),
            ("away", match.get("away_team"), match.get("home_team")),
        )
        for side, team, opponent in participants:
            if not team:
                continue
            change = float(match.get(f"{side}_elo_change", 0.0) or 0.0)
            after = current_elo.get(str(team), np.nan)
            before = float(after - change) if pd.notna(after) else np.nan
            home_score = int(match.get("home_score", 0) or 0)
            away_score = int(match.get("away_score", 0) or 0)
            goals_for = home_score if side == "home" else away_score
            goals_against = away_score if side == "home" else home_score
            result = "draw"
            if goals_for > goals_against:
                result = "win"
            elif goals_for < goals_against:
                result = "loss"
            rows.append(
                {
                    "match_id": int(match["match_id"]),
                    "team": str(team),
                    "opponent": str(opponent),
                    "result": result,
                    "goals_for": goals_for,
                    "goals_against": goals_against,
                    "elo_before": before,
                    "elo_after": after,
                    "elo_change": change,
                    "processed_at_utc": processed_at,
                    "model_version": model_version,
                }
            )
    return pd.DataFrame(rows)


def _relationship(team: str, group: str, played: set[str], played_groups: set[str]) -> str:
    if team in played:
        return "played"
    if group in played_groups:
        return "same_group"
    return "other"


def build_match_impacts(prices: pd.DataFrame, summary: dict) -> pd.DataFrame:
    snapshot_id = _snapshot_id(summary)
    matches = summary.get("new_matches") or []
    played = {
        str(team)
        for match in matches
        for team in (match.get("home_team"), match.get("away_team"))
        if team
    }
    team_group = dict(zip(prices["team"].astype(str), prices["group"].astype(str)))
    played_groups = {team_group[team] for team in played if team in team_group}
    trigger_ids, trigger_matches = _trigger_details(summary)

    result = prices[
        [
            "team",
            "group",
            "live_elo",
            "cupmarket_price",
            "previous_price",
            "price_change",
            "price_change_percent",
            "prob_reach_round_32",
            "prob_champion",
            "model_version",
            "bracket_mode",
        ]
    ].copy()
    result = result.rename(
        columns={
            "team": "affected_team",
            "cupmarket_price": "price_after",
            "previous_price": "price_before",
            "prob_reach_round_32": "round_32_probability_after",
            "prob_champion": "champion_probability_after",
        }
    )
    result.insert(0, "snapshot_id", snapshot_id)
    result["trigger_match_ids"] = trigger_ids
    result["trigger_matches"] = trigger_matches
    result["relationship_to_matches"] = [
        _relationship(str(row.affected_team), str(row.group), played, played_groups)
        for row in result.itertuples(index=False)
    ]
    return result


def build_bracket_snapshots(
    probabilities: pd.DataFrame,
    group_tables: pd.DataFrame,
    summary: dict,
) -> pd.DataFrame:
    snapshot_id = _snapshot_id(summary)
    trigger_ids, _ = _trigger_details(summary)
    current_position = group_tables[["team", "position", "points", "goal_difference"]]
    result = probabilities.merge(current_position, on="team", how="left")
    columns = [
        "team",
        "group",
        "position",
        "points",
        "goal_difference",
        "prob_finish_1st_group",
        "prob_finish_2nd_group",
        "prob_finish_3rd_group",
        "prob_best_third_qualifier",
        "prob_reach_round_32",
        "bracket_mode",
        "model_version",
    ]
    result = result[columns].copy()
    result.insert(0, "snapshot_id", snapshot_id)
    result["trigger_match_ids"] = trigger_ids
    return result


def _baseline_source(market_history_dir: Path, current_prices: pd.DataFrame) -> pd.DataFrame:
    candidates = sorted(market_history_dir.glob("cupmarket_prices_*.csv"))
    for path in candidates:
        try:
            frame = pd.read_csv(path)
        except (OSError, pd.errors.ParserError):
            continue
        if {"team", "group", "live_elo", "cupmarket_price"}.issubset(frame.columns):
            return frame
    return current_prices


def create_baseline_once(
    path: Path,
    market_history_dir: Path,
    current_prices: pd.DataFrame,
) -> bool:
    if path.exists():
        return False
    source = _baseline_source(market_history_dir, current_prices)
    probability_columns = [
        column
        for column in source.columns
        if column.startswith("prob_")
    ]
    columns = [
        "team",
        "group",
        "live_elo",
        "cupmarket_price",
        "market_rank",
        *probability_columns,
        "generated_at_utc",
        "model_version",
        "bracket_mode",
    ]
    columns = [column for column in columns if column in source.columns]
    baseline = source[columns].copy()
    baseline = baseline.rename(
        columns={
            "live_elo": "opening_elo",
            "cupmarket_price": "opening_price",
            "market_rank": "opening_market_rank",
            "generated_at_utc": "baseline_captured_at_utc",
        }
    )
    baseline["baseline_source"] = "earliest_market_history"
    baseline = baseline.drop_duplicates(subset=BASELINE_KEYS, keep="first")
    _atomic_csv(baseline, path)
    return True


def archive_latest_outputs(repo_root: Path) -> dict:
    """Archive a successful model publication without changing live outputs."""
    if not history_is_enabled():
        return {"status": "disabled"}

    data_dir = repo_root / "data"
    state_dir = repo_root / "backend" / "state"
    paths = HistoryPaths.under(data_dir / "history")
    summary = _read_summary(state_dir / "last_automation_run.json")

    if summary.get("status") != "updated":
        return {"status": "skipped", "reason": str(summary.get("status"))}
    new_finished_matches = int(summary.get("new_finished_matches", 0) or 0)

    prices = _read_csv(
        data_dir / "cupmarket_prices_latest.csv",
        {"team", "group", "live_elo", "cupmarket_price", "model_version"},
    )
    probabilities = _read_csv(
        data_dir / "tournament_probabilities_latest.csv",
        {"team", "group", "model_version", "bracket_mode"},
    )
    group_tables = _read_csv(
        data_dir / "current_group_tables.csv",
        {"team", "position", "points", "goal_difference"},
    )

    baseline_created = create_baseline_once(
        paths.baseline,
        data_dir / "market_history",
        prices,
    )
    added = {
        "team_snapshots": _append_unique(
            paths.team_snapshots,
            build_team_snapshots(prices, summary),
            TEAM_SNAPSHOT_KEYS,
        ),
        "bracket_snapshots": _append_unique(
            paths.bracket_snapshots,
            build_bracket_snapshots(probabilities, group_tables, summary),
            BRACKET_SNAPSHOT_KEYS,
        ),
    }
    if new_finished_matches > 0:
        added["elo_events"] = _append_unique(
            paths.elo_events,
            build_elo_events(prices, summary),
            ELO_EVENT_KEYS,
        )
        added["match_impacts"] = _append_unique(
            paths.match_impacts,
            build_match_impacts(prices, summary),
            MATCH_IMPACT_KEYS,
        )
    else:
        added["elo_events"] = 0
        added["match_impacts"] = 0
    return {
        "status": "archived",
        "baseline_created": baseline_created,
        "rows_added": added,
        "history_root": str(paths.root),
    }
