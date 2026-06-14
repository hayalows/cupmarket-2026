from __future__ import annotations

import streamlit as st

import features.model_performance as base
from features.tournament_data import load_csv, load_static_data


def render_model_performance() -> None:
    """Render the scorecard from cached repository snapshots, without a live API call."""
    matches = load_csv(base.MATCHES_PATH)
    static = load_static_data()
    rows = base._verified_match_rows(matches, static["prediction_ledger"])
    metrics = base._live_metrics(rows)
    historical = base._read_json(base.HISTORICAL_EVAL_PATH)

    st.markdown("### Model Performance")
    st.write(
        "The live 50% figure is only the top-outcome hit rate. This scorecard also checks "
        "whether the probabilities were sensible, how close expected goals were, and "
        "whether the score distribution covered what actually happened."
    )

    base._render_live_scorecard(rows, metrics)
    base._render_historical_reference(historical)
    base._render_match_detail(rows, metrics)
    base._render_calibration(rows)
    base._render_tournament_and_market_status(static["prices"])

    with st.expander("How to read the metrics", expanded=False):
        st.markdown(
            "**Leading-outcome hit rate** asks whether the single highest home/draw/away "
            "probability occurred.\n\n"
            "**Brier score** evaluates all three outcome probabilities; lower is better and "
            "zero is perfect.\n\n"
            "**Probability of what happened** is the average probability CupMarket assigned "
            "to the outcomes that actually occurred.\n\n"
            "**Goal MAE** is the average absolute difference between expected and actual "
            "goals for each team.\n\n"
            "**Top-3 score coverage** asks whether the actual score was among the three most "
            "likely scorelines, which is more informative than exact-score hits alone."
        )

    st.caption(
        "Performance uses the latest saved match snapshot. Only predictions recorded before "
        "kickoff are included, and model versions remain visible in the match-level table."
    )
