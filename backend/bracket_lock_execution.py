"""Execute the immutable bracket lock from the runner's fresh API response."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

try:
    from . import bracket_lock_store as store
except ImportError:
    import bracket_lock_store as store


def lock_official_bracket_from_matches(
    repo_root: Path,
    matches: pd.DataFrame,
) -> dict:
    if not store.bracket_lock_enabled():
        return {"status": "disabled"}
    if not store.group_stage_is_complete(matches):
        return {"status": "waiting_for_group_stage_completion"}

    round_32 = store._round_32_matches(matches)
    if len(round_32) != store.EXPECTED_ROUND_32_MATCHES:
        return {
            "status": "waiting_for_official_round_32_fixtures",
            "fixtures_found": int(len(round_32)),
        }
    if not all(
        round_32[column].map(store._valid_team_name).all()
        for column in ("home_team", "away_team")
    ):
        return {"status": "waiting_for_official_round_32_teams"}

    data_dir = repo_root / "data"
    tables_path = data_dir / "current_group_tables.csv"
    if not tables_path.exists():
        return {"status": "waiting_for_final_group_tables"}

    group_tables = pd.read_csv(tables_path)
    proposed = store.build_official_bracket(matches, group_tables)
    fingerprint = store.bracket_fingerprint(proposed)
    generated_at = datetime.now(timezone.utc).isoformat()

    lock_path = data_dir / "official_round_32_bracket_locked.csv"
    state_path = data_dir / "official_round_32_bracket_lock.json"
    if lock_path.exists():
        existing = pd.read_csv(lock_path)
        if not store._same_locked_bracket(existing, proposed):
            raise store.BracketLockError(
                "Official Round-of-32 fixtures conflict with the existing immutable lock"
            )
        status = "already_locked"
    else:
        store._atomic_csv(proposed, lock_path)
        store._atomic_json(
            {
                "status": "locked",
                "locked_at_utc": generated_at,
                "source": "official_football_data_api",
                "bracket_mode": "official_api_locked",
                "fixture_count": store.EXPECTED_ROUND_32_MATCHES,
                "team_count": store.EXPECTED_ROUND_32_TEAMS,
                "fingerprint": fingerprint,
            },
            state_path,
        )
        status = "locked"

    opponents, paths = store._confirmed_probability_outputs(
        proposed,
        group_tables,
        generated_at,
    )
    store._atomic_csv(
        opponents,
        data_dir / "round_32_opponent_probabilities_latest.csv",
    )
    store._atomic_csv(
        paths,
        data_dir / "round_32_path_status_latest.csv",
    )
    store._atomic_json(
        {
            "status": "official_bracket_locked",
            "generated_at_utc": generated_at,
            "number_of_simulations": 0,
            "teams": store.EXPECTED_ROUND_32_TEAMS,
            "opponent_rows": store.EXPECTED_ROUND_32_TEAMS,
            "fixture_status_counts": paths["fixture_status"].value_counts().to_dict(),
            "bracket_mode": "official_api_locked",
            "fingerprint": fingerprint,
        },
        data_dir / "round_32_opponent_probabilities_metadata.json",
    )
    return {
        "status": status,
        "fixture_count": store.EXPECTED_ROUND_32_MATCHES,
        "team_count": store.EXPECTED_ROUND_32_TEAMS,
        "fingerprint": fingerprint,
    }
