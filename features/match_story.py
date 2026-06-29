from __future__ import annotations

import pandas as pd
import streamlit as st


def _pct(value: object) -> str:
    n = pd.to_numeric(value, errors="coerce")
    return "—" if pd.isna(n) else f"{100 * float(n):.1f}%"


def _format_call(value: object) -> str:
    text = str(value or "").replace("_", " ").title()
    return text if text else "Unknown"


def _score_from(row: pd.Series, home_col: str, away_col: str) -> str:
    h = pd.to_numeric(row.get(home_col), errors="coerce")
    a = pd.to_numeric(row.get(away_col), errors="coerce")
    if pd.isna(h) or pd.isna(a):
        return "vs"
    return f"{int(h)}-{int(a)}"


def _actual_from_scores(home_score, away_score) -> str:
    h = pd.to_numeric(home_score, errors="coerce")
    a = pd.to_numeric(away_score, errors="coerce")
    if pd.isna(h) or pd.isna(a):
        return "UNKNOWN"
    if h > a:
        return "HOME_WIN"
    if h < a:
        return "AWAY_WIN"
    return "DRAW"


def _prob(row: pd.Series, outcome: str):
    mapping = {"HOME_WIN": "prob_home_win", "DRAW": "prob_draw", "AWAY_WIN": "prob_away_win"}
    return row.get(mapping.get(outcome, ""))


def _completed_predictions(prediction_ledger: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(prediction_ledger, pd.DataFrame) or prediction_ledger.empty:
        return pd.DataFrame()
    required = {"home_team", "away_team", "actual_home_score", "actual_away_score"}
    if not required.issubset(prediction_ledger.columns):
        return pd.DataFrame()
    rows = prediction_ledger.copy()
    rows["actual_home_score"] = pd.to_numeric(rows["actual_home_score"], errors="coerce")
    rows["actual_away_score"] = pd.to_numeric(rows["actual_away_score"], errors="coerce")
    rows = rows.dropna(subset=["actual_home_score", "actual_away_score"])
    if rows.empty:
        return rows
    rows["story_source"] = "Prediction ledger"
    rows["scoreline"] = rows.apply(lambda r: _score_from(r, "actual_home_score", "actual_away_score"), axis=1)
    rows["actual_result"] = rows.apply(lambda r: _actual_from_scores(r.get("actual_home_score"), r.get("actual_away_score")), axis=1)
    if "generated_at_utc" in rows.columns:
        rows["story_time"] = pd.to_datetime(rows["generated_at_utc"], errors="coerce", utc=True)
    else:
        rows["story_time"] = pd.NaT
    return rows


def _completed_processed(processed_ledger: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(processed_ledger, pd.DataFrame) or processed_ledger.empty:
        return pd.DataFrame()
    required = {"home_team", "away_team", "home_score", "away_score"}
    if not required.issubset(processed_ledger.columns):
        return pd.DataFrame()
    rows = processed_ledger.copy()
    rows["home_score"] = pd.to_numeric(rows["home_score"], errors="coerce")
    rows["away_score"] = pd.to_numeric(rows["away_score"], errors="coerce")
    rows = rows.dropna(subset=["home_score", "away_score"])
    if rows.empty:
        return rows
    rows["actual_home_score"] = rows["home_score"]
    rows["actual_away_score"] = rows["away_score"]
    rows["predicted_result"] = rows.get("predicted_result", "Not stored")
    rows["story_source"] = "Processed match ledger"
    rows["scoreline"] = rows.apply(lambda r: _score_from(r, "home_score", "away_score"), axis=1)
    rows["actual_result"] = rows.apply(lambda r: _actual_from_scores(r.get("home_score"), r.get("away_score")), axis=1)
    time_column = "processed_at_utc" if "processed_at_utc" in rows.columns else "utc_date"
    rows["story_time"] = pd.to_datetime(rows.get(time_column), errors="coerce", utc=True)
    return rows


def render_match_story(prediction_ledger: pd.DataFrame, market_movements: pd.DataFrame, processed_ledger: pd.DataFrame | None = None) -> None:
    st.markdown("## Match Story Engine")
    st.caption("Completed games with model call where available. If prediction details are missing, CupMarket still shows the official result story from the processed ledger.")

    predicted = _completed_predictions(prediction_ledger)
    processed = _completed_processed(processed_ledger if isinstance(processed_ledger, pd.DataFrame) else pd.DataFrame())

    if predicted.empty and processed.empty:
        st.info("No completed match stories are available yet.")
        return

    predicted_keys = set()
    if not predicted.empty:
        predicted_keys = set(zip(predicted["home_team"].astype(str), predicted["away_team"].astype(str), predicted["scoreline"].astype(str)))
    if not processed.empty:
        processed = processed.loc[~processed.apply(lambda r: (str(r.get("home_team")), str(r.get("away_team")), str(r.get("scoreline"))) in predicted_keys, axis=1)]
    rows = pd.concat([predicted, processed], ignore_index=True, sort=False)
    rows = rows.sort_values("story_time", ascending=False, na_position="last")

    st.caption(f"Showing {len(rows)} completed match stories. Full model calls are shown only for rows stored in the prediction ledger.")
    labels = rows.apply(lambda r: f"{r.get('home_team')} {r.get('scoreline')} {r.get('away_team')} · {r.get('story_source')}", axis=1).tolist()
    selected = st.selectbox("Completed match", labels, key="match_story_selector")
    row = rows.iloc[labels.index(selected)]

    actual = str(row.get("actual_result", "UNKNOWN"))
    model_call = str(row.get("predicted_result", "Not stored"))
    has_model_call = model_call not in {"", "nan", "None", "Not stored"}
    actual_probability = _prob(row, actual)
    correct = has_model_call and model_call == actual

    cols = st.columns(4)
    cols[0].metric("Result", f"{row.get('home_team')} {row.get('scoreline')} {row.get('away_team')}")
    cols[1].metric("Source", str(row.get("story_source")))
    cols[2].metric("Model call", _format_call(model_call) if has_model_call else "Not stored")
    cols[3].metric("Actual probability", _pct(actual_probability))

    if has_model_call:
        if correct:
            st.success("The model called this result correctly before the match.")
        else:
            st.warning("This result went against the stored model call.")
    else:
        st.info("This match result is stored, but its full pre-match prediction was not linked into the prediction ledger. The app is using the processed match ledger so the match still appears in the story list.")

    st.write(
        f"**Story:** {row.get('home_team')} and {row.get('away_team')} finished {row.get('scoreline')}. "
        f"Actual outcome: {_format_call(actual)}. "
        f"Model call: {_format_call(model_call) if has_model_call else 'not stored for this row'}."
    )

    with st.expander("Why might model call say Not stored?", expanded=False):
        st.write(
            "The processed match ledger records completed results. The prediction ledger records pre-match model calls. "
            "Some older or fallback rows have the result but do not have a linked pre-match prediction row yet. "
            "That is why CupMarket can show the match result but cannot show actual-result probability for that row."
        )

    if isinstance(market_movements, pd.DataFrame) and not market_movements.empty and "team" in market_movements.columns:
        teams = [str(row.get("home_team")), str(row.get("away_team"))]
        focus = market_movements.loc[market_movements["team"].astype(str).isin(teams)].copy()
        if not focus.empty and "trigger_matches" in focus.columns:
            trigger_text = focus["trigger_matches"].astype(str)
            related = focus.loc[
                trigger_text.str.contains(teams[0], regex=False, na=False)
                | trigger_text.str.contains(teams[1], regex=False, na=False)
            ].copy()
            if not related.empty:
                focus = related
            elif "relationship_to_event" in focus.columns:
                focus = focus.loc[
                    ~focus["relationship_to_event"].astype(str).eq("other")
                ].copy()
        if not focus.empty and "snapshot_id" in focus.columns:
            focus["snapshot_id"] = pd.to_datetime(
                focus["snapshot_id"], errors="coerce", utc=True
            )
            focus = focus.sort_values("snapshot_id").groupby("team", as_index=False).tail(1)
        if not focus.empty:
            st.markdown("### Market impact for the teams involved")
            keep = [
                c
                for c in [
                    "team",
                    "movement_type",
                    "price_before",
                    "price_after",
                    "price_change",
                    "price_change_percent",
                    "trigger_matches",
                ]
                if c in focus.columns
            ]
            st.dataframe(focus[keep], hide_index=True, use_container_width=True)
        else:
            st.caption("No direct market movement row found for these teams in the movement archive.")
