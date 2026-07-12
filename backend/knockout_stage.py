"""Public Phase 6 knockout-stage interface."""

from __future__ import annotations

import pandas as pd

try:
    from . import knockout_stage_data as _knockout_data
    from .knockout_stage_data import *  # noqa: F401,F403
    from .knockout_stage_simulation import *  # noqa: F401,F403
except ImportError:
    import knockout_stage_data as _knockout_data
    from knockout_stage_data import *  # noqa: F401,F403
    from knockout_stage_simulation import *  # noqa: F401,F403


KNOWN_MATCH_STATUSES = {
    "SCHEDULED",
    "TIMED",
    "IN_PLAY",
    "LIVE",
    "PAUSED",
    "SUSPENDED",
    "FINISHED",
    "AWARDED",
    "POSTPONED",
    "CANCELLED",
}
TERMINAL_WINNERS = {"HOME_TEAM", "AWAY_TEAM", "DRAW"}


def normalise_official_statuses(matches: pd.DataFrame) -> pd.DataFrame:
    """Recover a completed match when the provider sends a malformed status value.

    A result is changed to FINISHED only when the provider also supplies an official
    winner field and both final scores. Valid live, scheduled and terminal statuses
    are never overwritten.
    """
    if matches.empty or "status" not in matches.columns:
        return matches.copy()

    output = matches.copy()
    status = output["status"].fillna("").astype(str).str.strip().str.upper()
    winner = output.get("winner", pd.Series("", index=output.index)).fillna("").astype(str).str.upper()
    home_score = pd.to_numeric(output.get("home_score_full_time"), errors="coerce")
    away_score = pd.to_numeric(output.get("away_score_full_time"), errors="coerce")

    malformed = ~status.isin(KNOWN_MATCH_STATUSES)
    completed_evidence = (
        winner.isin(TERMINAL_WINNERS)
        & home_score.notna()
        & away_score.notna()
    )
    output.loc[malformed & completed_evidence, "status"] = "FINISHED"
    return output


def fetch_enhanced_matches(pipeline) -> tuple[pd.DataFrame, dict]:
    """Fetch knockout data and repair only strongly evidenced status corruption."""
    matches, metadata = _knockout_data.fetch_enhanced_matches(pipeline)
    return normalise_official_statuses(matches), metadata
