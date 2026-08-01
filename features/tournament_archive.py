"""Archive-first presentation for the completed CupMarket tournament."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from features.official_bundle import load_final_archive_bundle
from features.official_data import load_latest_json
from features.tournament_data_v2 import DATA_DIR, STATE_DIR, load_static_data
from features.tournament_path_data import load_tournament_path_data


MANIFEST_PATH = DATA_DIR / "publication_manifest.json"
ADAPTIVE_HEALTH_PATH = DATA_DIR / "adaptive_model_health.json"


def _final_row(matches: pd.DataFrame) -> pd.Series:
    if matches.empty or not {"stage", "status"}.issubset(matches.columns):
        return pd.Series(dtype=object)
    rows = matches.loc[
        matches["stage"].astype(str).eq("FINAL")
        & matches["status"].astype(str).isin({"FINISHED", "AWARDED"})
    ]
    return rows.iloc[-1] if not rows.empty else pd.Series(dtype=object)


def _stage_row(matches: pd.DataFrame, stage: str) -> pd.Series:
    rows = matches.loc[matches.get("stage", pd.Series(dtype=str)).astype(str).eq(stage)]
    return rows.iloc[-1] if not rows.empty else pd.Series(dtype=object)


def _score(row: pd.Series) -> str:
    home = pd.to_numeric(row.get("home_score_full_time"), errors="coerce")
    away = pd.to_numeric(row.get("away_score_full_time"), errors="coerce")
    return "Result pending" if pd.isna(home) or pd.isna(away) else f"{int(home)}-{int(away)}"


def _percent(value) -> str:
    number = pd.to_numeric(value, errors="coerce")
    return "Unavailable" if pd.isna(number) else f"{100 * float(number):.1f}%"


def _metric_value(value, decimals: int = 2) -> str:
    number = pd.to_numeric(value, errors="coerce")
    return "Unavailable" if pd.isna(number) else f"{float(number):.{decimals}f}"


def _table(records: list[dict], columns: list[str], rename: dict[str, str] | None = None) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    frame = pd.DataFrame(records)
    available = [column for column in columns if column in frame.columns]
    frame = frame[available]
    return frame.rename(columns=rename or {})


def _render_group_stage_record(path_data: dict) -> None:
    tables = path_data.get("group_tables", pd.DataFrame())
    paths = path_data.get("path_status", pd.DataFrame())
    st.markdown("### Group-stage record")
    st.caption("Choose a group to review its final table and saved knockout-path publication.")
    if tables.empty or "group" not in tables.columns:
        st.info("Final group tables are not available in this publication.")
        return

    groups = sorted(tables["group"].dropna().astype(str).unique())
    selected_group = st.selectbox("Group", groups, key="cupmarket_archive_group")
    table = tables.loc[tables["group"].astype(str).eq(selected_group)].copy()
    columns = [
        "position", "team", "played", "wins", "draws", "losses",
        "goals_for", "goals_against", "goal_difference", "points",
    ]
    table = table[[column for column in columns if column in table.columns]].rename(
        columns={
            "position": "Pos", "team": "Country", "played": "P", "wins": "W",
            "draws": "D", "losses": "L", "goals_for": "GF",
            "goals_against": "GA", "goal_difference": "GD", "points": "Pts",
        }
    )
    st.dataframe(table, hide_index=True, width="stretch")

    if paths.empty or "team" not in paths.columns:
        return
    group_teams = set(table.get("Country", pd.Series(dtype=str)).astype(str))
    saved = paths.loc[paths["team"].astype(str).isin(group_teams)].copy()
    saved_columns = [
        "team", "fixture_status", "current_group_position", "most_likely_opponent",
    ]
    saved = saved[[column for column in saved_columns if column in saved.columns]].rename(
        columns={
            "team": "Country", "fixture_status": "Saved path state",
            "current_group_position": "Group position",
            "most_likely_opponent": "Projected opponent",
        }
    )
    if not saved.empty:
        with st.expander("Saved path publication", expanded=False):
            st.dataframe(saved, hide_index=True, width="stretch")


def _render_final_overview(
    matches: pd.DataFrame,
    prices: pd.DataFrame,
    settled: pd.DataFrame,
    archive: dict,
) -> None:
    final = _final_row(matches)
    third = _stage_row(matches, "THIRD_PLACE")
    if final.empty:
        st.info("The final has not been published yet.")
        return

    champion = (
        final.get("home_team") if str(final.get("winner")) == "HOME_TEAM"
        else final.get("away_team") if str(final.get("winner")) == "AWAY_TEAM"
        else archive.get("champion")
    )
    runner_up = (
        final.get("away_team") if str(final.get("winner")) == "HOME_TEAM"
        else final.get("home_team") if str(final.get("winner")) == "AWAY_TEAM"
        else "Unavailable"
    )
    third_team = (
        third.get("home_team") if str(third.get("winner")) == "HOME_TEAM"
        else third.get("away_team") if str(third.get("winner")) == "AWAY_TEAM"
        else "Unavailable"
    )

    st.markdown("### The tournament is complete")
    st.success(f"{champion} are world champions. Final: {final.get('home_team')} {_score(final)} {final.get('away_team')}.")
    podium = st.columns(3)
    podium[0].metric("Champion", str(champion))
    podium[1].metric("Runner-up", str(runner_up))
    podium[2].metric("Third place", str(third_team))
    st.caption(
        f"Final played {pd.to_datetime(final.get('utc_date'), errors='coerce', utc=True).strftime('%d %b %Y') if pd.notna(pd.to_datetime(final.get('utc_date'), errors='coerce', utc=True)) else 'date unavailable'}"
        f" - {str(final.get('duration') or 'regular time').replace('_', ' ').lower()}."
    )

    if not settled.empty:
        final_prediction = settled.loc[settled["match_id"].astype(str).eq(str(final.get("match_id")))]
        if not final_prediction.empty:
            prediction = final_prediction.iloc[-1]
            st.markdown("### What the closing forecast said")
            forecast = st.columns(4)
            forecast[0].metric("Model call", str(prediction.get("model_result") or "Unavailable").replace("_", " ").title())
            forecast[1].metric("Actual-result probability", _percent(prediction.get("model_actual_probability")))
            forecast[2].metric("Most likely score", str(prediction.get("most_likely_score") or "Unavailable"))
            forecast[3].metric("Forecast status", "Missed final" if not bool(prediction.get("model_correct")) else "Correct")
            st.caption(
                "This is the latest eligible pre-kickoff forecast. It is preserved as evidence, not rewritten after the result."
            )

    if not prices.empty and "prob_champion" in prices.columns:
        st.markdown("### Final market leaderboard")
        leaderboard = prices[[column for column in ["team", "cupmarket_price", "prob_champion", "market_rank"] if column in prices.columns]].copy()
        leaderboard = leaderboard.sort_values("market_rank" if "market_rank" in leaderboard.columns else "cupmarket_price").head(10)
        if "prob_champion" in leaderboard.columns:
            leaderboard["prob_champion"] = leaderboard["prob_champion"].map(_percent)
        leaderboard = leaderboard.rename(
            columns={
                "team": "Country", "cupmarket_price": "Expected settlement value",
                "prob_champion": "Champion chance", "market_rank": "Market rank",
            }
        )
        st.dataframe(leaderboard, hide_index=True, width="stretch")


def _render_tournament_report(retrospective: dict, report_text: str) -> None:
    facts = retrospective.get("facts", {})
    model = retrospective.get("model", {})
    coverage = retrospective.get("coverage", {})
    st.markdown("### Tournament report")
    st.caption("A read-only retrospective generated from the finalized match, market, history and prediction artifacts.")
    facts_columns = st.columns(4)
    facts_columns[0].metric("Counted goals", str(facts.get("total_goals_excluding_penalty_shootout_tallies", "Unavailable")))
    facts_columns[1].metric("Goals per scored match", _metric_value(facts.get("goals_per_goal_scored_match")))
    facts_columns[2].metric("Extra time", str(facts.get("extra_time_matches", "Unavailable")))
    facts_columns[3].metric("Penalty shootouts", str(facts.get("penalty_shootouts", "Unavailable")))
    st.caption(
        f"The goal total excludes shootout tallies: {facts.get('matches_with_goal_scores', 0)} matches had reliable goal scores."
    )

    st.markdown("### Teams that stood out")
    teams = _table(
        retrospective.get("team_performance", [])[:12],
        ["team", "finish_label", "group_points", "group_goal_difference", "goals_for", "cupmarket_price", "performance_index"],
        {
            "team": "Country", "finish_label": "Finish", "group_points": "Group points",
            "group_goal_difference": "Group GD", "goals_for": "Goals",
            "cupmarket_price": "Final market", "performance_index": "Performance index",
        },
    )
    if not teams.empty:
        st.dataframe(teams, hide_index=True, width="stretch")

    st.markdown("### Forecast scorecard")
    scorecard_rows = []
    for label, key in [("All eligible forecasts", "primary"), ("Baseline, adaptive cohort", "baseline"), ("Adaptive, adaptive cohort", "adaptive")]:
        scorecard = model.get(key, {})
        scorecard_rows.append(
            {
                "Cohort": label,
                "Matches": scorecard.get("sample_size", 0),
                "Accuracy": _percent(scorecard.get("accuracy")),
                "Brier": _metric_value(scorecard.get("brier"), 3),
                "Log loss": _metric_value(scorecard.get("log_loss"), 3),
                "Mean confidence": _percent(scorecard.get("mean_confidence")),
            }
        )
    st.dataframe(pd.DataFrame(scorecard_rows), hide_index=True, width="stretch")
    delta = model.get("adaptive_vs_baseline", {})
    st.caption(
        f"Adaptive minus baseline on the same {model.get('adaptive', {}).get('sample_size', 0)}-match cohort: "
        f"Brier {_metric_value(delta.get('brier_delta'), 4)}, log loss {_metric_value(delta.get('log_loss_delta'), 4)}. Positive is worse."
    )

    st.markdown("### Relationships in the data")
    correlations = _table(
        [item for item in retrospective.get("correlations", []) if item.get("sample_size", 0) >= 3],
        ["label", "sample_size", "pearson", "spearman"],
        {"label": "Relationship", "sample_size": "Sample", "pearson": "Pearson", "spearman": "Spearman"},
    )
    if not correlations.empty:
        correlations["Pearson"] = correlations["Pearson"].map(lambda value: f"{float(value):+.3f}")
        correlations["Spearman"] = correlations["Spearman"].map(lambda value: f"{float(value):+.3f}")
        st.dataframe(correlations, hide_index=True, width="stretch")
    st.caption("These are descriptive associations. They do not prove that market price or goals caused later performance.")

    st.markdown("### Surprises and largest moves")
    surprises = _table(
        retrospective.get("model_surprises", [])[:5],
        ["home_team", "away_team", "stage", "model_result", "actual_result", "actual_scoreline", "model_actual_probability"],
        {
            "home_team": "Home", "away_team": "Away", "stage": "Stage",
            "model_result": "Model call", "actual_result": "Actual",
            "actual_scoreline": "Score", "model_actual_probability": "Actual probability",
        },
    )
    if not surprises.empty:
        surprises["Actual probability"] = surprises["Actual probability"].map(_percent)
        st.dataframe(surprises, hide_index=True, width="stretch")
    moves = _table(
        retrospective.get("market_moves", [])[:8],
        ["team", "price_change", "price_change_percent", "trigger_matches"],
        {"team": "Country", "price_change": "Price move", "price_change_percent": "Move %", "trigger_matches": "Event"},
    )
    if not moves.empty:
        moves["Price move"] = moves["Price move"].map(lambda value: f"{float(value):+.2f}")
        moves["Move %"] = moves["Move %"].map(lambda value: f"{float(value):+.1f}%")
        st.dataframe(moves, hide_index=True, width="stretch")

    st.markdown("### Archive coverage")
    coverage_frame = pd.DataFrame(
        [
            {"Check": "Official matches", "Value": coverage.get("official_matches", 0)},
            {"Check": "Settled rows", "Value": coverage.get("settled_prediction_rows", 0)},
            {"Check": "Rows with forecasts", "Value": coverage.get("prediction_rows_with_forecasts", 0)},
            {"Check": "Rows with official results", "Value": coverage.get("prediction_rows_with_actual_results", 0)},
        ]
    )
    st.dataframe(coverage_frame, hide_index=True, width="stretch")
    if report_text:
        st.download_button(
            "Download the full report",
            data=report_text,
            file_name="cupmarket-2026-tournament-retrospective.md",
            mime="text/markdown",
            icon=":material/download:",
        )


def _render_model_verdict(retrospective: dict, adaptive: dict) -> None:
    model = retrospective.get("model", {})
    published_delta = adaptive.get("delta", {}) if isinstance(adaptive, dict) else {}
    st.markdown("### Model verdict")
    metrics = st.columns(4)
    metrics[0].metric("Published guardrail", str(adaptive.get("decision") or "Unavailable").title())
    metrics[1].metric("Guardrail sample", str(adaptive.get("comparison_sample_size", "Unavailable")))
    metrics[2].metric("Guardrail Brier delta", _metric_value(published_delta.get("brier"), 4))
    metrics[3].metric("Retrospective forecasts", str(model.get("primary", {}).get("sample_size", "Unavailable")))
    st.write(str(adaptive.get("message") or "The published guardrail is unavailable."))
    st.caption("The retrospective uses the closing eligible pre-kickoff forecast per match; the live guardrail retains its own published cohort definition.")

    rows = []
    for label, key in [("Baseline", "baseline"), ("Adaptive", "adaptive")]:
        item = model.get(key, {})
        rows.append(
            {
                "Model": label,
                "Matches": item.get("sample_size", 0),
                "Accuracy": _percent(item.get("accuracy")),
                "Brier": _metric_value(item.get("brier"), 4),
                "Log loss": _metric_value(item.get("log_loss"), 4),
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def render_tournament_archive() -> None:
    static = load_static_data()
    matches = static.get("matches", pd.DataFrame())
    prices = static.get("prices", pd.DataFrame())
    history = static.get("history", pd.DataFrame())
    settled = static.get("settled_predictions", pd.DataFrame())
    if matches.empty:
        st.info("The official final match feed is not available in this publication.")
        return

    archive_bundle = load_final_archive_bundle(DATA_DIR, STATE_DIR)
    archive_manifest = archive_bundle.get("archive_manifest", {})
    retrospective = archive_bundle.get("retrospective", {})
    report_text = archive_bundle.get("report_text", "")
    path_data = load_tournament_path_data()
    manifest = load_latest_json(MANIFEST_PATH)
    adaptive = load_latest_json(ADAPTIVE_HEALTH_PATH)
    final = _final_row(matches)
    complete = not final.empty
    archive = manifest.get("archive", {}) if isinstance(manifest, dict) else {}
    archive = {**archive, **{key: value for key, value in archive_manifest.items() if value not in (None, "")}}

    st.markdown("### Archive status")
    if complete:
        st.success(f"Final result: {final.get('home_team')} {_score(final)} {final.get('away_team')}.")
    else:
        st.info("The final has not been published yet. This archive is collecting durable evidence.")

    checkpoint_count = int(history.get("generated_at_utc", pd.Series(dtype=object)).nunique())
    forecast_count = int(settled.get("match_id", pd.Series(dtype=object)).nunique()) if not settled.empty else 0
    archive_state = str(archive.get("status") or "collecting").replace("_", " ").title()
    summary = st.columns(4)
    summary[0].metric("Archive state", archive_state)
    summary[1].metric("Matches", f"{len(matches)}/104")
    summary[2].metric("Market checkpoints", str(checkpoint_count))
    summary[3].metric("Settled forecasts", str(forecast_count))
    st.caption(
        f"Publication {archive.get('archive_id') or 'live collection'} - source commit {str(archive.get('source_commit') or 'unavailable')[:7]}."
    )

    st.markdown("### Choose an archive view")
    st.caption("Each view is read-only. Official prices and results cannot be changed from the archive.")
    archive_view = st.selectbox(
        "Archive view",
        ["Final overview", "Tournament report", "Market replay", "Group-stage record", "Model verdict", "Archive method"],
        key="cupmarket_archive_view",
    )

    if archive_view == "Final overview":
        _render_final_overview(matches, prices, settled, archive)
    elif archive_view == "Tournament report":
        _render_tournament_report(retrospective, report_text)
    elif archive_view == "Market replay":
        if history.empty or not {"team", "generated_at_utc", "cupmarket_price"}.issubset(history.columns):
            st.caption("Market history is not available yet.")
        else:
            teams = sorted(history["team"].dropna().astype(str).unique())
            selected = st.selectbox("Country replay", teams, key="archive_team")
            series = history.loc[history["team"].astype(str).eq(selected)].copy()
            series["generated_at_utc"] = pd.to_datetime(series["generated_at_utc"], errors="coerce", utc=True)
            series["cupmarket_price"] = pd.to_numeric(series["cupmarket_price"], errors="coerce")
            series = series.dropna(subset=["generated_at_utc", "cupmarket_price"]).sort_values("generated_at_utc")
            figure = px.line(series, x="generated_at_utc", y="cupmarket_price", markers=True, title=f"{selected} market path")
            figure.update_layout(template="plotly_white", height=380, margin=dict(l=16, r=16, t=52, b=16))
            figure.update_xaxes(title=None)
            figure.update_yaxes(title="Expected settlement value")
            st.plotly_chart(figure, width="stretch")
    elif archive_view == "Group-stage record":
        _render_group_stage_record(path_data)
    elif archive_view == "Model verdict":
        _render_model_verdict(retrospective, adaptive)
    else:
        st.markdown("### Reproducibility")
        st.write("CupMarket preserves official results, market checkpoints, bracket progress, raw prediction history and a settled final forecast table.")
        checks = archive.get("checks", {}) if isinstance(archive, dict) else {}
        check_frame = pd.DataFrame(
            [{"Check": str(key).replace("_", " ").title(), "Status": "Passed" if value else "Needs attention"} for key, value in checks.items()]
        )
        if not check_frame.empty:
            st.dataframe(check_frame, hide_index=True, width="stretch")
        st.caption("Prices are virtual expected settlement values, not betting odds or real-money prices.")
