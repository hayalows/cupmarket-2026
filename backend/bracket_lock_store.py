"""Lock the official Round-of-32 bracket after the group stage is complete.

The official football data feed is the source of truth for populated knockout
fixtures. This module never guesses the final third-place allocation.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os

import pandas as pd


GROUP_STAGE = "GROUP_STAGE"
ROUND_32_STAGES = {"LAST_32", "ROUND_OF_32", "R32"}
EXPECTED_GROUP_MATCHES = 72
EXPECTED_ROUND_32_MATCHES = 16
EXPECTED_ROUND_32_TEAMS = 32
IMMUTABLE_BRACKET_COLUMNS = [
    "api_match_id",
    "home_team",
    "away_team",
    "home_source_slot",
    "away_source_slot",
]


class BracketLockError(RuntimeError):
    """Raised when official bracket data is incomplete or conflicts with a lock."""


def bracket_lock_enabled() -> bool:
    return os.environ.get("ENABLE_EXACT_BRACKET_LOCK", "true").lower() in {
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


def _atomic_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


def group_stage_is_complete(matches: pd.DataFrame) -> bool:
    group_matches = matches.loc[matches["stage"] == GROUP_STAGE].copy()
    if len(group_matches) != EXPECTED_GROUP_MATCHES:
        return False
    finished = (
        (group_matches["status"] == "FINISHED")
        & group_matches["home_score_full_time"].notna()
        & group_matches["away_score_full_time"].notna()
    )
    return bool(finished.all())


def _round_32_matches(matches: pd.DataFrame) -> pd.DataFrame:
    return (
        matches.loc[matches["stage"].astype(str).isin(ROUND_32_STAGES)]
        .sort_values(["utc_date", "match_id"])
        .reset_index(drop=True)
    )


def _valid_team_name(value) -> bool:
    if value is None or pd.isna(value):
        return False
    normalized = str(value).strip().lower()
    return normalized not in {"", "tbd", "to be decided", "winner", "unknown"}


def _position_lookup(group_tables: pd.DataFrame) -> dict[str, str]:
    required = {"team", "group", "position"}
    missing = required - set(group_tables.columns)
    if missing:
        raise BracketLockError(
            "Current group tables are missing columns: " + ", ".join(sorted(missing))
        )
    return {
        str(row.team): f"{int(row.position)}{str(row.group)}"
        for row in group_tables.itertuples(index=False)
    }


def build_official_bracket(
    matches: pd.DataFrame,
    group_tables: pd.DataFrame,
) -> pd.DataFrame:
    if not group_stage_is_complete(matches):
        raise BracketLockError("The group stage is not complete")

    round_32 = _round_32_matches(matches)
    if len(round_32) != EXPECTED_ROUND_32_MATCHES:
        raise BracketLockError(
            f"Expected {EXPECTED_ROUND_32_MATCHES} Round-of-32 fixtures, "
            f"found {len(round_32)}"
        )

    for column in ("home_team", "away_team"):
        invalid = ~round_32[column].map(_valid_team_name)
        if invalid.any():
            bad_ids = round_32.loc[invalid, "match_id"].astype(str).tolist()
            raise BracketLockError(
                f"Round-of-32 fixtures still contain unresolved {column} values "
                f"for matches: {', '.join(bad_ids)}"
            )

    all_teams = list(round_32["home_team"].astype(str)) + list(
        round_32["away_team"].astype(str)
    )
    if len(set(all_teams)) != EXPECTED_ROUND_32_TEAMS:
        raise BracketLockError(
            "The official Round-of-32 bracket must contain 32 unique teams"
        )

    slot_lookup = _position_lookup(group_tables)
    missing_slots = sorted(set(all_teams) - set(slot_lookup))
    if missing_slots:
        raise BracketLockError(
            "Round-of-32 teams are missing from final group tables: "
            + ", ".join(missing_slots)
        )

    output = pd.DataFrame(
        {
            "bracket_match_number": range(73, 89),
            "api_match_id": round_32["match_id"].astype(int),
            "utc_date": round_32["utc_date"].astype(str),
            "status": round_32["status"].astype(str),
            "home_team": round_32["home_team"].astype(str),
            "away_team": round_32["away_team"].astype(str),
        }
    )
    output["home_source_slot"] = output["home_team"].map(slot_lookup)
    output["away_source_slot"] = output["away_team"].map(slot_lookup)
    output["fixture_status"] = "confirmed"
    output["bracket_mode"] = "official_api_locked"
    return output


def immutable_bracket_identity(bracket: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in IMMUTABLE_BRACKET_COLUMNS if column not in bracket]
    if missing:
        raise BracketLockError(
            "Bracket lock comparison is missing columns: " + ", ".join(missing)
        )

    canonical = bracket[IMMUTABLE_BRACKET_COLUMNS].copy()
    canonical["api_match_id"] = (
        pd.to_numeric(canonical["api_match_id"], errors="coerce")
        .astype("Int64")
        .astype(str)
    )
    for column in (
        "home_team",
        "away_team",
        "home_source_slot",
        "away_source_slot",
    ):
        canonical[column] = canonical[column].astype(str).str.strip()
    return canonical.sort_values("api_match_id").reset_index(drop=True)


def bracket_fingerprint(bracket: pd.DataFrame) -> str:
    canonical = immutable_bracket_identity(bracket)
    payload = canonical.to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _same_locked_bracket(existing: pd.DataFrame, proposed: pd.DataFrame) -> bool:
    return bracket_fingerprint(existing) == bracket_fingerprint(proposed)


def _confirmed_probability_outputs(
    bracket: pd.DataFrame,
    group_tables: pd.DataFrame,
    generated_at: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    group_lookup = dict(
        zip(group_tables["team"].astype(str), group_tables["group"].astype(str))
    )
    position_lookup = dict(
        zip(group_tables["team"].astype(str), group_tables["position"].astype(int))
    )

    opponent_rows = []
    path_rows = []
    for fixture in bracket.itertuples(index=False):
        pairs = (
            (fixture.home_team, fixture.away_team),
            (fixture.away_team, fixture.home_team),
        )
        for team, opponent in pairs:
            opponent_rows.append(
                {
                    "team": team,
                    "team_group": group_lookup[team],
                    "opponent": opponent,
                    "opponent_group": group_lookup[opponent],
                    "pairing_count": 1,
                    "probability_unconditional": 1.0,
                    "probability_given_qualification": 1.0,
                    "qualification_count": 1,
                    "number_of_simulations": 0,
                    "generated_at_utc": generated_at,
                    "model_version": "official_bracket_lock",
                    "bracket_mode": "official_api_locked",
                }
            )
            path_rows.append(
                {
                    "team": team,
                    "group": group_lookup[team],
                    "fixture_status": "confirmed",
                    "confirmed_slot": f"{position_lookup[team]}{group_lookup[team]}",
                    "round_32_match_id": int(fixture.bracket_match_number),
                    "current_group_position": int(position_lookup[team]),
                    "group_complete": True,
                    "prob_reach_round_32": 1.0,
                    "prob_eliminated": 0.0,
                    "most_likely_opponent": opponent,
                    "most_likely_opponent_probability_unconditional": 1.0,
                    "most_likely_opponent_probability_given_qualification": 1.0,
                    "prob_finish_1st_group": float(position_lookup[team] == 1),
                    "prob_finish_2nd_group": float(position_lookup[team] == 2),
                    "prob_finish_3rd_group": float(position_lookup[team] == 3),
                    "prob_finish_4th_group": 0.0,
                    "number_of_simulations": 0,
                    "generated_at_utc": generated_at,
                    "model_version": "official_bracket_lock",
                    "bracket_mode": "official_api_locked",
                }
            )

    qualified = set(group_lookup)
    bracket_teams = set(bracket["home_team"]).union(bracket["away_team"])
    eliminated = qualified - bracket_teams
    for team in sorted(eliminated):
        position = int(position_lookup[team])
        path_rows.append(
            {
                "team": team,
                "group": group_lookup[team],
                "fixture_status": "eliminated",
                "confirmed_slot": None,
                "round_32_match_id": None,
                "current_group_position": position,
                "group_complete": True,
                "prob_reach_round_32": 0.0,
                "prob_eliminated": 1.0,
                "most_likely_opponent": None,
                "most_likely_opponent_probability_unconditional": 0.0,
                "most_likely_opponent_probability_given_qualification": 0.0,
                "prob_finish_1st_group": float(position == 1),
                "prob_finish_2nd_group": float(position == 2),
                "prob_finish_3rd_group": float(position == 3),
                "prob_finish_4th_group": float(position == 4),
                "number_of_simulations": 0,
                "generated_at_utc": generated_at,
                "model_version": "official_bracket_lock",
                "bracket_mode": "official_api_locked",
            }
        )

    return pd.DataFrame(opponent_rows), pd.DataFrame(path_rows)


def lock_official_bracket(repo_root: Path) -> dict:
    if not bracket_lock_enabled():
        return {"status": "disabled"}

    data_dir = repo_root / "data"
    matches_path = data_dir / "world_cup_2026_matches_latest.csv"
    tables_path = data_dir / "current_group_tables.csv"
    if not matches_path.exists() or not tables_path.exists():
        raise FileNotFoundError("Latest matches or current group tables are missing")

    matches = pd.read_csv(matches_path)
    if not group_stage_is_complete(matches):
        return {"status": "waiting_for_group_stage_completion"}

    round_32 = _round_32_matches(matches)
    if len(round_32) != EXPECTED_ROUND_32_MATCHES:
        return {
            "status": "waiting_for_official_round_32_fixtures",
            "fixtures_found": int(len(round_32)),
        }
    if not all(
        round_32[column].map(_valid_team_name).all()
        for column in ("home_team", "away_team")
    ):
        return {"status": "waiting_for_official_round_32_teams"}

    group_tables = pd.read_csv(tables_path)
    proposed = build_official_bracket(matches, group_tables)
    fingerprint = bracket_fingerprint(proposed)

    lock_path = data_dir / "official_round_32_bracket_locked.csv"
    state_path = data_dir / "official_round_32_bracket_lock.json"
    generated_at = datetime.now(timezone.utc).isoformat()

    if lock_path.exists():
        existing = pd.read_csv(lock_path)
        if not _same_locked_bracket(existing, proposed):
            raise BracketLockError(
                "Official Round-of-32 fixtures conflict with the existing immutable lock"
            )
        confirmed_bracket = existing
        status = "already_locked"
    else:
        _atomic_csv(proposed, lock_path)
        _atomic_json(
            {
                "status": "locked",
                "locked_at_utc": generated_at,
                "source": "official_football_data_api",
                "bracket_mode": "official_api_locked",
                "fixture_count": EXPECTED_ROUND_32_MATCHES,
                "team_count": EXPECTED_ROUND_32_TEAMS,
                "fingerprint": fingerprint,
            },
            state_path,
        )
        confirmed_bracket = proposed
        status = "locked"

    opponents, paths = _confirmed_probability_outputs(
        confirmed_bracket, group_tables, generated_at
    )
    _atomic_csv(
        opponents,
        data_dir / "round_32_opponent_probabilities_latest.csv",
    )
    _atomic_csv(paths, data_dir / "round_32_path_status_latest.csv")
    _atomic_json(
        {
            "status": "official_bracket_locked",
            "generated_at_utc": generated_at,
            "number_of_simulations": 0,
            "teams": EXPECTED_ROUND_32_TEAMS,
            "opponent_rows": EXPECTED_ROUND_32_TEAMS,
            "fixture_status_counts": paths["fixture_status"].value_counts().to_dict(),
            "bracket_mode": "official_api_locked",
            "fingerprint": fingerprint,
        },
        data_dir / "round_32_opponent_probabilities_metadata.json",
    )

    return {
        "status": status,
        "fixture_count": EXPECTED_ROUND_32_MATCHES,
        "team_count": EXPECTED_ROUND_32_TEAMS,
        "fingerprint": fingerprint,
    }
