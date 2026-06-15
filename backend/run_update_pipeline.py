"""Safe entry point for the CupMarket automated backend."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

import numpy as np
import pandas as pd

try:
    from . import update_pipeline
except ImportError:
    import update_pipeline


ACTIVE_GROUP_MATCH_STATUSES = {"IN_PLAY", "PAUSED"}
PRICE_CHANGE_COLUMNS = [
    "previous_price",
    "price_change",
    "price_change_percent",
]

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


def _has_meaningful_change(frame: pd.DataFrame) -> bool:
    if frame.empty or "price_change" not in frame.columns:
        return False
    changes = pd.to_numeric(frame["price_change"], errors="coerce").fillna(0.0)
    return bool((changes.abs() > 1e-9).any())


def _load_price_anchor() -> pd.DataFrame:
    """Find the latest checkpoint that still describes a real market move."""
    current_path = update_pipeline.PRICES_OUTPUT_PATH
    if current_path.exists():
        current = pd.read_csv(current_path)
        if _has_meaningful_change(current):
            return current[["team", "previous_price"]].copy()

    history_dir = update_pipeline.HISTORY_DIR
    for path in sorted(
        history_dir.glob("cupmarket_prices_*.csv"), reverse=True
    ):
        try:
            checkpoint = pd.read_csv(path)
        except (OSError, pd.errors.ParserError):
            continue
        if _has_meaningful_change(checkpoint):
            return checkpoint[["team", "previous_price"]].copy()

    return pd.DataFrame(columns=["team", "previous_price"])


def _restore_meaningful_market_move(anchor: pd.DataFrame) -> None:
    """Keep the last real event movement after any no-new-result run."""
    if anchor.empty or not update_pipeline.PRICES_OUTPUT_PATH.exists():
        return

    summary_path = update_pipeline.RUN_SUMMARY_PATH
    if not summary_path.exists():
        return
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("status") not in {"updated", "no_new_finished_match"}:
        return
    if int(summary.get("new_finished_matches", 0) or 0) != 0:
        return

    prices = pd.read_csv(update_pipeline.PRICES_OUTPUT_PATH)
    prices = prices.drop(columns=PRICE_CHANGE_COLUMNS, errors="ignore")
    prices = prices.merge(anchor, on="team", how="left")
    prices["price_change"] = (
        pd.to_numeric(prices["cupmarket_price"], errors="coerce")
        - pd.to_numeric(prices["previous_price"], errors="coerce")
    )
    denominator = pd.to_numeric(prices["previous_price"], errors="coerce")
    prices["price_change_percent"] = np.where(
        denominator.abs() > 1e-12,
        100.0 * prices["price_change"] / denominator,
        np.nan,
    )
    update_pipeline.atomic_to_csv(prices, update_pipeline.PRICES_OUTPUT_PATH)

    completed_at = pd.to_datetime(
        summary.get("completed_at_utc"), errors="coerce", utc=True
    )
    if pd.notna(completed_at):
        history_path = (
            update_pipeline.HISTORY_DIR
            / f"cupmarket_prices_{completed_at.strftime('%Y%m%dT%H%M%SZ')}.csv"
        )
        if history_path.exists():
            update_pipeline.atomic_to_csv(prices, history_path)

    print("Preserved the latest meaningful market-price movement.")


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

    price_anchor = _load_price_anchor()
    update_pipeline.main()
    _restore_meaningful_market_move(price_anchor)
    return True


if __name__ == "__main__":
    run_guarded_pipeline()
