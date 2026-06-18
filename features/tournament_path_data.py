from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from features.official_data import load_latest_csv, load_latest_json
from features.tournament_data import DATA_DIR, load_static_data

ROOT = Path(__file__).resolve().parents[1]
HISTORY_DIR = DATA_DIR / "history"

PATH_STATUS_PATH = DATA_DIR / "round_32_path_status_latest.csv"
OPPONENTS_PATH = DATA_DIR / "round_32_opponent_probabilities_latest.csv"
BRACKET_PATH = DATA_DIR / "official_round_32_bracket_locked.csv"
BRACKET_STATE_PATH = DATA_DIR / "official_round_32_bracket_lock.json"
OPPONENT_METADATA_PATH = DATA_DIR / "round_32_opponent_probabilities_metadata.json"
KNOCKOUT_PROGRESS_PATH = DATA_DIR / "knockout_progress_latest.csv"
MARKET_MOVEMENT_PATH = DATA_DIR / "market_movements_latest.csv"
TEAM_SNAPSHOTS_PATH = HISTORY_DIR / "team_snapshots.csv"

ACTIVE_STATUSES = {"IN_PLAY", "PAUSED"}
UPCOMING_STATUSES = {"TIMED", "SCHEDULED"}
STATUS_LABELS = {
    "projected": "Projected path",
    "slot_confirmed": "Slot confirmed",
    "confirmed": "Fixture confirmed",
    "slot_confirmed_opponent_pending": "Slot confirmed · opponent pending",
    "third_place_ranking_pending": "Third-place ranking pending",
    "eliminated": "Eliminated",
}
STAGE_LABELS = {
    "LAST_32": "Round of 32",
    "ROUND_OF_32": "Round of 32",
    "R32": "Round of 32",
    "LAST_16": "Round of 16",
    "ROUND_OF_16": "Round of 16",
    "R16": "Round of 16",
    "QUARTER_FINALS": "Quarter-finals",
    "QUARTER_FINAL": "Quarter-finals",
    "QF": "Quarter-finals",
    "SEMI_FINALS": "Semi-finals",
    "SEMI_FINAL": "Semi-finals",
    "SF": "Semi-finals",
    "THIRD_PLACE": "Third-place match",
    "FINAL": "Final",
}


def load_tournament_path_data() -> dict[str, Any]:
    static = load_static_data()
    return {
        "prices": static.get("prices", pd.DataFrame()),
        "predictions": static.get("latest_predictions", pd.DataFrame()),
        "history": static.get("history", pd.DataFrame()),
        "path_status": load_latest_csv(PATH_STATUS_PATH),
        "opponents": load_latest_csv(OPPONENTS_PATH),
        "bracket": load_latest_csv(BRACKET_PATH),
        "bracket_state": load_latest_json(BRACKET_STATE_PATH),
        "opponent_metadata": load_latest_json(OPPONENT_METADATA_PATH),
        "progress": load_latest_csv(KNOCKOUT_PROGRESS_PATH),
        "movements": load_latest_csv(MARKET_MOVEMENT_PATH),
        "snapshots": load_latest_csv(TEAM_SNAPSHOTS_PATH),
    }


def available_teams(data: dict[str, Any]) -> list[str]:
    teams: set[str] = set()
    for key, column in (
        ("prices", "team"),
        ("path_status", "team"),
        ("opponents", "team"),
        ("movements", "team"),
        ("snapshots", "team"),
    ):
        frame = data.get(key)
        if isinstance(frame, pd.DataFrame) and column in frame.columns:
            teams.update(frame[column].dropna().astype(str))

    for key in ("progress", "bracket"):
        frame = data.get(key)
        if not isinstance(frame, pd.DataFrame):
            continue
        for column in ("home_team", "away_team"):
            if column in frame.columns:
                teams.update(frame[column].dropna().astype(str))
    return sorted(team for team in teams if team and team.lower() != "nan")


def preferred_team(
    teams: list[str],
    requested: str | None,
    prices: pd.DataFrame,
) -> str | None:
    if not teams:
        return None
    if requested in teams:
        return requested
    if "Ghana" in teams:
        return "Ghana"
    if not prices.empty and {"team", "cupmarket_price"}.issubset(prices.columns):
        ranked = prices.copy()
        ranked["cupmarket_price"] = pd.to_numeric(
            ranked["cupmarket_price"], errors="coerce"
        )
        ranked = ranked.dropna(subset=["cupmarket_price"]).sort_values(
            "cupmarket_price", ascending=False
        )
        if not ranked.empty and str(ranked.iloc[0]["team"]) in teams:
            return str(ranked.iloc[0]["team"])
    return teams[0]


def latest_team_row(
    frame: pd.DataFrame,
    team: str,
    *,
    team_column: str = "team",
) -> pd.Series:
    if frame.empty or team_column not in frame.columns:
        return pd.Series(dtype=object)
    rows = frame.loc[frame[team_column].astype(str) == str(team)].copy()
    if rows.empty:
        return pd.Series(dtype=object)
    for timestamp_column in ("generated_at_utc", "snapshot_id", "processed_at_utc"):
        if timestamp_column in rows.columns:
            rows[timestamp_column] = pd.to_datetime(
                rows[timestamp_column], errors="coerce", utc=True
            )
            rows = rows.sort_values(timestamp_column, na_position="first")
            break
    return rows.iloc[-1]


def opponent_options(
    opponents: pd.DataFrame,
    team: str,
    limit: int = 6,
) -> pd.DataFrame:
    if opponents.empty or not {"team", "opponent"}.issubset(opponents.columns):
        return pd.DataFrame()
    rows = opponents.loc[opponents["team"].astype(str) == str(team)].copy()
    if rows.empty:
        return rows
    probability_column = (
        "probability_given_qualification"
        if "probability_given_qualification" in rows.columns
        else "probability_unconditional"
    )
    if probability_column in rows.columns:
        rows[probability_column] = pd.to_numeric(
            rows[probability_column], errors="coerce"
        )
        rows = rows.sort_values(probability_column, ascending=False)
    return rows.head(limit).reset_index(drop=True)


def team_fixtures(
    progress: pd.DataFrame,
    bracket: pd.DataFrame,
    team: str,
) -> pd.DataFrame:
    source = progress if not progress.empty else bracket
    if source.empty or not {"home_team", "away_team"}.issubset(source.columns):
        return pd.DataFrame()
    mask = (
        source["home_team"].astype(str).eq(str(team))
        | source["away_team"].astype(str).eq(str(team))
    )
    rows = source.loc[mask].copy()
    if rows.empty:
        return rows
    if "utc_date" in rows.columns:
        rows["utc_date"] = pd.to_datetime(rows["utc_date"], errors="coerce", utc=True)
        rows = rows.sort_values("utc_date", na_position="last")
    return rows.reset_index(drop=True)


def stage_label(value: Any) -> str:
    text = str(value or "").strip()
    return STAGE_LABELS.get(text, text.replace("_", " ").title() or "Tournament")


def status_label(value: Any) -> str:
    text = str(value or "").strip()
    return STATUS_LABELS.get(text, text.replace("_", " ").title() or "Pending")


def tournament_summary(data: dict[str, Any]) -> dict[str, Any]:
    progress = data.get("progress", pd.DataFrame())
    bracket = data.get("bracket", pd.DataFrame())
    path_status = data.get("path_status", pd.DataFrame())
    bracket_state = data.get("bracket_state", {}) or {}

    completed = live = upcoming = 0
    current_stage = "Group stage"
    if isinstance(progress, pd.DataFrame) and not progress.empty:
        statuses = progress.get("status", pd.Series(dtype=str)).astype(str)
        completed = int(statuses.eq("FINISHED").sum())
        live = int(statuses.isin(ACTIVE_STATUSES).sum())
        upcoming = int(statuses.isin(UPCOMING_STATUSES).sum())
        stage_rows = progress.copy()
        if live:
            stage_rows = stage_rows.loc[statuses.isin(ACTIVE_STATUSES)]
        elif upcoming:
            stage_rows = stage_rows.loc[statuses.isin(UPCOMING_STATUSES)]
        else:
            stage_rows = stage_rows.loc[statuses.eq("FINISHED")]
        if not stage_rows.empty and "stage" in stage_rows.columns:
            current_stage = stage_label(stage_rows.iloc[0]["stage"])
    elif isinstance(bracket, pd.DataFrame) and not bracket.empty:
        current_stage = "Round of 32"
        upcoming = len(bracket)
    elif isinstance(path_status, pd.DataFrame) and not path_status.empty:
        current_stage = "Group-stage paths"

    locked = bool(
        (isinstance(bracket, pd.DataFrame) and not bracket.empty)
        or str(bracket_state.get("status", "")).lower() in {"locked", "already_locked"}
    )
    return {
        "current_stage": current_stage,
        "bracket_status": "Official bracket locked" if locked else "Bracket projected",
        "completed_knockout_matches": completed,
        "live_knockout_matches": live,
        "upcoming_knockout_matches": upcoming,
        "is_locked": locked,
    }


def team_summary(data: dict[str, Any], team: str) -> dict[str, Any]:
    price = latest_team_row(data.get("prices", pd.DataFrame()), team)
    path = latest_team_row(data.get("path_status", pd.DataFrame()), team)
    movement = latest_team_row(data.get("movements", pd.DataFrame()), team)
    opponents = opponent_options(data.get("opponents", pd.DataFrame()), team)
    fixtures = team_fixtures(
        data.get("progress", pd.DataFrame()),
        data.get("bracket", pd.DataFrame()),
        team,
    )
    return {
        "team": team,
        "price": price,
        "path": path,
        "movement": movement,
        "opponents": opponents,
        "fixtures": fixtures,
    }
