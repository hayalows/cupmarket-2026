"""A durable World Cup archive that becomes the default story after the final."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from features.official_data import load_latest_json
from features.tournament_data_v2 import DATA_DIR, load_static_data
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


def _score(row: pd.Series) -> str:
    home = pd.to_numeric(row.get("home_score_full_time"), errors="coerce")
    away = pd.to_numeric(row.get("away_score_full_time"), errors="coerce")
    return "Result pending" if pd.isna(home) or pd.isna(away) else f"{int(home)}-{int(away)}"


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


def render_tournament_archive() -> None:
    static = load_static_data()
    matches = static.get("matches", pd.DataFrame())
    if matches.empty:
        from features.live_match_data import load_matches

        matches, _ = load_matches(DATA_DIR / "world_cup_2026_matches_latest.csv")
    prices = static.get("prices", pd.DataFrame())
    history = static.get("history", pd.DataFrame())
    ledger = static.get("prediction_ledger", pd.DataFrame())
    path_data = load_tournament_path_data()
    manifest = load_latest_json(MANIFEST_PATH)
    adaptive = load_latest_json(ADAPTIVE_HEALTH_PATH)
    final = _final_row(matches)
    complete = not final.empty
    archive = manifest.get("archive", {}) if isinstance(manifest, dict) else {}

    st.markdown("### Archive status")
    st.caption(
        "This page preserves official outcomes, market paths and forecast evidence as a permanent record."
    )
    if complete:
        st.success(
            f"Final result: {final.get('home_team')} {_score(final)} {final.get('away_team')}."
        )
    else:
        st.info("The final has not been published yet. This archive is collecting the durable evidence that will become the post-tournament record.")

    checkpoint_count = int(history.get("generated_at_utc", pd.Series(dtype=object)).nunique())
    forecast_count = int(ledger.get("match_id", pd.Series(dtype=object)).nunique())
    archive_state = str(archive.get("status") or "collecting").replace("_", " ").title()
    st.caption(
        f"Archive coverage: {len(matches)} matches - {checkpoint_count} market checkpoints - "
        f"{forecast_count} saved forecasts - state: {archive_state}."
    )
    st.markdown("### Choose an archive view")
    st.caption("Open one permanent record at a time. Archive views never change official prices.")
    archive_view = st.selectbox(
        "Archive view",
        ["Tournament story", "Market replay", "Group-stage record", "Model verdict", "Archive method"],
        key="cupmarket_archive_view",
    )

    if archive_view == "Tournament story":
        if complete:
            st.markdown("### Final outcome")
            st.write(
                f"**{final.get('home_team')}** and **{final.get('away_team')}** completed the tournament final at **{_score(final)}**."
            )
        else:
            upcoming = matches.loc[matches.get("status", pd.Series(dtype=str)).astype(str).isin({"TIMED", "SCHEDULED"})]
            if upcoming.empty:
                st.caption("The official fixture feed has no remaining scheduled match yet.")
            else:
                next_match = upcoming.sort_values("utc_date").iloc[0]
                st.write(f"Next official fixture: **{next_match.get('home_team')} vs {next_match.get('away_team')}**.")
        if not prices.empty and "prob_champion" in prices.columns:
            leaderboard = prices[["team", "cupmarket_price", "prob_champion", "market_rank"]].copy()
            leaderboard = leaderboard.sort_values("market_rank").head(10)
            leaderboard["prob_champion"] = pd.to_numeric(leaderboard["prob_champion"], errors="coerce").map(lambda value: f"{100 * value:.1f}%")
            leaderboard.columns = ["Country", "Expected settlement value", "Champion chance", "Market rank"]
            st.dataframe(leaderboard, hide_index=True, width="stretch")

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
        decision = str(adaptive.get("decision") or "collecting_evidence").replace("_", " ").title()
        metrics = st.columns(3)
        metrics[0].metric("Adaptive guardrail", decision)
        metrics[1].metric("Comparison sample", int(adaptive.get("comparison_sample_size", 0) or 0))
        delta = adaptive.get("delta", {}) if isinstance(adaptive, dict) else {}
        metrics[2].metric("Brier delta", "Unavailable" if "brier" not in delta else f"{float(delta['brier']):+.3f}")
        st.write(str(adaptive.get("message") or "The forecast comparison is still collecting evidence."))
        st.caption("Open Analysis Lab for match-level Brier score, log loss and calibration evidence.")

    else:
        st.write("CupMarket preserves official results, a commit-pinned publication snapshot, price checkpoints, prediction ledgers and bracket progress. The final archive is therefore reproducible from the same published record used during the tournament.")
        st.caption("Prices are virtual expected settlement values, not betting odds or real-money prices.")
