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
MARKET_MOVEMENT_HISTORY_PATH = HISTORY_DIR / "market_movements.csv"
TEAM_SNAPSHOTS_PATH = HISTORY_DIR / "team_snapshots.csv"
ADAPTIVE_RATINGS_PATH = DATA_DIR / "adaptive_ratings_latest.csv"
PUBLICATION_MANIFEST_PATH = DATA_DIR / "publication_manifest.json"

ACTIVE_STATUSES = {"IN_PLAY", "LIVE", "PAUSED", "SUSPENDED"}
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
ROUND_OF_16_SOURCES = {
    89: (73, 76),
    90: (75, 78),
    91: (74, 77),
    92: (79, 80),
    93: (83, 84),
    94: (81, 82),
    95: (87, 86),
    96: (85, 88),
}


def clean_team(value: Any) -> str:
    try:
        if pd.isna(value):
            return "TBD"
    except (TypeError, ValueError):
        pass
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "null", "tbd"}:
        return "TBD"
    return text


def _score_text(row: pd.Series) -> str:
    home = pd.to_numeric(
        row.get("home_score", row.get("home_score_full_time")),
        errors="coerce",
    )
    away = pd.to_numeric(
        row.get("away_score", row.get("away_score_full_time")),
        errors="coerce",
    )
    return "vs" if pd.isna(home) or pd.isna(away) else f"{int(home)}-{int(away)}"


def _progress_by_logical_number(progress: pd.DataFrame) -> dict[int, pd.Series]:
    if progress.empty or "logical_match_number" not in progress.columns:
        return {}
    rows: dict[int, pd.Series] = {}
    for _, row in progress.iterrows():
        number = pd.to_numeric(row.get("logical_match_number"), errors="coerce")
        if pd.notna(number):
            rows[int(number)] = row
    return rows


def _winner_slot_text(rows: dict[int, pd.Series], source_number: int) -> dict[str, Any]:
    row = rows.get(source_number)
    if row is None:
        return {
            "source_match": source_number,
            "label": f"Winner of match {source_number}",
            "short_label": f"M{source_number} winner",
            "state": "Waiting",
            "known_team": "TBD",
            "fixture": "TBD",
        }

    home = clean_team(row.get("home_team"))
    away = clean_team(row.get("away_team"))
    advancing = clean_team(row.get("advancing_team"))
    fixture = f"{home} {_score_text(row)} {away}" if home != "TBD" and away != "TBD" else "TBD"
    if advancing != "TBD":
        return {
            "source_match": source_number,
            "label": advancing,
            "short_label": advancing,
            "state": "Advanced",
            "known_team": advancing,
            "fixture": fixture,
        }
    if home != "TBD" and away != "TBD":
        return {
            "source_match": source_number,
            "label": f"Winner of match {source_number}: {home} vs {away}",
            "short_label": f"{home}/{away} winner",
            "state": str(row.get("status", "Pending")).replace("_", " ").title(),
            "known_team": "TBD",
            "fixture": f"{home} vs {away}",
        }
    return {
        "source_match": source_number,
        "label": f"Winner of match {source_number}",
        "short_label": f"M{source_number} winner",
        "state": "Waiting",
        "known_team": "TBD",
        "fixture": "TBD",
    }


def _slot_state(left: dict[str, Any], right: dict[str, Any]) -> str:
    known = sum(1 for slot in [left, right] if slot["known_team"] != "TBD")
    if known == 2:
        return "Fixture confirmed"
    if known == 1:
        return "One team through"
    return "Waiting for winners"


def round_of_16_build(progress: pd.DataFrame) -> pd.DataFrame:
    """Build Round-of-16 slots from known Round-of-32 winners and pending ties."""
    if progress.empty:
        return pd.DataFrame()
    rows_by_number = _progress_by_logical_number(progress)
    if not rows_by_number:
        return pd.DataFrame()
    output = []
    for match_number, (left_source, right_source) in ROUND_OF_16_SOURCES.items():
        left = _winner_slot_text(rows_by_number, left_source)
        right = _winner_slot_text(rows_by_number, right_source)
        fixture_row = rows_by_number.get(match_number, pd.Series(dtype=object))
        kickoff = fixture_row.get("utc_date")
        known_teams = [
            slot["known_team"]
            for slot in [left, right]
            if slot["known_team"] != "TBD"
        ]
        output.append(
            {
                "match_number": match_number,
                "stage": "LAST_16",
                "stage_label": "Round of 16",
                "fixture": f"{left['short_label']} vs {right['short_label']}",
                "side_a": left["label"],
                "side_b": right["label"],
                "side_a_source_match": left_source,
                "side_b_source_match": right_source,
                "side_a_state": left["state"],
                "side_b_state": right["state"],
                "state": _slot_state(left, right),
                "known_teams": ", ".join(known_teams),
                "kickoff_utc": kickoff,
            }
        )
    result = pd.DataFrame(output)
    if not result.empty:
        result["kickoff_utc"] = pd.to_datetime(
            result["kickoff_utc"], errors="coerce", utc=True
        )
        result = result.sort_values("match_number").reset_index(drop=True)
    return result


def team_next_knockout_slot(progress: pd.DataFrame, team: str) -> pd.Series:
    slots = round_of_16_build(progress)
    if slots.empty:
        return pd.Series(dtype=object)
    team_text = str(team)
    for _, row in slots.iterrows():
        known = [
            value.strip()
            for value in str(row.get("known_teams", "")).split(",")
            if value.strip()
        ]
        if team_text in known:
            return row
    return pd.Series(dtype=object)


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
        "movement_history": load_latest_csv(MARKET_MOVEMENT_HISTORY_PATH),
        "snapshots": load_latest_csv(TEAM_SNAPSHOTS_PATH),
        "adaptive_ratings": load_latest_csv(ADAPTIVE_RATINGS_PATH),
        "publication_manifest": load_latest_json(PUBLICATION_MANIFEST_PATH),
    }


def available_teams(data: dict[str, Any]) -> list[str]:
    teams: set[str] = set()
    for key, column in (
        ("prices", "team"),
        ("path_status", "team"),
        ("opponents", "team"),
        ("movements", "team"),
        ("movement_history", "team"),
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


def latest_direct_event_movement(frame: pd.DataFrame, team: str) -> pd.Series:
    if frame.empty or "team" not in frame.columns:
        return pd.Series(dtype=object)
    rows = frame.loc[frame["team"].astype(str) == str(team)].copy()
    if rows.empty:
        return pd.Series(dtype=object)
    if "movement_type" in rows.columns:
        rows = rows.loc[rows["movement_type"].astype(str).eq("match_event")]
    if "relationship_to_event" in rows.columns:
        rows = rows.loc[rows["relationship_to_event"].astype(str).eq("played")]
    if rows.empty:
        return pd.Series(dtype=object)
    return latest_team_row(rows, team)


def latest_relevant_movement(frame: pd.DataFrame, team: str) -> pd.Series:
    if frame.empty or "team" not in frame.columns:
        return pd.Series(dtype=object)
    rows = frame.loc[frame["team"].astype(str) == str(team)].copy()
    if rows.empty:
        return pd.Series(dtype=object)
    if "relationship_to_event" in rows.columns:
        rows = rows.loc[~rows["relationship_to_event"].astype(str).eq("other")]
    if rows.empty:
        return pd.Series(dtype=object)
    return latest_team_row(rows, team)


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
    movement_source = data.get("movement_history", pd.DataFrame())
    if not isinstance(movement_source, pd.DataFrame) or movement_source.empty:
        movement_source = data.get("movements", pd.DataFrame())
    event_movement = latest_direct_event_movement(movement_source, team)
    latest_movement = latest_relevant_movement(movement_source, team)
    movement = latest_movement if not latest_movement.empty else event_movement
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
        "event_movement": event_movement,
        "latest_movement": latest_movement,
        "opponents": opponents,
        "fixtures": fixtures,
    }
