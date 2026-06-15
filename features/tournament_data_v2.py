from __future__ import annotations

from pathlib import Path

import pandas as pd

from features.official_data import load_latest_csv
from features.tournament_data import (
    DATA_DIR,
    HISTORY_DIR,
    ROOT,
    STATE_DIR,
    actual_outcome,
    batch_context_for_match,
    leading_outcome_label,
    latest_update_matches,
    outcome_probability,
    reference_prediction,
)


def load_csv(path: Path) -> pd.DataFrame:
    return load_latest_csv(path)


def load_market_history() -> pd.DataFrame:
    from features.tournament_data import load_market_history as load_local_history

    history = load_local_history()
    current = load_csv(DATA_DIR / "cupmarket_prices_latest.csv")
    if current.empty:
        return history
    combined = pd.concat([history, current], ignore_index=True, sort=False)
    required = ["team", "cupmarket_price", "generated_at_utc"]
    if not set(required).issubset(combined.columns):
        return history
    return (
        combined.dropna(subset=required)
        .drop_duplicates(["team", "generated_at_utc"], keep="last")
        .sort_values(["generated_at_utc", "team"])
        .reset_index(drop=True)
    )


def load_static_data() -> dict[str, pd.DataFrame]:
    return {
        "prices": load_csv(DATA_DIR / "cupmarket_prices_latest.csv"),
        "latest_predictions": load_csv(
            DATA_DIR / "world_cup_live_predictions_latest.csv"
        ),
        "prediction_ledger": load_csv(
            STATE_DIR / "world_cup_prediction_ledger.csv"
        ),
        "processed_ledger": load_csv(
            STATE_DIR / "world_cup_processed_match_ledger.csv"
        ),
        "history": load_market_history(),
    }
