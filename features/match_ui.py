from __future__ import annotations

import pandas as pd
import streamlit as st

from features.live_qualification_ui import render_live_match
from features.qualification_ui import (
    cached_qualification_scenarios,
    format_percent,
    render_qualification_result,
)


def format_number(value, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):.{digits}f}"


def score_text(row: pd.Series) -> str:
    home = row.get("home_score_full_time")
    away = row.get("away_score_full_time")
    if pd.isna(home) or pd.isna(away):
        return "vs"
    return f"{int(home)}–{int(away)}"


def combine_prediction_sources(
    latest_predictions: pd.DataFrame,
    prediction_ledger: pd.DataFrame,
) -> pd.DataFrame:
    frames = []
    if not prediction_ledger.empty:
        ledger = prediction_ledger.copy()
        ledger["source_priority"] = 0
        frames.append(ledger)
    if not latest_predictions.empty:
        latest = latest_predictions.copy()
        latest["source_priority"] = 1
        frames.append(latest)
    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined["match_id"] = pd.to_numeric(
        combined["match_id"], errors="coerce"
    )
    combined = combined.dropna(subset=["match_id"])
    combined["match_id"] = combined["match_id"].astype(int)
    if "generated_at_utc" in combined.columns:
        combined["generated_at_utc"] = pd.to_datetime(
            combined["generated_at_utc"], errors="coerce", utc=True
        )
        combined = combined.sort_values(
            ["generated_at_utc", "source_priority"]
        )
    return combined.drop_duplicates("match_id", keep="last").reset_index(drop=True)


def prediction_confidence(row: pd.Series) -> tuple[str, float, float]:
    probabilities = sorted(
        [
            float(row.get("prob_home_win", 0) or 0),
            float(row.get("prob_draw", 0) or 0),
            float(row.get("prob_away_win", 0) or 0),
        ],
        reverse=True,
    )
    top_probability = probabilities[0]
    separation = probabilities[0] - probabilities[1]
    if top_probability >= 0.65 and separation >= 0.15:
        label = "High"
    elif top_probability >= 0.50 and separation >= 0.08:
        label = "Moderate"
    else:
        label = "Low · close matchup"
    return label, top_probability, separation


def match_option_label(row: pd.Series) -> str:
    kickoff = row.get("utc_date")
    kickoff_text = (
        kickoff.strftime("%d %b · %H:%M UTC")
        if pd.notna(kickoff)
        else "Time pending"
    )
    return (
        f'{row.get("home_team", "TBD")} vs '
        f'{row.get("away_team", "TBD")} · {kickoff_text}'
    )


def render_match_centre(
    matches: pd.DataFrame,
    prediction_outputs: pd.DataFrame,
    prices: pd.DataFrame,
) -> None:
    st.markdown("### Fixtures and match intelligence")
    st.caption(
        "Open any matchup to inspect probabilities, expected goals, likely "
        "scores and qualification impact."
    )

    if st.button(
        "Refresh score cache",
        help=(
            "Clears the 60-second cache. Avoid repeated refreshes because "
            "the football API is rate-limited."
        ),
    ):
        st.cache_data.clear()
        st.rerun()

    if matches.empty:
        st.warning("No matches are available.")
        return

    status_options = sorted(matches["status"].dropna().unique())
    selected_statuses = st.multiselect(
        "Match status",
        status_options,
        default=status_options,
    )
    filtered = matches[matches["status"].isin(selected_statuses)].copy()
    filtered["kickoff_utc"] = filtered["utc_date"].dt.strftime(
        "%Y-%m-%d %H:%M"
    )
    filtered["score"] = filtered.apply(score_text, axis=1)

    prediction_columns = [
        column
        for column in [
            "match_id",
            "expected_home_goals",
            "expected_away_goals",
            "prob_home_win",
            "prob_draw",
            "prob_away_win",
            "prob_btts_yes",
            "prob_over_2_5",
            "display_label",
            "most_likely_score",
            "most_likely_score_probability",
            "second_likely_score",
            "second_likely_score_probability",
            "third_likely_score",
            "third_likely_score_probability",
        ]
        if column in prediction_outputs.columns
    ]
    if prediction_columns:
        filtered = filtered.merge(
            prediction_outputs[prediction_columns],
            on="match_id",
            how="left",
        )

    display_columns = [
        "kickoff_utc",
        "status",
        "home_team",
        "score",
        "away_team",
        "group",
        "stage",
    ]
    for optional in [
        "prob_home_win",
        "prob_draw",
        "prob_away_win",
        "display_label",
        "most_likely_score",
    ]:
        if optional in filtered.columns:
            display_columns.append(optional)

    match_display = filtered[display_columns].copy()
    for probability_column in [
        "prob_home_win",
        "prob_draw",
        "prob_away_win",
    ]:
        if probability_column in match_display.columns:
            match_display[probability_column] = match_display[
                probability_column
            ].map(format_percent)
    match_display = match_display.rename(
        columns={
            "kickoff_utc": "Kickoff · UTC",
            "status": "Status",
            "home_team": "Home",
            "score": "Score",
            "away_team": "Away",
            "group": "Group",
            "stage": "Stage",
            "prob_home_win": "Home win",
            "prob_draw": "Draw",
            "prob_away_win": "Away win",
            "display_label": "Model view",
            "most_likely_score": "Likely score",
        }
    )
    st.dataframe(match_display, use_container_width=True, hide_index=True)

    st.markdown("### Open a matchup")
    st.caption("Choose a match to view its own intelligence page.")
    selectable = filtered[
        filtered["home_team"].notna() & filtered["away_team"].notna()
    ].sort_values("utc_date")
    if selectable.empty:
        st.info("No complete matchup is available for the selected filters.")
        return

    option_rows = {
        int(row.match_id): pd.Series(row._asdict())
        for row in selectable.itertuples(index=False)
    }
    selected_match_id = st.selectbox(
        "Choose a match",
        list(option_rows),
        format_func=lambda match_id: match_option_label(option_rows[match_id]),
    )
    match_row = option_rows[int(selected_match_id)]
    prediction_rows = (
        prediction_outputs[
            prediction_outputs["match_id"] == int(selected_match_id)
        ]
        if not prediction_outputs.empty
        else pd.DataFrame()
    )
    prediction_row = (
        prediction_rows.iloc[-1]
        if not prediction_rows.empty
        else pd.Series(dtype=object)
    )

    kickoff = match_row.get("utc_date")
    kickoff_text = (
        kickoff.strftime("%A, %d %B · %H:%M UTC")
        if pd.notna(kickoff)
        else "Kickoff pending"
    )
    st.markdown(
        f'''
        <div class="cm-match-card">
            <div class="cm-match-meta">{match_row.get("status", "")} · {kickoff_text}</div>
            <div class="cm-match-teams">
                <strong>{match_row.get("home_team", "TBD")}</strong>
                <span>{score_text(match_row)}</span>
                <strong>{match_row.get("away_team", "TBD")}</strong>
            </div>
            <div class="cm-match-meta">{match_row.get("group", "")} · {match_row.get("stage", "")}</div>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    live_projection_shown = render_live_match(
        matches,
        prediction_outputs,
        prices,
        int(selected_match_id),
    )
    if live_projection_shown:
        st.markdown("#### Original pre-match forecast")

    if prediction_row.empty or pd.isna(prediction_row.get("prob_home_win")):
        st.info("A saved probability forecast is not available for this match yet.")
        return

    confidence_label, top_probability, separation = prediction_confidence(
        prediction_row
    )
    probability_columns = st.columns(3)
    probability_columns[0].metric(
        f'{match_row.get("home_team")} win',
        format_percent(prediction_row.get("prob_home_win")),
    )
    probability_columns[1].metric(
        "Draw",
        format_percent(prediction_row.get("prob_draw")),
    )
    probability_columns[2].metric(
        f'{match_row.get("away_team")} win',
        format_percent(prediction_row.get("prob_away_win")),
    )

    detail_columns = st.columns(4)
    detail_columns[0].metric(
        "Home expected goals",
        format_number(prediction_row.get("expected_home_goals")),
    )
    detail_columns[1].metric(
        "Away expected goals",
        format_number(prediction_row.get("expected_away_goals")),
    )
    detail_columns[2].metric(
        "Most likely score",
        prediction_row.get("most_likely_score", "—"),
        delta=format_percent(
            prediction_row.get("most_likely_score_probability")
        ),
    )
    detail_columns[3].metric(
        "Model confidence",
        confidence_label,
        delta=f'{format_percent(top_probability)} leading outcome',
    )

    extra_columns = st.columns(3)
    extra_columns[0].metric(
        "Both teams to score",
        format_percent(prediction_row.get("prob_btts_yes")),
    )
    extra_columns[1].metric(
        "Over 2.5 goals",
        format_percent(prediction_row.get("prob_over_2_5")),
    )
    extra_columns[2].metric(
        "Outcome separation",
        format_percent(separation),
    )
    st.caption(
        "Confidence describes how clearly one outcome leads the alternatives. "
        "It is not a guarantee that the result will happen."
    )

    scoreline_rows = []
    for rank, (score_column, probability_column) in enumerate(
        [
            ("most_likely_score", "most_likely_score_probability"),
            ("second_likely_score", "second_likely_score_probability"),
            ("third_likely_score", "third_likely_score_probability"),
        ],
        start=1,
    ):
        if prediction_row.get(score_column):
            scoreline_rows.append(
                {
                    "Rank": rank,
                    "Score": prediction_row.get(score_column),
                    "Probability": format_percent(
                        prediction_row.get(probability_column)
                    ),
                }
            )
    if scoreline_rows:
        st.dataframe(
            pd.DataFrame(scoreline_rows),
            use_container_width=True,
            hide_index=True,
        )

    is_future_group_match = (
        match_row.get("stage") == "GROUP_STAGE"
        and match_row.get("status") in ["TIMED", "SCHEDULED"]
    )
    if is_future_group_match:
        with st.expander("What does this match mean for qualification?"):
            impact_team = st.selectbox(
                "Analyse qualification impact for",
                [match_row.get("home_team"), match_row.get("away_team")],
                key=f"match_impact_{selected_match_id}",
            )
            if st.button(
                "Calculate win, draw and loss impact",
                key=f"calculate_match_impact_{selected_match_id}",
            ):
                strength = (
                    dict(zip(prices["team"], prices["cupmarket_price"]))
                    if not prices.empty
                    else {}
                )
                with st.spinner("Simulating the remaining group stage..."):
                    result = cached_qualification_scenarios(
                        matches,
                        prediction_outputs,
                        impact_team,
                        tuple(sorted(strength.items())),
                        1500,
                    )
                if (
                    result.get("available")
                    and result["next_match"]["match_id"]
                    != int(selected_match_id)
                ):
                    st.info(
                        "The calculator starts with this country's next unplayed "
                        "group match."
                    )
                render_qualification_result(result, compact=True)

    st.caption(
        "Scores can refresh every 60 seconds. Saved model probabilities change "
        "when the automated model pipeline publishes a new file."
    )
