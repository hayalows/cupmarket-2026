from __future__ import annotations

from hashlib import sha256

import pandas as pd
import streamlit as st

from features.live_match_room import _ordered_selectable, _render_live_room
from features.match_ui import (
    format_number,
    match_option_label,
    prediction_confidence,
    score_text,
)
from features.qualification_ui import (
    cached_qualification_scenarios,
    format_percent,
    render_qualification_result,
)


def _render_selected_match_card(match: pd.Series) -> None:
    kickoff = pd.to_datetime(match.get("utc_date"), errors="coerce", utc=True)
    kickoff_text = (
        kickoff.strftime("%a, %d %b · %H:%M UTC")
        if pd.notna(kickoff)
        else "Kickoff pending"
    )
    status = str(match.get("status", ""))
    if status == "PAUSED":
        state = "HALF TIME"
    elif status == "IN_PLAY":
        minute = pd.to_numeric(match.get("minute"), errors="coerce")
        state = f"LIVE · {int(minute)}'" if pd.notna(minute) else "LIVE"
    elif status in {"FINISHED", "AWARDED"}:
        state = "FULL TIME"
    else:
        state = status.replace("_", " ")

    group = str(match.get("group", "")).replace("GROUP_", "Group ")
    stage = str(match.get("stage", "")).replace("_", " ").title()
    st.markdown(
        f'''
        <div class="cm-match-card cm-selected-match-card">
            <div class="cm-match-meta">{state} · {kickoff_text}</div>
            <div class="cm-match-teams">
                <strong>{match.get('home_team', 'TBD')}</strong>
                <span>{score_text(match)}</span>
                <strong>{match.get('away_team', 'TBD')}</strong>
            </div>
            <div class="cm-match-meta">{group} · {stage}</div>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def _scenario_context_token(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    prices: pd.DataFrame,
    selected_match_id: int,
    team: str,
) -> str:
    """Fingerprint the inputs that can change a qualification calculation."""
    selected_rows = matches[
        pd.to_numeric(matches.get("match_id"), errors="coerce")
        == int(selected_match_id)
    ]
    group = selected_rows.iloc[0].get("group") if not selected_rows.empty else None
    group_rows = matches[matches.get("group").astype(str) == str(group)].copy()
    if "match_id" in group_rows.columns:
        group_rows = group_rows.sort_values("match_id")

    snapshot_columns = [
        "match_id",
        "status",
        "home_score_full_time",
        "away_score_full_time",
        "home_score",
        "away_score",
        "last_updated",
    ]
    available_columns = [
        column for column in snapshot_columns if column in group_rows.columns
    ]
    group_snapshot = tuple(
        tuple(str(value) for value in row)
        for row in group_rows[available_columns].itertuples(index=False, name=None)
    )

    def latest_generation(frame: pd.DataFrame) -> str:
        if frame.empty or "generated_at_utc" not in frame.columns:
            return ""
        timestamps = pd.to_datetime(
            frame["generated_at_utc"], errors="coerce", utc=True
        ).dropna()
        return "" if timestamps.empty else timestamps.max().isoformat()

    payload = (
        int(selected_match_id),
        str(team),
        str(group),
        group_snapshot,
        latest_generation(predictions),
        latest_generation(prices),
    )
    return sha256(repr(payload).encode("utf-8")).hexdigest()[:20]


def _render_saved_forecast(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    prices: pd.DataFrame,
    selected_match_id: int,
    match: pd.Series,
    prediction: pd.Series,
) -> None:
    if prediction.empty or pd.isna(prediction.get("prob_home_win")):
        st.info("A saved probability forecast is not available for this match yet.")
        return

    confidence, top_probability, separation = prediction_confidence(prediction)
    st.markdown("#### Pre-match forecast")
    outcomes = st.columns(3)
    outcomes[0].metric(
        f"{match.get('home_team')} win",
        format_percent(prediction.get("prob_home_win")),
    )
    outcomes[1].metric("Draw", format_percent(prediction.get("prob_draw")))
    outcomes[2].metric(
        f"{match.get('away_team')} win",
        format_percent(prediction.get("prob_away_win")),
    )

    with st.expander("More forecast detail", expanded=False):
        details = st.columns(4)
        details[0].metric(
            "Home expected goals",
            format_number(prediction.get("expected_home_goals")),
        )
        details[1].metric(
            "Away expected goals",
            format_number(prediction.get("expected_away_goals")),
        )
        details[2].metric(
            "Most likely score",
            prediction.get("most_likely_score", "—"),
            delta=format_percent(prediction.get("most_likely_score_probability")),
        )
        details[3].metric(
            "Model confidence",
            confidence,
            delta=f"{format_percent(top_probability)} leading outcome",
        )
        extras = st.columns(3)
        extras[0].metric(
            "Both teams score",
            format_percent(prediction.get("prob_btts_yes")),
        )
        extras[1].metric(
            "Over 2.5 goals",
            format_percent(prediction.get("prob_over_2_5")),
        )
        extras[2].metric("Outcome separation", format_percent(separation))

    is_future_group_match = (
        match.get("stage") == "GROUP_STAGE"
        and match.get("status") in {"TIMED", "SCHEDULED"}
    )
    if is_future_group_match:
        result_key = f"compact_match_impact_result_{selected_match_id}"
        stored_before_open = st.session_state.get(result_key)
        with st.expander(
            "Qualification impact of a win, draw or loss",
            expanded=bool(stored_before_open),
        ):
            team = st.selectbox(
                "Analyse qualification impact for",
                [match.get("home_team"), match.get("away_team")],
                key=f"compact_match_impact_{selected_match_id}",
            )
            context_token = _scenario_context_token(
                matches,
                predictions,
                prices,
                selected_match_id,
                str(team),
            )
            stored = st.session_state.get(result_key)
            has_current_result = bool(
                stored
                and stored.get("team") == team
                and stored.get("context_token") == context_token
            )

            button_label = (
                "Recalculate qualification paths"
                if has_current_result
                else "Calculate qualification paths"
            )
            if st.button(
                button_label,
                key=f"compact_calculate_match_impact_{selected_match_id}",
                use_container_width=True,
            ):
                strength = (
                    dict(zip(prices["team"], prices["cupmarket_price"]))
                    if not prices.empty
                    else {}
                )
                with st.spinner("Simulating the remaining group stage..."):
                    result = cached_qualification_scenarios(
                        matches,
                        predictions,
                        team,
                        tuple(sorted(strength.items())),
                        1500,
                    )
                st.session_state[result_key] = {
                    "team": team,
                    "context_token": context_token,
                    "result": result,
                }
                stored = st.session_state[result_key]
                has_current_result = True

            if has_current_result and stored:
                render_qualification_result(stored["result"], compact=True)
                st.caption(
                    "This result stays on screen during automatic score refreshes. "
                    "CupMarket asks for a new calculation only when the selected team, "
                    "group results or published model inputs change."
                )
            elif stored and stored.get("team") == team:
                st.info(
                    "The score feed or published model changed after this calculation. "
                    "Calculate again to use the newest inputs."
                )

    st.caption(
        "This is the saved pre-match view. Official country prices and tournament "
        "probabilities change after completed results are processed."
    )


def render_compact_match_room(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    prices: pd.DataFrame,
) -> None:
    if matches.empty:
        st.warning("No matches are available.")
        return

    statuses = sorted(matches["status"].dropna().unique())
    filter_key = "cupmarket_match_status_filter"
    if st.session_state.pop("cupmarket_reset_status_filter", False):
        st.session_state[filter_key] = statuses

    with st.popover("Filter or refresh matches", use_container_width=True):
        selected_statuses = st.multiselect(
            "Match states",
            statuses,
            default=statuses,
            key=filter_key,
        )
        st.caption("Live matches are always ordered first, followed by upcoming fixtures.")
        if st.button(
            "Refresh live scores",
            key="compact_match_refresh",
            use_container_width=True,
            help="Clears the 60-second score cache and requests the latest match states.",
        ):
            st.cache_data.clear()
            st.rerun()

    filtered = matches[matches["status"].isin(selected_statuses)].copy()
    selectable = _ordered_selectable(filtered)
    if selectable.empty:
        st.info("No complete matchup is available for the selected filters.")
        return

    option_rows = {
        int(row.match_id): pd.Series(row._asdict())
        for row in selectable.itertuples(index=False)
    }
    option_ids = list(option_rows)
    selector_key = "cupmarket_match_selector"
    preferred = st.session_state.pop("cupmarket_selected_match_id", None)
    if preferred in option_rows:
        st.session_state[selector_key] = int(preferred)
    elif (
        selector_key not in st.session_state
        or st.session_state[selector_key] not in option_rows
    ):
        st.session_state[selector_key] = option_ids[0]

    selected_match_id = st.selectbox(
        "Selected match",
        option_ids,
        format_func=lambda match_id: match_option_label(option_rows[match_id]),
        key=selector_key,
    )
    match = option_rows[int(selected_match_id)]
    _render_selected_match_card(match)

    prediction_rows = (
        predictions[predictions["match_id"] == int(selected_match_id)]
        if not predictions.empty
        else pd.DataFrame()
    )
    prediction = (
        prediction_rows.iloc[-1]
        if not prediction_rows.empty
        else pd.Series(dtype=object)
    )

    if _render_live_room(
        matches,
        predictions,
        prices,
        int(selected_match_id),
        prediction,
    ):
        return

    _render_saved_forecast(
        matches,
        predictions,
        prices,
        int(selected_match_id),
        match,
        prediction,
    )
