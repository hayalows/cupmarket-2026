from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from features.live_match_data import load_matches
from features.match_ui import prediction_confidence
from features.official_data import load_latest_json
from features.tournament_data import (
    DATA_DIR,
    actual_outcome,
    load_market_history,
    load_static_data,
    outcome_probability,
    reference_prediction,
)

HISTORICAL_EVAL_PATH = DATA_DIR / "phase3_goal_model_evaluation.json"
ADAPTIVE_HEALTH_PATH = DATA_DIR / "adaptive_model_health.json"
MATCHES_PATH = DATA_DIR / "world_cup_2026_matches_latest.csv"
OUTCOME_COLUMNS = {
    "HOME_WIN": "prob_home_win",
    "DRAW": "prob_draw",
    "AWAY_WIN": "prob_away_win",
}


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _probability_vector(prediction: pd.Series) -> dict[str, float] | None:
    values: dict[str, float] = {}
    for outcome, column in OUTCOME_COLUMNS.items():
        value = pd.to_numeric(prediction.get(column), errors="coerce")
        if pd.isna(value):
            return None
        values[outcome] = float(value)
    total = sum(values.values())
    if total <= 0:
        return None
    return {outcome: value / total for outcome, value in values.items()}


def _leading_outcome(probabilities: dict[str, float]) -> str:
    return max(probabilities, key=probabilities.get)


def _score_text(home, away) -> str:
    home_value = pd.to_numeric(home, errors="coerce")
    away_value = pd.to_numeric(away, errors="coerce")
    if pd.isna(home_value) or pd.isna(away_value):
        return "—"
    return f"{int(home_value)}-{int(away_value)}"


def _verified_match_rows(
    matches: pd.DataFrame,
    prediction_ledger: pd.DataFrame,
) -> pd.DataFrame:
    if matches.empty or prediction_ledger.empty:
        return pd.DataFrame()

    finished = matches[matches["status"].isin(["FINISHED", "AWARDED"])].copy()
    rows: list[dict] = []

    for match_tuple in finished.sort_values("utc_date").itertuples(index=False):
        match = pd.Series(match_tuple._asdict())
        prediction, source = reference_prediction(prediction_ledger, match)
        if source != "Saved pre-match forecast" or prediction.empty:
            continue

        probabilities = _probability_vector(prediction)
        actual = actual_outcome(match)
        if probabilities is None or actual not in OUTCOME_COLUMNS:
            continue

        baseline_prediction = pd.Series(
            {
                "prob_home_win": prediction.get("baseline_prob_home_win"),
                "prob_draw": prediction.get("baseline_prob_draw"),
                "prob_away_win": prediction.get("baseline_prob_away_win"),
            }
        )
        baseline_probabilities = _probability_vector(baseline_prediction)

        actual_probability = probabilities[actual]
        brier = sum(
            (probability - (1.0 if outcome == actual else 0.0)) ** 2
            for outcome, probability in probabilities.items()
        )
        log_loss = -math.log(max(actual_probability, 1e-15))

        actual_home = pd.to_numeric(match.get("home_score_full_time"), errors="coerce")
        actual_away = pd.to_numeric(match.get("away_score_full_time"), errors="coerce")
        expected_home = pd.to_numeric(prediction.get("expected_home_goals"), errors="coerce")
        expected_away = pd.to_numeric(prediction.get("expected_away_goals"), errors="coerce")

        home_error = (
            abs(float(expected_home) - float(actual_home))
            if pd.notna(expected_home) and pd.notna(actual_home)
            else None
        )
        away_error = (
            abs(float(expected_away) - float(actual_away))
            if pd.notna(expected_away) and pd.notna(actual_away)
            else None
        )

        actual_score = _score_text(actual_home, actual_away)
        likely_scores = [
            str(prediction.get(column, "")).strip()
            for column in [
                "most_likely_score",
                "second_likely_score",
                "third_likely_score",
            ]
            if str(prediction.get(column, "")).strip()
        ]
        confidence, top_probability, separation = prediction_confidence(prediction)

        rows.append(
            {
                "match_id": int(match["match_id"]),
                "date": pd.to_datetime(match.get("utc_date"), errors="coerce", utc=True),
                "match": f"{match.get('home_team')} vs {match.get('away_team')}",
                "actual_score": actual_score,
                "actual_outcome": actual,
                "leading_outcome": _leading_outcome(probabilities),
                "leading_correct": _leading_outcome(probabilities) == actual,
                "actual_probability": actual_probability,
                "brier": brier,
                "log_loss": log_loss,
                "home_goal_error": home_error,
                "away_goal_error": away_error,
                "expected_score": (
                    f"{float(expected_home):.2f}-{float(expected_away):.2f}"
                    if pd.notna(expected_home) and pd.notna(expected_away)
                    else "—"
                ),
                "most_likely_score": likely_scores[0] if likely_scores else "—",
                "exact_score_hit": bool(likely_scores and actual_score == likely_scores[0]),
                "top_three_score_hit": actual_score in likely_scores,
                "confidence": confidence,
                "top_probability": top_probability,
                "outcome_separation": separation,
                "model_version": str(prediction.get("model_version", "Unknown")),
                "prob_home_win": probabilities["HOME_WIN"],
                "prob_draw": probabilities["DRAW"],
                "prob_away_win": probabilities["AWAY_WIN"],
                "baseline_actual_probability": (
                    baseline_probabilities[actual]
                    if baseline_probabilities is not None
                    else None
                ),
                "baseline_brier": (
                    sum(
                        (probability - (1.0 if outcome == actual else 0.0)) ** 2
                        for outcome, probability in baseline_probabilities.items()
                    )
                    if baseline_probabilities is not None
                    else None
                ),
                "baseline_log_loss": (
                    -math.log(max(baseline_probabilities[actual], 1e-15))
                    if baseline_probabilities is not None
                    else None
                ),
                "baseline_prob_home_win": (
                    baseline_probabilities["HOME_WIN"]
                    if baseline_probabilities is not None
                    else None
                ),
                "baseline_prob_draw": (
                    baseline_probabilities["DRAW"]
                    if baseline_probabilities is not None
                    else None
                ),
                "baseline_prob_away_win": (
                    baseline_probabilities["AWAY_WIN"]
                    if baseline_probabilities is not None
                    else None
                ),
            }
        )

    return pd.DataFrame(rows)


def _mean_available(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    return None if numeric.empty else float(numeric.mean())


def _live_metrics(rows: pd.DataFrame) -> dict:
    if rows.empty:
        return {
            "n": 0,
            "correct": 0,
            "hit_rate": None,
            "brier": None,
            "log_loss": None,
            "actual_probability": None,
            "goal_mae": None,
            "exact_score": None,
            "top_three": None,
        }

    goal_errors = pd.concat(
        [rows["home_goal_error"], rows["away_goal_error"]],
        ignore_index=True,
    )
    n = len(rows)
    correct = int(rows["leading_correct"].sum())
    return {
        "n": n,
        "correct": correct,
        "hit_rate": correct / n,
        "brier": float(rows["brier"].mean()),
        "log_loss": float(rows["log_loss"].mean()),
        "actual_probability": float(rows["actual_probability"].mean()),
        "goal_mae": _mean_available(goal_errors),
        "exact_score": float(rows["exact_score_hit"].mean()),
        "top_three": float(rows["top_three_score_hit"].mean()),
    }


def _format_percent(value: float | None) -> str:
    return "—" if value is None else f"{100 * value:.1f}%"


def _format_decimal(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _interpret_live(metrics: dict) -> str:
    n = metrics["n"]
    if n == 0:
        return "No verified pre-match forecasts have completed yet."
    if n < 10:
        return (
            f"This is an early live sample: {metrics['correct']} of {n} leading outcomes "
            "were correct. One result can still move the percentage sharply, so the "
            "probability and goal metrics matter more than the headline hit rate alone."
        )
    return (
        "The live scorecard combines result direction, probability quality, expected-goal "
        "error and scoreline coverage. No single metric should be read in isolation."
    )


def _render_live_scorecard(rows: pd.DataFrame, metrics: dict) -> None:
    st.markdown("### Live World Cup scorecard")
    st.caption("Only forecasts saved before kickoff are included.")

    first = st.columns(3)
    first[0].metric("Verified forecasts", metrics["n"])
    first[1].metric(
        "Leading-outcome hit rate",
        _format_percent(metrics["hit_rate"]),
        delta=(
            f"{metrics['correct']} correct from {metrics['n']}"
            if metrics["n"]
            else "Waiting for verified results"
        ),
        delta_color="off",
    )
    first[2].metric(
        "Brier score",
        _format_decimal(metrics["brier"]),
        delta="Lower is better · 0 is perfect",
        delta_color="off",
    )

    second = st.columns(3)
    second[0].metric(
        "Probability of what happened",
        _format_percent(metrics["actual_probability"]),
        delta="Average probability assigned to actual outcomes",
        delta_color="off",
    )
    second[1].metric(
        "Goal MAE",
        _format_decimal(metrics["goal_mae"], 2),
        delta="Average error per team, in goals",
        delta_color="off",
    )
    second[2].metric(
        "Top-3 score coverage",
        _format_percent(metrics["top_three"]),
        delta=(
            f"{int(rows['top_three_score_hit'].sum())} of {len(rows)} actual scores"
            if not rows.empty
            else "Waiting for verified results"
        ),
        delta_color="off",
    )

    st.info(_interpret_live(metrics))


def _render_historical_reference(historical: dict) -> None:
    with st.expander("Compare with the historical holdout", expanded=False):
        if not historical:
            st.caption("Historical evaluation data is unavailable.")
            return

        rows = int(historical.get("holdout_rows", 0))
        home_mae = pd.to_numeric(historical.get("home_goal_mae"), errors="coerce")
        away_mae = pd.to_numeric(historical.get("away_goal_mae"), errors="coerce")
        combined_mae = (
            float(home_mae + away_mae) / 2
            if pd.notna(home_mae) and pd.notna(away_mae)
            else None
        )

        columns = st.columns(4)
        columns[0].metric("Historical test matches", f"{rows:,}")
        columns[1].metric(
            "Outcome hit rate",
            _format_percent(pd.to_numeric(historical.get("outcome_accuracy"), errors="coerce")),
        )
        columns[2].metric(
            "Brier score",
            _format_decimal(pd.to_numeric(historical.get("outcome_multiclass_brier"), errors="coerce")),
        )
        columns[3].metric("Goal MAE", _format_decimal(combined_mae, 2))

        st.caption(
            "The historical figures come from a 4,567-match holdout. The live scorecard "
            "uses only current World Cup forecasts recorded before kickoff, so the two "
            "samples should not be expected to match after only a few tournament games."
        )


def _render_match_detail(rows: pd.DataFrame, metrics: dict) -> None:
    if rows.empty:
        return

    with st.expander("Match-by-match evidence", expanded=False):
        chart_data = rows.copy()
        chart_data["Actual outcome probability"] = 100 * chart_data["actual_probability"]
        figure = px.bar(
            chart_data,
            x="match",
            y="Actual outcome probability",
            color="leading_correct",
            labels={
                "match": "Match",
                "leading_correct": "Leading outcome correct",
            },
            title="Probability assigned to each actual result",
        )
        figure.update_layout(
            template="plotly_white",
            height=360,
            margin=dict(l=16, r=16, t=52, b=16),
            legend_title_text="Top outcome correct",
        )
        figure.update_yaxes(range=[0, 100], ticksuffix="%")
        st.plotly_chart(figure, width="stretch")

        display = rows[
            [
                "match",
                "actual_score",
                "most_likely_score",
                "actual_probability",
                "brier",
                "expected_score",
                "top_three_score_hit",
                "model_version",
            ]
        ].copy()
        display["actual_probability"] = display["actual_probability"].map(
            lambda value: f"{100 * float(value):.1f}%"
        )
        display["brier"] = display["brier"].map(lambda value: f"{float(value):.3f}")
        display["top_three_score_hit"] = display["top_three_score_hit"].map(
            {True: "Yes", False: "No"}
        )
        display.columns = [
            "Match",
            "Actual score",
            "Most likely score",
            "Actual outcome probability",
            "Brier contribution",
            "Expected goals",
            "Actual score in top 3",
            "Model version",
        ]
        st.dataframe(display, hide_index=True, width="stretch")

        advanced = st.columns(3)
        advanced[0].metric("Log loss", _format_decimal(metrics["log_loss"]))
        advanced[1].metric(
            "Exact-score hit rate",
            _format_percent(metrics["exact_score"]),
        )
        advanced[2].metric(
            "Average outcome separation",
            _format_percent(_mean_available(rows["outcome_separation"])),
        )


def _calibration_rows(rows: pd.DataFrame) -> pd.DataFrame:
    records: list[dict] = []
    for row in rows.itertuples(index=False):
        for outcome, column in OUTCOME_COLUMNS.items():
            records.append(
                {
                    "probability": float(getattr(row, column)),
                    "occurred": 1.0 if row.actual_outcome == outcome else 0.0,
                }
            )
    if not records:
        return pd.DataFrame()
    data = pd.DataFrame(records)
    data["band"] = pd.cut(
        data["probability"],
        bins=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        include_lowest=True,
    )
    calibration = (
        data.groupby("band", observed=True)
        .agg(
            predicted_probability=("probability", "mean"),
            actual_frequency=("occurred", "mean"),
            observations=("occurred", "size"),
        )
        .reset_index()
    )
    return calibration


def _render_calibration(rows: pd.DataFrame) -> None:
    with st.expander("Probability calibration", expanded=False):
        verified = len(rows)
        threshold = 20
        if verified < threshold:
            st.progress(min(verified / threshold, 1.0))
            st.write(
                f"**{verified} of {threshold} verified matches collected.** A live calibration "
                "chart is deliberately withheld because a four-match reliability curve would "
                "look precise while saying very little."
            )
            st.caption(
                "Calibration asks whether events assigned about 60% probability actually occur "
                "around 60% of the time. The view will activate automatically as the sample grows."
            )
            return

        calibration = _calibration_rows(rows)
        if calibration.empty:
            st.caption("Calibration data is unavailable.")
            return
        figure = px.line(
            calibration,
            x="predicted_probability",
            y="actual_frequency",
            markers=True,
            text="observations",
            title="Live probability calibration",
        )
        figure.add_shape(
            type="line",
            x0=0,
            y0=0,
            x1=1,
            y1=1,
            line=dict(dash="dash"),
        )
        figure.update_traces(textposition="top center")
        figure.update_layout(
            template="plotly_white",
            height=380,
            margin=dict(l=16, r=16, t=52, b=16),
        )
        figure.update_xaxes(tickformat=".0%", range=[0, 1], title="Average predicted probability")
        figure.update_yaxes(tickformat=".0%", range=[0, 1], title="Observed frequency")
        st.plotly_chart(figure, width="stretch")


def _render_adaptive_comparison(rows: pd.DataFrame, health: dict) -> None:
    comparable = rows.dropna(subset=["baseline_brier", "baseline_log_loss"]).copy()
    st.markdown("### Baseline vs adaptive")
    if comparable.empty:
        st.info("CupMarket is saving baseline probabilities, but no completed forecasts can be compared yet.")
        return

    adaptive_brier = float(comparable["brier"].mean())
    baseline_brier = float(comparable["baseline_brier"].mean())
    adaptive_log_loss = float(comparable["log_loss"].mean())
    baseline_log_loss = float(comparable["baseline_log_loss"].mean())
    columns = st.columns(4)
    columns[0].metric("Matched forecasts", len(comparable))
    columns[1].metric("Brier vs baseline", f"{adaptive_brier - baseline_brier:+.3f}", delta="Lower is better")
    columns[2].metric("Log loss vs baseline", f"{adaptive_log_loss - baseline_log_loss:+.3f}", delta="Lower is better")
    decision = str(health.get("decision") or "collecting_evidence").replace("_", " ").title()
    columns[3].metric("Guardrail", decision)
    st.caption(str(health.get("message") or "The guardrail evaluates saved pre-match forecasts only."))

    comparison_frames = []
    for label, columns_map in {
        "Adaptive": OUTCOME_COLUMNS,
        "Baseline": {
            "HOME_WIN": "baseline_prob_home_win",
            "DRAW": "baseline_prob_draw",
            "AWAY_WIN": "baseline_prob_away_win",
        },
    }.items():
        calibration_source = comparable[["actual_outcome", *columns_map.values()]].rename(
            columns={value: OUTCOME_COLUMNS[key] for key, value in columns_map.items()}
        )
        calibration = _calibration_rows(calibration_source)
        if not calibration.empty:
            calibration["Model"] = label
            comparison_frames.append(calibration)
    if comparison_frames:
        chart_data = pd.concat(comparison_frames, ignore_index=True)
        figure = px.line(
            chart_data,
            x="predicted_probability",
            y="actual_frequency",
            color="Model",
            markers=True,
            title="Calibration: adaptive probability versus saved baseline",
        )
        figure.add_shape(type="line", x0=0, y0=0, x1=1, y1=1, line=dict(dash="dash"))
        figure.update_layout(template="plotly_white", height=360, margin=dict(l=16, r=16, t=52, b=16))
        figure.update_xaxes(tickformat=".0%", range=[0, 1], title="Average predicted probability")
        figure.update_yaxes(tickformat=".0%", range=[0, 1], title="Observed frequency")
        st.plotly_chart(figure, width="stretch")


def _simulation_integrity(prices: pd.DataFrame) -> tuple[int, int]:
    stage_columns = [
        "prob_reach_round_32",
        "prob_reach_round_16",
        "prob_reach_quarter_final",
        "prob_reach_semi_final",
        "prob_reach_final",
        "prob_champion",
    ]
    available = [column for column in stage_columns if column in prices.columns]
    if prices.empty or len(available) < 2:
        return 0, 0

    checked = 0
    passed = 0
    for row in prices[available].itertuples(index=False, name=None):
        values = [pd.to_numeric(value, errors="coerce") for value in row]
        if any(pd.isna(value) for value in values):
            continue
        checked += 1
        if all(float(values[index]) + 1e-9 >= float(values[index + 1]) for index in range(len(values) - 1)):
            passed += 1
    return passed, checked


def _render_tournament_and_market_status(prices: pd.DataFrame) -> None:
    with st.expander("Tournament simulation and market evaluation", expanded=False):
        passed, checked = _simulation_integrity(prices)
        history = load_market_history()
        snapshots = (
            history["generated_at_utc"].nunique()
            if not history.empty and "generated_at_utc" in history.columns
            else 0
        )
        columns = st.columns(3)
        columns[0].metric(
            "Stage-probability integrity",
            f"{passed}/{checked} teams" if checked else "Unavailable",
            delta="Later-stage probability must not exceed earlier-stage probability",
            delta_color="off",
        )
        columns[1].metric(
            "Official price checkpoints",
            int(snapshots),
            delta="Used for before-and-after market stories",
            delta_color="off",
        )
        columns[2].metric(
            "Final price accuracy",
            "Pending",
            delta="Measured against tournament settlement as outcomes become final",
            delta_color="off",
        )
        st.caption(
            "Tournament probabilities and prices cannot be fully scored until stages are "
            "decided. For now, CupMarket checks structural consistency and preserves official "
            "price checkpoints. Stage Brier scores and final settlement error will become "
            "meaningful as the tournament progresses."
        )


def render_model_performance() -> None:
    matches, source = load_matches(MATCHES_PATH)
    static = load_static_data()
    rows = _verified_match_rows(matches, static["prediction_ledger"])
    metrics = _live_metrics(rows)
    historical = _read_json(HISTORICAL_EVAL_PATH)
    adaptive_health = load_latest_json(ADAPTIVE_HEALTH_PATH)

    st.markdown("### Model Performance")
    st.write(
        "The live 50% figure is only the top-outcome hit rate. This scorecard also checks "
        "whether the probabilities were sensible, how close expected goals were, and "
        "whether the score distribution covered what actually happened."
    )

    _render_live_scorecard(rows, metrics)
    _render_historical_reference(historical)
    _render_adaptive_comparison(rows, adaptive_health)
    _render_match_detail(rows, metrics)
    _render_calibration(rows)
    _render_tournament_and_market_status(static["prices"])

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
        f"Score source: {source.get('source', 'Unknown')}. Only predictions recorded before "
        "kickoff are included, and model versions remain visible in the match-level table."
    )
