from __future__ import annotations

import pandas as pd


def add_rank_movement(prices: pd.DataFrame) -> pd.DataFrame:
    """Add previous rank and rank movement without mutating the source frame.

    Positive ``rank_change`` means a country moved up the market table.
    Previous rank is reconstructed from the previous official prices so the UI
    can explain movement even before the backend stores an explicit rank field.
    """
    frame = prices.copy()
    if frame.empty:
        frame["previous_market_rank"] = pd.Series(dtype="Int64")
        frame["rank_change"] = pd.Series(dtype="Int64")
        return frame

    current_rank = pd.to_numeric(frame.get("market_rank"), errors="coerce")
    frame["market_rank"] = current_rank.astype("Int64")

    if "previous_market_rank" in frame.columns:
        previous_rank = pd.to_numeric(
            frame["previous_market_rank"], errors="coerce"
        )
    elif "previous_price" in frame.columns:
        previous_price = pd.to_numeric(frame["previous_price"], errors="coerce")
        previous_rank = previous_price.rank(method="min", ascending=False)
        previous_rank = previous_rank.where(previous_price.notna())
    else:
        previous_rank = pd.Series(pd.NA, index=frame.index, dtype="Int64")

    frame["previous_market_rank"] = previous_rank.astype("Int64")
    frame["rank_change"] = (
        frame["previous_market_rank"] - frame["market_rank"]
    ).astype("Int64")
    return frame


def rank_movement_text(
    current_rank,
    previous_rank,
    *,
    include_previous: bool = False,
) -> str:
    """Return a plain-language rank movement label for the interface."""
    current = pd.to_numeric(current_rank, errors="coerce")
    previous = pd.to_numeric(previous_rank, errors="coerce")
    if pd.isna(current) or pd.isna(previous):
        return "Previous rank unavailable"

    current_int = int(current)
    previous_int = int(previous)
    movement = previous_int - current_int
    suffix = f" from #{previous_int}" if include_previous else ""

    if movement > 0:
        unit = "place" if movement == 1 else "places"
        return f"↑ {movement} {unit}{suffix}"
    if movement < 0:
        distance = abs(movement)
        unit = "place" if distance == 1 else "places"
        return f"↓ {distance} {unit}{suffix}"
    return f"No change{suffix}"
