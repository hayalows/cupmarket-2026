from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from features.live_match_data import format_source_time, load_matches
from features.match_ui import combine_prediction_sources, prediction_confidence
from features.tournament_data import (
    DATA_DIR,
    actual_outcome,
    batch_context_for_match,
    leading_outcome_label,
    load_static_data,
    outcome_probability,
    reference_prediction,
)

ROOT = Path(__file__).resolve().parents[1]
LIVE_STATUSES = {"IN_PLAY", "PAUSED"}
UPCOMING_STATUSES = {"TIMED", "SCHEDULED"}
FINISHED_STATUSES = {"FINISHED", "AWARDED"}


def inject_styles() -> None:
    for path in [ROOT / "assets" / "product.css", ROOT / "assets" / "group_tools.css", ROOT / "assets" / "pulse_v3.css"]:
        if path.exists():
            st.markdown(f"<style>{path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def _score(row: pd.Series) -> str:
    home = pd.to_numeric(row.get("home_score_full_time"), errors="coerce")
    away = pd.to_numeric(row.get("away_score_full_time"), errors="coerce")
    return "vs" if pd.isna(home) or pd.isna(away) else f"{int(home)}–{int(away)}"


def _kickoff(value, short: bool = False) -> str:
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(timestamp):
        return "Time pending"
    return timestamp.strftime("%d %b · %H:%M UTC" if short else "%A, %d %B · %H:%M UTC")


def _group(value) -> str:
    return str(value or "").replace("GROUP_", "Group ").replace("_", " ").title()


def _pct(value, digits: int = 1) -> str:
    number = pd.to_numeric(value, errors="coerce")
    return "—" if pd.isna(number) else f"{100 * float(number):.{digits}f}%"


def _open_match_room(match_id: int) -> None:
    st.session_state["cupmarket_selected_match_id"] = int(match_id)
    st.session_state["cupmarket_reset_status_filter"] = True
    st.switch_page("pages/1_Match_Intelligence.py")


def _prediction_outcome(prediction: pd.Series) -> str | None:
    if prediction.empty:
        return None
    values = {
        "HOME_WIN": pd.to_numeric(prediction.get("prob_home_win"), errors="coerce"),
        "DRAW": pd.to_numeric(prediction.get("prob_draw"), errors="coerce"),
        "AWAY_WIN": pd.to_numeric(prediction.get("prob_away_win"), errors="coerce"),
    }
    valid = {key: float(value) for key, value in values.items() if pd.notna(value)}
    return max(valid, key=valid.get) if valid else None


def _finished_review_rows(finished: pd.DataFrame, prediction_ledger: pd.DataFrame) -> tuple[pd.DataFrame, list[int]]:
    rows = []
    ids = []
    for match in finished.itertuples(index=False):
        series = pd.Series(match._asdict())
        prediction, source = reference_prediction(prediction_ledger, series)
        likely_score = str(prediction.get("most_likely_score", "—")) if not prediction.empty else "—"
        likely_prob = _pct(prediction.get("most_likely_score_probability")) if not prediction.empty else "—"
        rows.append(
            {
                "Result": f"{series.get('home_team')} {_score(series)} {series.get('away_team')}",
                "Model view": leading_outcome_label(prediction, series),
                "Likely score": f"{likely_score} · {likely_prob}" if likely_score != "—" else "—",
                "Forecast record": source,
            }
        )
        ids.append(int(series["match_id"]))
    return pd.DataFrame(rows), ids


def _render_market_reaction(match: pd.Series, processed: pd.DataFrame, history: pd.DataFrame) -> None:
    context = batch_context_for_match(int(match["match_id"]), processed, history)
    st.markdown("#### Market reaction")
    if not context.get("available"):
        st.info("This result has not yet been linked to a published model update.")
        return
    snapshot = context.get("snapshot", pd.DataFrame())
    batch = context.get("batch_matches", pd.DataFrame())
    snapshot_time = context.get("snapshot_time")
    if snapshot.empty:
        st.info("A matching historical price snapshot is unavailable for this result.")
    else:
        columns = st.columns(2)
        for column, team in zip(columns, [str(match.get("home_team")), str(match.get("away_team"))]):
            team_rows = snapshot[snapshot["team"] == team]
            with column:
                st.markdown(f"**{team}**")
                if team_rows.empty:
                    st.caption("No price row was found in this update snapshot.")
                    continue
                row = team_rows.iloc[-1]
                price = pd.to_numeric(row.get("cupmarket_price"), errors="coerce")
                previous = pd.to_numeric(row.get("previous_price"), errors="coerce")
                change = pd.to_numeric(row.get("price_change"), errors="coerce")
                percent = pd.to_numeric(row.get("price_change_percent"), errors="coerce")
                delta = None
                if pd.notna(change):
                    sign = "+" if float(change) > 0 else ""
                    pct_text = f" · {float(percent):+.2f}%" if pd.notna(percent) else ""
                    delta = f"{sign}{float(change):.2f} CM{pct_text}"
                st.metric(
                    "Published price after update",
                    f"{float(price):.2f} CM" if pd.notna(price) else "—",
                    delta=delta,
                )
                st.caption(
                    f"Previous: {float(previous):.2f} CM"
                    if pd.notna(previous)
                    else "Previous official value unavailable"
                )
    if not batch.empty:
        time_text = "time unavailable" if pd.isna(snapshot_time) else pd.Timestamp(snapshot_time).strftime("%d %b · %H:%M UTC")
        st.caption(
            f"This result was included in the model update published {time_text}. "
            f"That update processed {len(batch)} completed match{'es' if len(batch) != 1 else ''}; "
            "the movement is batch-level market reaction, not proof that one result caused every change."
        )
        with st.expander("Matches included in the same update", expanded=False):
            for row in batch.sort_values("utc_date").itertuples(index=False):
                st.write(f"• {row.home_team} {int(row.home_score)}–{int(row.away_score)} {row.away_team}")


def _render_result_detail(match: pd.Series, prediction_ledger: pd.DataFrame, processed: pd.DataFrame, history: pd.DataFrame) -> None:
    prediction, source = reference_prediction(prediction_ledger, match)
    actual = actual_outcome(match)
    leading = _prediction_outcome(prediction)
    actual_prob = outcome_probability(prediction, actual)

    st.markdown(
        f'''
        <div class="cm-match-card cm-selected-match-card">
            <div class="cm-match-meta">FULL TIME · {_group(match.get('group'))} · {_kickoff(match.get('utc_date'), True)}</div>
            <div class="cm-match-teams">
                <strong>{match.get('home_team')}</strong>
                <span>{_score(match)}</span>
                <strong>{match.get('away_team')}</strong>
            </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    st.markdown("#### Forecast review")
    if prediction.empty:
        st.info("No stored model forecast is available for this match.")
    else:
        metrics = st.columns(3)
        metrics[0].metric("Model's leading outcome", leading_outcome_label(prediction, match))
        metrics[1].metric(
            "Most likely scoreline",
            str(prediction.get("most_likely_score", "—")),
            delta=_pct(prediction.get("most_likely_score_probability")),
            delta_color="off",
        )
        metrics[2].metric("Probability of actual outcome", _pct(actual_prob))

        if source == "Saved pre-match forecast":
            if leading == actual:
                st.success("The model's leading result direction occurred.")
            else:
                st.warning("The actual result differed from the model's leading outcome.")
        else:
            st.info(
                f"Forecast record: {source}. This is shown for comparison but is not counted as a verified pre-match prediction."
            )

        with st.expander("Full pre-match probability view", expanded=False):
            probs = st.columns(3)
            probs[0].metric(f"{match.get('home_team')} win", _pct(prediction.get("prob_home_win")))
            probs[1].metric("Draw", _pct(prediction.get("prob_draw")))
            probs[2].metric(f"{match.get('away_team')} win", _pct(prediction.get("prob_away_win")))
            expected = st.columns(2)
            home_xg = pd.to_numeric(prediction.get("expected_home_goals"), errors="coerce")
            away_xg = pd.to_numeric(prediction.get("expected_away_goals"), errors="coerce")
            expected[0].metric("Home expected goals", f"{float(home_xg):.2f}" if pd.notna(home_xg) else "—")
            expected[1].metric("Away expected goals", f"{float(away_xg):.2f}" if pd.notna(away_xg) else "—")
            confidence, top, separation = prediction_confidence(prediction)
            st.caption(
                f"Forecast clarity: {confidence}. Leading outcome {100 * top:.1f}%; outcome separation {100 * separation:.1f} percentage points."
            )

    _render_market_reaction(match, processed, history)


def _render_results(matches: pd.DataFrame, static: dict[str, pd.DataFrame]) -> None:
    finished = matches[matches["status"].isin(FINISHED_STATUSES)].copy().sort_values("utc_date", ascending=False)
    prediction_ledger = static["prediction_ledger"]
    processed = static["processed_ledger"]
    history = static["history"]

    true_predictions = 0
    correct = 0
    for row in finished.itertuples(index=False):
        match = pd.Series(row._asdict())
        prediction, source = reference_prediction(prediction_ledger, match)
        if source == "Saved pre-match forecast" and not prediction.empty:
            true_predictions += 1
            correct += int(_prediction_outcome(prediction) == actual_outcome(match))

    summary = st.columns(3)
    summary[0].metric("Completed matches", len(finished))
    summary[1].metric("Verified pre-match records", true_predictions)
    summary[2].metric(
        "Leading-outcome accuracy",
        f"{100 * correct / true_predictions:.1f}%" if true_predictions else "—",
    )
    if true_predictions < 10:
        st.caption("Early sample: performance measures can change materially as more verified matches are completed.")

    if finished.empty:
        st.info("No completed matches yet.")
        return

    countries = sorted(set(finished["home_team"]).union(set(finished["away_team"])))
    groups = sorted(finished["group"].dropna().astype(str).unique())
    with st.popover("Filter results", use_container_width=True):
        country = st.selectbox("Country", ["All countries", *countries])
        group = st.selectbox("Group", ["All groups", *groups])
    filtered = finished.copy()
    if country != "All countries":
        filtered = filtered[(filtered["home_team"] == country) | (filtered["away_team"] == country)]
    if group != "All groups":
        filtered = filtered[filtered["group"].astype(str) == group]

    review_table, match_ids = _finished_review_rows(filtered, prediction_ledger)
    event = st.dataframe(
        review_table,
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key="match_hub_results_table",
    )
    rows = getattr(getattr(event, "selection", None), "rows", [])
    requested = st.session_state.pop("cupmarket_match_hub_match_id", None)
    selected_id = requested if requested in match_ids else st.session_state.get("match_hub_selected_result")
    if rows:
        selected_id = match_ids[int(rows[0])]
    if selected_id not in match_ids:
        selected_id = match_ids[0]
    st.session_state["match_hub_selected_result"] = int(selected_id)
    selected = filtered[filtered["match_id"] == int(selected_id)].iloc[0]
    _render_result_detail(selected, prediction_ledger, processed, history)


def _current_predictions(static: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return combine_prediction_sources(static["latest_predictions"], static["prediction_ledger"])


def _render_live(matches: pd.DataFrame) -> None:
    live = matches[matches["status"].isin(LIVE_STATUSES)].copy().sort_values("utc_date")
    if live.empty:
        upcoming = matches[matches["status"].isin(UPCOMING_STATUSES)].copy().sort_values("utc_date")
        st.info("No match is live. The next fixture is ready in Upcoming.")
        if not upcoming.empty and st.button("Open next fixture", type="primary", use_container_width=True):
            st.session_state["match_hub_view_control"] = "Upcoming"
            st.session_state["cupmarket_match_hub_match_id"] = int(upcoming.iloc[0]["match_id"])
            st.rerun()
        return
    for row in live.itertuples(index=False):
        match = pd.Series(row._asdict())
        minute = pd.to_numeric(match.get("minute"), errors="coerce")
        clock = "HT" if str(match.get("status")) == "PAUSED" else (f"{int(minute)}'" if pd.notna(minute) else "LIVE")
        with st.container(border=True):
            st.markdown(f"**{match.get('home_team')} {_score(match)} {match.get('away_team')}**")
            st.caption(f"{clock} · {_group(match.get('group'))}")
            if st.button("Open live intelligence", key=f"hub_live_{int(match['match_id'])}", use_container_width=True):
                _open_match_room(int(match["match_id"]))


def _render_upcoming(matches: pd.DataFrame, static: dict[str, pd.DataFrame]) -> None:
    upcoming = matches[matches["status"].isin(UPCOMING_STATUSES)].copy().sort_values("utc_date")
    if upcoming.empty:
        st.info("No upcoming fixtures are available.")
        return
    predictions = _current_predictions(static)
    prediction_columns = [
        column
        for column in ["match_id", "prob_home_win", "prob_draw", "prob_away_win", "most_likely_score"]
        if column in predictions.columns
    ]
    if "match_id" in prediction_columns:
        merged = upcoming.merge(predictions[prediction_columns], on="match_id", how="left")
    else:
        merged = upcoming.copy()
    display = pd.DataFrame(
        {
            "Fixture": merged.apply(lambda row: f"{row['home_team']} vs {row['away_team']}", axis=1),
            "Kickoff": merged["utc_date"].map(lambda value: _kickoff(value, True)),
            "Model view": merged.apply(lambda row: leading_outcome_label(row, row), axis=1),
        }
    )
    event = st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key="match_hub_upcoming_table",
    )
    requested = st.session_state.pop("cupmarket_match_hub_match_id", None)
    ids = merged["match_id"].astype(int).tolist()
    selected_id = requested if requested in ids else st.session_state.get("match_hub_selected_upcoming")
    rows = getattr(getattr(event, "selection", None), "rows", [])
    if rows:
        selected_id = ids[int(rows[0])]
    if selected_id not in ids:
        selected_id = ids[0]
    st.session_state["match_hub_selected_upcoming"] = int(selected_id)
    match = merged[merged["match_id"] == int(selected_id)].iloc[0]
    with st.container(border=True):
        st.markdown(f"### {match.get('home_team')} vs {match.get('away_team')}")
        st.caption(f"{_kickoff(match.get('utc_date'))} · {_group(match.get('group'))}")
        probabilities = st.columns(3)
        probabilities[0].metric(f"{match.get('home_team')} win", _pct(match.get("prob_home_win")))
        probabilities[1].metric("Draw", _pct(match.get("prob_draw")))
        probabilities[2].metric(f"{match.get('away_team')} win", _pct(match.get("prob_away_win")))
        st.caption(f"Most likely scoreline: {match.get('most_likely_score', '—')}")
        if st.button("Open full match forecast", type="primary", use_container_width=True):
            _open_match_room(int(match["match_id"]))


def render_match_hub() -> None:
    matches, source = load_matches(DATA_DIR / "world_cup_2026_matches_latest.csv")
    static = load_static_data()

    st.markdown(
        '''
        <div class="cm-hero">
            <div class="cm-eyebrow">CupMarket 2026 · Match Hub</div>
            <h1>Every match, one consistent path.</h1>
            <p>Move from live action to completed-result review or the next fixture without learning a different navigation system.</p>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    requested = st.session_state.pop("cupmarket_match_hub_view", None)
    options = ["Live", "Results", "Upcoming"]
    default = "Live" if not matches.empty and matches["status"].isin(LIVE_STATUSES).any() else "Results"
    if requested in options:
        st.session_state["match_hub_view_control"] = requested
    elif st.session_state.get("match_hub_view_control") not in options:
        st.session_state["match_hub_view_control"] = default

    view = st.segmented_control(
        "Match view",
        options,
        key="match_hub_view_control",
        selection_mode="single",
    ) or default

    st.caption(
        f"Score source: {source.get('source', 'Unknown')} · refreshed {format_source_time(source.get('fetched_at_utc'))}"
    )
    if source.get("warning"):
        st.warning(source["warning"] + " Showing the latest saved snapshot.")

    if view == "Live":
        _render_live(matches)
    elif view == "Results":
        _render_results(matches, static)
    else:
        _render_upcoming(matches, static)
