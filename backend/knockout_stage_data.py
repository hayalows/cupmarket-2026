"""Knockout-stage ingestion and official result handling for CupMarket.

The group-stage pipeline remains unchanged. This module takes over only after the
official Round-of-32 bracket has been locked.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

import numpy as np
import pandas as pd


MODEL_VERSION = "phase6_knockout_progression_v1"
BRACKET_MODE = "official_api_locked_knockout_progression"
ACTIVE_STATUSES = {"IN_PLAY", "LIVE", "PAUSED", "SUSPENDED"}
UPCOMING_STATUSES = {"TIMED", "SCHEDULED"}
KNOCKOUT_STAGES = {
    "LAST_32",
    "ROUND_OF_32",
    "R32",
    "LAST_16",
    "ROUND_OF_16",
    "R16",
    "QUARTER_FINALS",
    "QUARTER_FINAL",
    "QF",
    "SEMI_FINALS",
    "SEMI_FINAL",
    "SF",
    "THIRD_PLACE",
    "FINAL",
}
STAGE_ALIASES = {
    "round_32": {"LAST_32", "ROUND_OF_32", "R32"},
    "round_16": {"LAST_16", "ROUND_OF_16", "R16"},
    "quarter_final": {"QUARTER_FINALS", "QUARTER_FINAL", "QF"},
    "semi_final": {"SEMI_FINALS", "SEMI_FINAL", "SF"},
    "third_place": {"THIRD_PLACE"},
    "final": {"FINAL"},
}
LOGICAL_NUMBERS = {
    "round_16": tuple(range(89, 97)),
    "quarter_final": tuple(range(97, 101)),
    "semi_final": (101, 102),
    "third_place": (103,),
    "final": (104,),
}
FINAL_MATCH_NUMBER = 104
MEDAL_FIXTURE_SOURCES = {
    103: ("loser", (101, 102)),
    104: ("winner", (101, 102)),
}


class KnockoutProcessingError(RuntimeError):
    """Raised when official knockout data conflicts with the locked bracket."""


def atomic_csv(frame: pd.DataFrame, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def atomic_json(payload: dict, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


def fetch_enhanced_matches(pipeline) -> tuple[pd.DataFrame, dict]:
    """Fetch the tournament with extra-time and penalty fields preserved."""
    response = pipeline.requests.get(
        pipeline.API_URL,
        headers={"X-Auth-Token": pipeline.TOKEN},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    rows = []
    for match in payload.get("matches", []):
        score = match.get("score") or {}
        rows.append(
            {
                "match_id": match.get("id"),
                "utc_date": match.get("utcDate"),
                "status": match.get("status"),
                "stage": match.get("stage"),
                "group": match.get("group"),
                "matchday": match.get("matchday"),
                "minute": match.get("minute"),
                "injury_time": match.get("injuryTime"),
                "home_team": pipeline.nested_get(match, ["homeTeam", "name"]),
                "away_team": pipeline.nested_get(match, ["awayTeam", "name"]),
                "winner": score.get("winner"),
                "duration": score.get("duration"),
                "home_score_full_time": pipeline.nested_get(
                    match, ["score", "fullTime", "home"]
                ),
                "away_score_full_time": pipeline.nested_get(
                    match, ["score", "fullTime", "away"]
                ),
                "home_score_regular_time": pipeline.nested_get(
                    match, ["score", "regularTime", "home"]
                ),
                "away_score_regular_time": pipeline.nested_get(
                    match, ["score", "regularTime", "away"]
                ),
                "home_score_extra_time": pipeline.nested_get(
                    match, ["score", "extraTime", "home"]
                ),
                "away_score_extra_time": pipeline.nested_get(
                    match, ["score", "extraTime", "away"]
                ),
                "home_score_penalties": pipeline.nested_get(
                    match, ["score", "penalties", "home"]
                ),
                "away_score_penalties": pipeline.nested_get(
                    match, ["score", "penalties", "away"]
                ),
                "last_updated": match.get("lastUpdated"),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("The World Cup API returned no matches.")
    frame["utc_date"] = pd.to_datetime(frame["utc_date"], errors="coerce", utc=True)
    frame["last_updated"] = pd.to_datetime(
        frame["last_updated"], errors="coerce", utc=True
    )
    for column in (
        "matchday",
        "minute",
        "injury_time",
        "home_score_full_time",
        "away_score_full_time",
        "home_score_regular_time",
        "away_score_regular_time",
        "home_score_extra_time",
        "away_score_extra_time",
        "home_score_penalties",
        "away_score_penalties",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.sort_values(["utc_date", "match_id"]).reset_index(drop=True)
    metadata = {
        "http_status": response.status_code,
        "matches_returned": len(frame),
        "requests_remaining": (
            response.headers.get("X-RequestsAvailable")
            or response.headers.get("X-Requests-Available-Minute")
        ),
        "request_counter_reset": response.headers.get("X-RequestCounter-Reset"),
    }
    return frame, metadata


def is_knockout_stage(stage) -> bool:
    return str(stage) in KNOCKOUT_STAGES


def active_knockout_matches(matches: pd.DataFrame) -> pd.DataFrame:
    return matches.loc[
        matches["stage"].map(is_knockout_stage)
        & matches["status"].isin(ACTIVE_STATUSES)
    ].copy()


def decision_method(match) -> str:
    duration = str(getattr(match, "duration", "") or "").upper()
    if duration in {"PENALTY_SHOOTOUT", "PENALTIES", "PENALTY"}:
        return "penalties"
    if duration in {"EXTRA_TIME", "EXTRA-TIME"}:
        return "extra_time"
    if pd.notna(getattr(match, "home_score_penalties", np.nan)):
        return "penalties"
    return "regular_time"


def advancing_team(match) -> str:
    winner = str(getattr(match, "winner", "") or "").upper()
    if winner == "HOME_TEAM":
        return str(match.home_team)
    if winner == "AWAY_TEAM":
        return str(match.away_team)

    home_penalties = getattr(match, "home_score_penalties", np.nan)
    away_penalties = getattr(match, "away_score_penalties", np.nan)
    if pd.notna(home_penalties) and pd.notna(away_penalties):
        if int(home_penalties) > int(away_penalties):
            return str(match.home_team)
        if int(away_penalties) > int(home_penalties):
            return str(match.away_team)

    home_score = getattr(match, "home_score_full_time", np.nan)
    away_score = getattr(match, "away_score_full_time", np.nan)
    if pd.notna(home_score) and pd.notna(away_score):
        if int(home_score) > int(away_score):
            return str(match.home_team)
        if int(away_score) > int(home_score):
            return str(match.away_team)
    raise KnockoutProcessingError(
        f"Finished knockout match {match.match_id} has no resolvable winner"
    )


def elo_actual_home_score(match) -> float:
    if decision_method(match) == "penalties":
        return 0.5
    home_score = int(match.home_score_full_time)
    away_score = int(match.away_score_full_time)
    if home_score > away_score:
        return 1.0
    if home_score < away_score:
        return 0.0
    raise KnockoutProcessingError(
        f"Non-penalty knockout match {match.match_id} ended level"
    )


def _state_defaults(pipeline) -> dict:
    return {
        "matches": 0,
        "ema_goals_for": pipeline.INITIAL_GOALS_AVERAGE,
        "ema_goals_against": pipeline.INITIAL_GOALS_AVERAGE,
        "ema_points": pipeline.INITIAL_POINTS_AVERAGE,
        "last_date": pd.NaT,
    }


def apply_new_finished_knockout_matches(
    matches: pd.DataFrame,
    team_map: pd.DataFrame,
    live_elo: pd.DataFrame,
    live_team_state: pd.DataFrame,
    processed_ledger: pd.DataFrame,
    pipeline,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict]]:
    """Update Elo and form for newly completed knockout matches once only."""
    name_lookup = dict(zip(team_map["live_team_name"], team_map["historical_team_name"]))
    rating_lookup = dict(zip(live_elo["team"], live_elo["elo_rating"]))
    state_lookup = live_team_state.set_index("team").to_dict(orient="index")
    processed_ids = set(
        pd.to_numeric(
            processed_ledger.get("match_id", pd.Series(dtype=float)), errors="coerce"
        ).dropna().astype(int)
    )
    finished = matches.loc[
        matches["stage"].map(is_knockout_stage)
        & (matches["status"] == "FINISHED")
        & matches["home_team"].notna()
        & matches["away_team"].notna()
        & matches["home_score_full_time"].notna()
        & matches["away_score_full_time"].notna()
    ].sort_values("utc_date")
    new_matches = finished.loc[
        ~finished["match_id"].astype(int).isin(processed_ids)
    ].reset_index(drop=True)

    ledger_rows: list[dict] = []
    audit_rows: list[dict] = []

    def get_state(team: str) -> dict:
        if team not in state_lookup:
            state_lookup[team] = _state_defaults(pipeline)
        return state_lookup[team]

    for match in new_matches.itertuples(index=False):
        home_live = str(match.home_team)
        away_live = str(match.away_team)
        home_team = name_lookup.get(home_live, home_live)
        away_team = name_lookup.get(away_live, away_live)
        home_score = int(match.home_score_full_time)
        away_score = int(match.away_score_full_time)
        home_before = float(rating_lookup.get(home_team, pipeline.INITIAL_RATING))
        away_before = float(rating_lookup.get(away_team, pipeline.INITIAL_RATING))
        host_adjustment = 0.0
        if home_live in pipeline.WORLD_CUP_HOSTS:
            host_adjustment += pipeline.HOST_ELO_ADJUSTMENT
        if away_live in pipeline.WORLD_CUP_HOSTS:
            host_adjustment -= pipeline.HOST_ELO_ADJUSTMENT
        expected_home = pipeline.elo_expected_score(
            home_before, away_before, host_adjustment=host_adjustment
        )
        actual_home = elo_actual_home_score(match)
        margin_multiplier = (
            1.0
            if decision_method(match) == "penalties"
            else pipeline.goal_margin_multiplier(home_score, away_score)
        )
        rating_change = pipeline.WORLD_CUP_K * margin_multiplier * (
            actual_home - expected_home
        )
        rating_lookup[home_team] = home_before + rating_change
        rating_lookup[away_team] = away_before - rating_change

        home_state = get_state(home_team)
        away_state = get_state(away_team)
        home_points = pipeline.points_from_score(home_score, away_score)
        away_points = pipeline.points_from_score(away_score, home_score)
        for state, goals_for, goals_against, points in (
            (home_state, home_score, away_score, home_points),
            (away_state, away_score, home_score, away_points),
        ):
            state["ema_goals_for"] = (
                pipeline.STATE_ALPHA * goals_for
                + (1 - pipeline.STATE_ALPHA) * float(state["ema_goals_for"])
            )
            state["ema_goals_against"] = (
                pipeline.STATE_ALPHA * goals_against
                + (1 - pipeline.STATE_ALPHA) * float(state["ema_goals_against"])
            )
            state["ema_points"] = (
                pipeline.STATE_ALPHA * points
                + (1 - pipeline.STATE_ALPHA) * float(state["ema_points"])
            )
            state["matches"] = int(state["matches"]) + 1
            state["last_date"] = match.utc_date

        method = decision_method(match)
        advanced = advancing_team(match)
        processed_at = datetime.now(timezone.utc).isoformat()
        ledger_rows.append(
            {
                "match_id": int(match.match_id),
                "utc_date": match.utc_date,
                "stage": str(match.stage),
                "home_team": home_live,
                "away_team": away_live,
                "home_score": home_score,
                "away_score": away_score,
                "duration": getattr(match, "duration", None),
                "decision_method": method,
                "advancing_team": advanced,
                "home_penalties": getattr(match, "home_score_penalties", None),
                "away_penalties": getattr(match, "away_score_penalties", None),
                "processed_at_utc": processed_at,
                "model_version": MODEL_VERSION,
            }
        )
        audit_rows.append(
            {
                "match_id": int(match.match_id),
                "stage": str(match.stage),
                "home_team": home_live,
                "away_team": away_live,
                "home_score": home_score,
                "away_score": away_score,
                "duration": getattr(match, "duration", None),
                "decision_method": method,
                "advancing_team": advanced,
                "home_penalties": getattr(match, "home_score_penalties", None),
                "away_penalties": getattr(match, "away_score_penalties", None),
                "home_elo_change": rating_change,
                "away_elo_change": -rating_change,
            }
        )

    elo_updated = pd.DataFrame(
        {"team": list(rating_lookup), "elo_rating": list(rating_lookup.values())}
    ).sort_values("elo_rating", ascending=False).reset_index(drop=True)
    elo_updated["rank"] = np.arange(1, len(elo_updated) + 1)
    state_updated = pd.DataFrame(
        [
            {
                "team": team,
                "matches": int(state["matches"]),
                "ema_goals_for": float(state["ema_goals_for"]),
                "ema_goals_against": float(state["ema_goals_against"]),
                "ema_points": float(state["ema_points"]),
                "last_date": state["last_date"],
            }
            for team, state in state_lookup.items()
        ]
    ).sort_values("team").reset_index(drop=True)
    if ledger_rows:
        processed_ledger = pd.concat(
            [processed_ledger, pd.DataFrame(ledger_rows)], ignore_index=True, sort=False
        ).drop_duplicates(subset=["match_id"], keep="first")
        processed_ledger = processed_ledger.sort_values("utc_date").reset_index(drop=True)
    return elo_updated, state_updated, processed_ledger, new_matches, audit_rows


def _stage_rows(matches: pd.DataFrame, stage_key: str) -> pd.DataFrame:
    return matches.loc[
        matches["stage"].astype(str).isin(STAGE_ALIASES[stage_key])
    ].sort_values(["utc_date", "match_id"]).reset_index(drop=True)


def logical_match_map(matches: pd.DataFrame, locked_bracket: pd.DataFrame) -> dict[int, int]:
    mapping = dict(
        zip(
            locked_bracket["api_match_id"].astype(int),
            locked_bracket["bracket_match_number"].astype(int),
        )
    )
    for stage_key, logical_numbers in LOGICAL_NUMBERS.items():
        rows = _stage_rows(matches, stage_key)
        if len(rows) > len(logical_numbers):
            raise KnockoutProcessingError(
                f"Too many {stage_key} fixtures: {len(rows)}"
            )
        for logical_number, match_id in zip(logical_numbers, rows["match_id"]):
            mapping[int(match_id)] = int(logical_number)
    return mapping


def build_actual_results(
    matches: pd.DataFrame,
    locked_bracket: pd.DataFrame,
) -> dict[int, dict]:
    mapping = logical_match_map(matches, locked_bracket)
    results: dict[int, dict] = {}
    finished = matches.loc[
        matches["stage"].map(is_knockout_stage)
        & (matches["status"] == "FINISHED")
        & matches["home_team"].notna()
        & matches["away_team"].notna()
    ]
    for match in finished.itertuples(index=False):
        logical = mapping.get(int(match.match_id))
        if logical is None:
            continue
        winner = advancing_team(match)
        loser = (
            str(match.away_team)
            if winner == str(match.home_team)
            else str(match.home_team)
        )
        results[logical] = {
            "logical_match_number": logical,
            "api_match_id": int(match.match_id),
            "stage": str(match.stage),
            "home_team": str(match.home_team),
            "away_team": str(match.away_team),
            "winner": winner,
            "loser": loser,
            "decision_method": decision_method(match),
            "home_score": int(match.home_score_full_time),
            "away_score": int(match.away_score_full_time),
            "home_penalties": getattr(match, "home_score_penalties", None),
            "away_penalties": getattr(match, "away_score_penalties", None),
        }
    return results


def _is_resolved_team(value) -> bool:
    if value is None or pd.isna(value):
        return False
    team = str(value).strip()
    normalized = team.upper()
    if normalized in {"", "TBD", "UNKNOWN", "NONE", "NAN", "N/A"}:
        return False
    return not normalized.startswith(("WINNER OF", "LOSER OF"))


def hydrate_medal_fixture_teams(
    matches: pd.DataFrame,
    locked_bracket: pd.DataFrame,
) -> pd.DataFrame:
    """Fill third-place and final participants from completed semifinals.

    Some provider snapshots keep a future fixture slot empty after its source match
    has finished. The completed bracket result is authoritative for that slot. A
    conflicting populated provider value is rejected instead of silently replaced.
    """
    if matches.empty:
        return matches.copy()

    output = matches.copy()
    mapping = logical_match_map(output, locked_bracket)
    row_by_logical = {
        logical: index
        for index, match_id in output["match_id"].items()
        if (logical := mapping.get(int(match_id))) is not None
    }
    actual_results = build_actual_results(output, locked_bracket)

    for target, (participant_key, sources) in MEDAL_FIXTURE_SOURCES.items():
        target_index = row_by_logical.get(target)
        if target_index is None:
            continue
        for column, source in zip(("home_team", "away_team"), sources):
            source_result = actual_results.get(source)
            if source_result is None:
                continue
            expected = source_result.get(participant_key)
            if not _is_resolved_team(expected):
                continue

            current = output.at[target_index, column]
            if _is_resolved_team(current):
                if str(current).strip().casefold() != str(expected).strip().casefold():
                    raise KnockoutProcessingError(
                        f"Logical match {target} {column} is {current!r}, but the "
                        f"completed bracket requires {expected!r}."
                    )
                continue
            output.at[target_index, column] = expected

    return output


def build_knockout_progress(
    matches: pd.DataFrame,
    locked_bracket: pd.DataFrame,
) -> pd.DataFrame:
    mapping = logical_match_map(matches, locked_bracket)
    rows = []
    knockout = matches.loc[matches["stage"].map(is_knockout_stage)]
    for match in knockout.itertuples(index=False):
        logical = mapping.get(int(match.match_id))
        rows.append(
            {
                "logical_match_number": logical,
                "api_match_id": int(match.match_id),
                "stage": str(match.stage),
                "utc_date": match.utc_date,
                "status": str(match.status),
                "home_team": getattr(match, "home_team", None),
                "away_team": getattr(match, "away_team", None),
                "home_score": getattr(match, "home_score_full_time", None),
                "away_score": getattr(match, "away_score_full_time", None),
                "duration": getattr(match, "duration", None),
                "decision_method": (
                    decision_method(match)
                    if str(match.status) == "FINISHED"
                    else None
                ),
                "advancing_team": (
                    advancing_team(match)
                    if str(match.status) == "FINISHED"
                    else None
                ),
                "home_penalties": getattr(match, "home_score_penalties", None),
                "away_penalties": getattr(match, "away_score_penalties", None),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["logical_match_number", "utc_date"], na_position="last"
    ).reset_index(drop=True)


def input_fingerprint(
    matches: pd.DataFrame,
    locked_bracket: pd.DataFrame,
    live_elo: pd.DataFrame,
) -> str:
    match_columns = [
        "match_id",
        "utc_date",
        "status",
        "stage",
        "home_team",
        "away_team",
        "winner",
        "duration",
        "home_score_full_time",
        "away_score_full_time",
        "home_score_penalties",
        "away_score_penalties",
        "last_updated",
    ]
    knockout = matches.loc[
        matches["stage"].map(is_knockout_stage), match_columns
    ].copy()
    knockout = knockout.sort_values("match_id").astype(str)
    bracket = locked_bracket.sort_values("bracket_match_number").astype(str)
    elo = live_elo[["team", "elo_rating"]].sort_values("team").astype(str)
    payload = "\n---\n".join(
        [
            knockout.to_csv(index=False, lineterminator="\n"),
            bracket.to_csv(index=False, lineterminator="\n"),
            elo.to_csv(index=False, lineterminator="\n"),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
