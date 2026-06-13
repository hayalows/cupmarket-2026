"""Safe entry point for the CupMarket automated backend."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

try:
    from . import update_pipeline
except ImportError:
    import update_pipeline


ACTIVE_GROUP_MATCH_STATUSES = {"IN_PLAY", "PAUSED"}

_original_concat = update_pipeline.pd.concat


def concat_with_normalized_timestamps(*args, **kwargs):
    """Concatenate frames and normalize known UTC timestamp columns."""
    result = _original_concat(*args, **kwargs)
    if isinstance(result, pd.DataFrame):
        for column in (
            "utc_date",
            "generated_at_utc",
            "processed_at_utc",
            "last_updated",
        ):
            if column in result.columns:
                result[column] = pd.to_datetime(
                    result[column], errors="coerce", utc=True, format="mixed"
                )
    return result


update_pipeline.pd.concat = concat_with_normalized_timestamps


def active_group_matches(world_cup: pd.DataFrame) -> pd.DataFrame:
    """Return active group matches that block official model publication."""
    required = {"match_id", "stage", "status", "home_team", "away_team"}
    missing = required - set(world_cup.columns)
    if missing:
        raise ValueError(
            "Cannot evaluate the official-update safety gate; missing columns: "
            + ", ".join(sorted(missing))
        )
    return world_cup[
        (world_cup["stage"] == "GROUP_STAGE")
        & world_cup["status"].isin(ACTIVE_GROUP_MATCH_STATUSES)
    ].copy().reset_index(drop=True)


def deferred_run_summary(active_matches: pd.DataFrame, api_metadata: dict) -> dict:
    """Describe a safe delay without recording it as a model failure."""
    records = []
    for match in active_matches.itertuples(index=False):
        records.append(
            {
                "match_id": int(match.match_id),
                "group": getattr(match, "group", None),
                "status": str(match.status),
                "home_team": str(match.home_team),
                "away_team": str(match.away_team),
            }
        )
    return {
        "status": "deferred_active_group_matches",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "active_group_match_count": int(len(active_matches)),
        "active_group_matches": records,
        "number_of_simulations": update_pipeline.N_SIMULATIONS,
        "api": api_metadata,
        "message": (
            "Official ratings, tournament probabilities and country prices were "
            "not changed because a group-stage match is still active. The next "
            "scheduled run will retry automatically."
        ),
    }


def run_guarded_pipeline() -> bool:
    """Delay official publication while a group-stage match is active."""
    world_cup, api_metadata = update_pipeline.fetch_world_cup_matches()
    active_matches = active_group_matches(world_cup)
    if not active_matches.empty:
        update_pipeline.atomic_to_json(
            deferred_run_summary(active_matches, api_metadata),
            update_pipeline.RUN_SUMMARY_PATH,
        )
        print(
            "Official CupMarket update deferred; active group matches:",
            len(active_matches),
        )
        return False

    update_pipeline.main()
    return True


if __name__ == "__main__":
    run_guarded_pipeline()
