"""Compatibility entry point for the CupMarket automated backend."""

from __future__ import annotations

import pandas as pd

import update_pipeline


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


if __name__ == "__main__":
    update_pipeline.main()
