"""Safe entry point for the CupMarket automated backend."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

try:
    from . import update_pipeline
except ImportError:  # Script execution: python backend/run_update_pipeline.py
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
                    result[column],
                    errors="coerce",
                    utc=True,
                    format="mixed",
                )

    return result


update_pipeline.pd.concat = concat_with_normalized_timestamps


def active_group_matches(world_cup: pd.DataFrame) -> pd.DataFrame:
    """Return active group matches that make official publication unsafe."""
    required = {"match_id", "stage", "status", "home_team", "away_team"}
    missing = required - set(world_cup.columns)
    if missing:
        raise ValueError(
            "Cannot evaluate the official-update safety gate; missing columns: "
            + ", ".join(sorted(missing))
        )

    active = world_cup[
        (world_cup["stage"] == "GROUP_STAGE")
        & world_cup["status"].isin(ACTIVE_GROUP_MATCH_STATUSES)
    ].copy()

    sort_columns = [
        column for column in ("utc_date", "match_id") if column in active.columns
    ]
    if sort_columns:
        active = active.sort_values(sort_columns)
    return active.reset_index(drop=True)


def _iso_timestamp(value) -> str | None:
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    return timestamp.isoformat() if pd.notna(timestamp) else None


def active_match_records(active_matches: pd.DataFrame) -> list[dict]:
    """Return JSON-safe details for logs and operational diagnosis."""
    records = []
    for match in active_matches.itertuples(index=False):
        records.append(
            {
                "match_id": int(match.match_id),
                "group": getattr(match, "group", None),
                "status": str(match.status),
                "home_team": str(match.home_team),
                "away_team": str(match.away_team),
                "kickoff_utc": _iso_timestamp(getattr(match, "utc_date", None)),
                "last_updated_utc": _iso_timestamp(
                    getattr(match, "last_updated", None)
                ),
            }
        )
    return records


def deferred_run_summary(
    active_matches: pd.DataFrame,
    api_metadata: dict,
) -> dict:
    """Describe a safe deferral without claiming that the model failed."""
    return {
        "status": "deferred_active_group_matches",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "active_group_match_count": int(len(active_matches)),
        "active_group_matches": active_match_records(active_matches),
        "number_of_simulations": update_pipeline.N_SIMULATIONS,
        "api": api_metadata,
        "message": (
            "Official ratings, tournament probabilities and country prices were "
            "not changed because at least one group-stage match is still active. "
            "The next scheduled run will retry automatically."
        ),
    }


def run_guarded_pipeline() -> bool:
    """Run the official model only from a coherent, non-live group snapshot.

    Returns True when the normal pipeline ran and False when publication was
    safely deferred. The fetched API snapshot is reused by the normal pipeline,
    so the safety check does not consume a second API request.
    """
    world_cup, api_metadata = update_pipeline.fetch_world_cup_matches()
    active_matches = active_group_matches(world_cup)

    if not active_matches.empty:
        summary = deferred_run_summary(active_matches, api_metadata)
        update_pipeline.atomic_to_json(
            summary,
            update_pipeline.RUN_SUMMARY_PATH,
        )
        print(
            "Official CupMarket update deferred; active group matches:",
            len(active_matches),
        )
        for match in summary["active_group_matches"]:
            print(
                f'- {match["group"]}: {match["home_team"]} vs '
                f'{match["away_team"]} ({match["status"]})'
            )
        return False

    original_fetch = update_pipeline.fetch_world_cup_matches
    update_pipeline.fetch_world_cup_matches = lambda: (
        world_cup.copy(deep=True),
        dict(api_metadata),
    )
    try:
        update_pipeline.main()
    finally:
        update_pipeline.fetch_world_cup_matches = original_fetch
    return True


if __name__ == "__main__":
    run_guarded_pipeline()
