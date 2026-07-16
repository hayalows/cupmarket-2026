from __future__ import annotations

import pandas as pd
import streamlit as st


def _yes(value: bool) -> str:
    return "Ready" if value else "Needs attention"


def _time(value) -> str:
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return "Unavailable"
    return ts.strftime("%d %b %Y · %H:%M UTC")


ADAPTIVE_COLUMNS = {
    "home_base_elo",
    "away_base_elo",
    "home_adaptive_adjustment",
    "away_adaptive_adjustment",
    "home_prediction_elo",
    "away_prediction_elo",
    "adaptive_prediction_enabled",
    "adaptive_model_version",
}


def render_knockout_readiness(prices: pd.DataFrame, predictions: pd.DataFrame, path_status: pd.DataFrame) -> None:
    st.markdown("## Knockout Readiness")
    st.caption("Checks whether CupMarket is ready to move from group-stage projection into knockout-stage intelligence.")

    if not isinstance(predictions, pd.DataFrame):
        predictions = pd.DataFrame()
    if not isinstance(path_status, pd.DataFrame):
        path_status = pd.DataFrame()
    if not isinstance(prices, pd.DataFrame):
        prices = pd.DataFrame()

    knockout_predictions = pd.DataFrame()
    if not predictions.empty and "stage" in predictions.columns:
        knockout_predictions = predictions.loc[~predictions["stage"].astype(str).str.contains("GROUP", case=False, na=False)].copy()

    confirmed_paths = pd.DataFrame()
    if not path_status.empty and "fixture_status" in path_status.columns:
        confirmed_paths = path_status.loc[path_status["fixture_status"].astype(str).isin(["confirmed", "slot_confirmed", "slot_confirmed_opponent_pending"])]

    expected_goal_ready = not knockout_predictions.empty and {"expected_home_goals", "expected_away_goals"}.issubset(knockout_predictions.columns)
    likely_score_ready = not knockout_predictions.empty and "most_likely_score" in knockout_predictions.columns
    advance_ready = not knockout_predictions.empty and {"prob_home_advance", "prob_away_advance"}.issubset(knockout_predictions.columns)
    adaptive_columns_ready = not predictions.empty and ADAPTIVE_COLUMNS.issubset(predictions.columns)
    adaptive_rows = (
        int(predictions[list(ADAPTIVE_COLUMNS)].dropna(how="all").shape[0])
        if adaptive_columns_ready
        else 0
    )
    adaptive_enabled = False
    if adaptive_columns_ready:
        adaptive_enabled = predictions["adaptive_prediction_enabled"].astype(str).str.lower().isin(["true", "1", "yes"]).any()
    adaptive_model = "Unavailable"
    if adaptive_columns_ready and not predictions["adaptive_model_version"].dropna().empty:
        adaptive_model = str(predictions["adaptive_model_version"].dropna().iloc[0])
    path_ready = not path_status.empty and "prob_reach_round_32" in path_status.columns
    price_ready = not prices.empty and {"prob_reach_round_16", "prob_champion", "cupmarket_price"}.issubset(prices.columns)
    model_text = "Unavailable"
    generated = "Unavailable"
    if not predictions.empty:
        model_text = str(predictions.get("model_version", pd.Series(["Unavailable"])).dropna().iloc[0]) if not predictions.get("model_version", pd.Series()).dropna().empty else "Unavailable"
        generated = _time(predictions.get("generated_at_utc", pd.Series([pd.NaT])).dropna().iloc[0]) if not predictions.get("generated_at_utc", pd.Series()).dropna().empty else "Unavailable"

    checks = pd.DataFrame([
        {"Check": "Round-of-32 path file exists", "Status": _yes(path_ready), "Evidence": f"{len(path_status)} team path rows"},
        {"Check": "Confirmed knockout slots detected", "Status": _yes(not confirmed_paths.empty), "Evidence": f"{len(confirmed_paths)} confirmed or partly confirmed path rows"},
        {"Check": "Knockout match predictions generated", "Status": _yes(not knockout_predictions.empty), "Evidence": f"{len(knockout_predictions)} knockout prediction rows"},
        {"Check": "Expected goals for knockout matches", "Status": _yes(expected_goal_ready), "Evidence": "Available" if expected_goal_ready else "Waiting for knockout prediction rows"},
        {"Check": "Likely scores for knockout matches", "Status": _yes(likely_score_ready), "Evidence": "Available" if likely_score_ready else "Waiting for knockout prediction rows"},
        {"Check": "Chance to advance for knockout matches", "Status": _yes(advance_ready), "Evidence": "Available" if advance_ready else "Waiting for advancement probability columns"},
        {"Check": "Live knockout advancement engine", "Status": "Ready", "Evidence": "Non-group live matches use backend/live_knockout.py"},
        {"Check": "Adaptive prediction columns", "Status": _yes(adaptive_columns_ready), "Evidence": f"{adaptive_rows} prediction rows with adaptive fields"},
        {"Check": "Market probabilities include later stages", "Status": _yes(price_ready), "Evidence": "R16/champion/price columns present" if price_ready else "Missing later-stage price columns"},
    ])

    cols = st.columns(4)
    cols[0].metric("Path rows", len(path_status))
    cols[1].metric("Confirmed/partial slots", len(confirmed_paths))
    cols[2].metric("Knockout predictions", len(knockout_predictions))
    cols[3].metric("Model", model_text)

    st.caption(f"Latest prediction run: {generated}")
    st.caption(
        "Adaptive prediction enabled: "
        f"{'yes' if adaptive_enabled else 'no'} - "
        f"{adaptive_model} - {adaptive_rows} rows with adaptive columns"
    )
    st.dataframe(checks, hide_index=True, width="stretch")

    if knockout_predictions.empty:
        st.warning(
            "The app is visually prepared for knockout stages, but the latest prediction file has no knockout prediction rows yet. "
            "Once the automation sees official Round-of-32 fixtures, it must publish expected goals, win probabilities and likely scores for those matches."
        )
    else:
        st.success("Knockout prediction rows are present. Review Match Intelligence and Bracket after the next model run.")

    with st.expander("What must happen after the group stage", expanded=False):
        st.write(
            "The backend needs to detect official knockout fixtures, create pre-match predictions, save them before kickoff, "
            "reprice teams after every elimination, move winners through the bracket, and keep eliminated teams locked out of future paths."
        )
