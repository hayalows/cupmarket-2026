from __future__ import annotations

import pandas as pd


def _rank_previous_prices(frame: pd.DataFrame) -> pd.Series:
    """Rebuild a stable sequential ranking from the prior official prices."""
    ranked = pd.DataFrame(
        {
            "row_index": frame.index,
            "team": frame.get("team", pd.Series("", index=frame.index)).astype(str),
            "previous_price": pd.to_numeric(
                frame.get("previous_price"), errors="coerce"
            ),
        }
    ).dropna(subset=["previous_price"])
    ranked = ranked.sort_values(
        ["previous_price", "team"],
        ascending=[False, True],
        kind="mergesort",
    )
    ranked["previous_market_rank"] = range(1, len(ranked) + 1)
    result = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    if not ranked.empty:
        result.loc[ranked["row_index"]] = ranked[
            "previous_market_rank"
        ].astype("Int64").to_numpy()
    return result


def add_rank_movement(prices: pd.DataFrame) -> pd.DataFrame:
    """Add previous rank and rank movement without mutating the source frame.

    Positive ``rank_change`` means a country moved up the market table. An
    explicit previous rank is used when the backend provides one. Older files
    are handled by rebuilding a stable sequential table from previous prices.
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
        ).astype("Int64")
    elif "previous_price" in frame.columns:
        previous_rank = _rank_previous_prices(frame)
    else:
        previous_rank = pd.Series(pd.NA, index=frame.index, dtype="Int64")

    frame["previous_market_rank"] = previous_rank
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
