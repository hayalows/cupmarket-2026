from __future__ import annotations

import pandas as pd
import streamlit as st


def _pct(value: object) -> str:
    n = pd.to_numeric(value, errors="coerce")
    return "—" if pd.isna(n) else f"{100 * float(n):.1f}%"


def _result(row: pd.Series) -> str:
    h = pd.to_numeric(row.get("actual_home_score"), errors="coerce")
    a = pd.to_numeric(row.get("actual_away_score"), errors="coerce")
    if pd.isna(h) or pd.isna(a):
        return "UNKNOWN"
    if h > a:
        return "HOME_WIN"
    if h < a:
        return "AWAY_WIN"
    return "DRAW"


def _score(row: pd.Series) -> str:
    h = pd.to_numeric(row.get("actual_home_score"), errors="coerce")
    a = pd.to_numeric(row.get("actual_away_score"), errors="coerce")
    if pd.isna(h) or pd.isna(a):
        return "vs"
    return f"{int(h)}-{int(a)}"


def _prob(row: pd.Series, outcome: str):
    mapping = {"HOME_WIN": "prob_home_win", "DRAW": "prob_draw", "AWAY_WIN": "prob_away_win"}
    return row.get(mapping.get(outcome, ""))


def _format_call(value: object) -> str:
    text = str(value or "").replace("_", " ").title()
    return text if text else "Unknown"


def render_match_story(prediction_ledger: pd.DataFrame, market_movements: pd.DataFrame) -> None:
    st.markdown("## Match Story Engine")
    st.caption("Turns completed games into a short story: model call, actual result, surprise level and market context.")

    if not isinstance(prediction_ledger, pd.DataFrame) or prediction_ledger.empty:
        st.info("Prediction ledger is not available yet.")
        return

    required = {"home_team", "away_team", "actual_home_score", "actual_away_score", "predicted_result"}
    if not required.issubset(prediction_ledger.columns):
        st.info("Prediction ledger needs result and model-call columns before match stories can be shown.")
        return

    rows = prediction_ledger.copy()
    rows["actual_home_score"] = pd.to_numeric(rows["actual_home_score"], errors="coerce")
    rows["actual_away_score"] = pd.to_numeric(rows["actual_away_score"], errors="coerce")
    rows = rows.dropna(subset=["actual_home_score", "actual_away_score"])
    if rows.empty:
        st.info("No completed match predictions are ready yet.")
        return

    if "generated_at_utc" in rows.columns:
        rows["generated_at_utc"] = pd.to_datetime(rows["generated_at_utc"], errors="coerce", utc=True)
        rows = rows.sort_values("generated_at_utc", ascending=False)

    labels = rows.apply(lambda r: f"{r.get('home_team')} {_score(r)} {r.get('away_team')}", axis=1).tolist()
    selected = st.selectbox("Completed match", labels, key="match_story_selector")
    row = rows.iloc[labels.index(selected)]

    actual = _result(row)
    predicted = str(row.get("predicted_result"))
    correct = predicted == actual
    actual_probability = _prob(row, actual)

    cols = st.columns(4)
    cols[0].metric("Match", selected)
    cols[1].metric("Model call", _format_call(predicted))
    cols[2].metric("Actual", _format_call(actual))
    cols[3].metric("Actual probability", _pct(actual_probability))

    if correct:
        st.success("The model called the result correctly before the match.")
    else:
        st.warning("This result went against the model call. Treat it as a useful model-learning moment.")

    home = row.get("home_team")
    away = row.get("away_team")
    st.write(
        f"**Story:** {home} and {away} produced a {selected} result. "
        f"The model expected {_format_call(predicted)}, but the actual outcome was {_format_call(actual)}. "
        f"The model assigned {_pct(actual_probability)} to what actually happened."
    )

    if isinstance(market_movements, pd.DataFrame) and not market_movements.empty and "team" in market_movements.columns:
        focus = market_movements.loc[market_movements["team"].astype(str).isin([str(home), str(away)])].copy()
        if not focus.empty:
            st.markdown("### Market impact for the teams involved")
            keep = [c for c in ["team", "price_before", "price_after", "price_change", "price_change_percent", "trigger_matches"] if c in focus.columns]
            display = focus[keep].copy()
            st.dataframe(display, hide_index=True, use_container_width=True)
        else:
            st.caption("No direct market movement row found for these teams in the latest movement file.")
