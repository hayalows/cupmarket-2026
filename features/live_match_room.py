from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from backend.live_qualification import (
    LIVE_STATUSES,
    build_provisional_snapshot,
    next_goal_impacts,
)
from features.live_qualification_ui import cached_projection, pct
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


def _minute_text(row: pd.Series) -> str:
    if str(row.get("status", "")) == "PAUSED":
        return "HT"
    minute = row.get("minute")
    return f"{int(minute)}'" if minute is not None and pd.notna(minute) else "LIVE"


def _pp_delta(current, baseline) -> str | None:
    if current is None or baseline is None or pd.isna(current) or pd.isna(baseline):
        return None
    return f"{100 * (float(current) - float(baseline)):+.1f} pp vs published model"


def _market_row(prices: pd.DataFrame, team: str) -> pd.Series:
    if prices.empty or "team" not in prices.columns:
        return pd.Series(dtype=object)
    rows = prices[prices["team"] == team]
    return rows.iloc[0] if not rows.empty else pd.Series(dtype=object)


def _pressure_label(live_qualification, published_qualification) -> str:
    if (
        live_qualification is None
        or published_qualification is None
        or pd.isna(live_qualification)
        or pd.isna(published_qualification)
    ):
        return "Direction unavailable"
    difference = float(live_qualification) - float(published_qualification)
    if difference >= 0.05:
        return "Likely upward pressure"
    if difference <= -0.05:
        return "Likely downward pressure"
    return "No clear directional signal"


def _render_table(rows: list[dict[str, Any]]) -> None:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return
    columns = [
        "position",
        "team",
        "played",
        "wins",
        "draws",
        "losses",
        "goal_difference",
        "points",
    ]
    frame = frame[[column for column in columns if column in frame.columns]].rename(
        columns={
            "position": "Pos",
            "team": "Country",
            "played": "P",
            "wins": "W",
            "draws": "D",
            "losses": "L",
            "goal_difference": "GD",
            "points": "Pts",
        }
    )
    st.dataframe(frame, use_container_width=True, hide_index=True)


def _render_score_cards(active_matches: pd.DataFrame) -> None:
    if active_matches.empty:
        return
    columns = st.columns(min(2, len(active_matches)))
    for index, row in enumerate(active_matches.itertuples(index=False)):
        series = pd.Series(row._asdict())
        with columns[index % len(columns)]:
            st.markdown(
                f'''
                <div class="cm-match-card">
                    <div class="cm-match-meta">● LIVE · {_minute_text(series)}</div>
                    <div class="cm-match-teams">
                        <strong>{series.get('home_team', 'TBD')}</strong>
                        <span>{score_text(series)}</span>
                        <strong>{series.get('away_team', 'TBD')}</strong>
                    </div>
                </div>
                ''',
                unsafe_allow_html=True,
            )


def _build_context(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    prices: pd.DataFrame,
    match_id: int,
) -> dict[str, Any] | None:
    rows = matches[matches["match_id"] == int(match_id)]
    if rows.empty or rows.iloc[0].get("status") not in LIVE_STATUSES:
        return None
    match = rows.iloc[0]
    strength = (
        dict(zip(prices["team"], prices["cupmarket_price"]))
        if not prices.empty
        else {}
    )
    result = cached_projection(
        matches,
        predictions,
        tuple(sorted(strength.items())),
        str(match.get("home_team")),
        1600,
    )
    live = result.get("matches", {}).get(int(match_id))
    if not result.get("available") or not live:
        return None
    snapshot = build_provisional_snapshot(matches, strength)
    group = str(match.get("group", "")).replace("GROUP_", "")
    active = matches[
        (matches["stage"] == "GROUP_STAGE")
        & (matches["group"].astype(str).str.replace("GROUP_", "") == group)
        & matches["status"].isin(LIVE_STATUSES)
    ].copy()
    return {
        "match": match,
        "result": result,
        "live": live,
        "snapshot": snapshot,
        "strength": strength,
        "group": group,
        "active": active,
    }


def _render_live_room(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    prices: pd.DataFrame,
    match_id: int,
    prediction_row: pd.Series,
) -> bool:
    context = _build_context(matches, predictions, prices, match_id)
    if not context:
        return False

    match = context["match"]
    result = context["result"]
    live = context["live"]
    snapshot = context["snapshot"]
    home_team = str(match.get("home_team"))
    away_team = str(match.get("away_team"))

    st.info(
        "Live Match Room is active. Scores and in-play projections can change when "
        "the feed refreshes. Official ratings, tournament probabilities and prices "
        "stay fixed until the final result is processed."
    )
    outlook_tab, qualification_tab, group_tab, market_tab, model_tab = st.tabs(
        [
            "Live outlook",
            "Qualification",
            "Group picture",
            "Market context",
            "Pre-match model",
        ]
    )

    with outlook_tab:
        st.markdown("#### What is most likely from here?")
        st.caption(
            f"Current score: {live['current_score']} after about "
            f"{live.get('minute', 0)} minutes."
        )
        columns = st.columns(3)
        columns[0].metric(f"{home_team} win", pct(live["home_win_probability"]))
        columns[1].metric("Draw", pct(live["draw_probability"]))
        columns[2].metric(f"{away_team} win", pct(live["away_win_probability"]))

        if not prediction_row.empty and pd.notna(prediction_row.get("prob_home_win")):
            st.markdown("##### Movement since kickoff")
            comparison = st.columns(3)
            comparison[0].metric(
                f"{home_team} outlook",
                pct(live["home_win_probability"]),
                delta=_pp_delta(
                    live["home_win_probability"], prediction_row.get("prob_home_win")
                ),
            )
            comparison[1].metric(
                "Draw outlook",
                pct(live["draw_probability"]),
                delta=_pp_delta(
                    live["draw_probability"], prediction_row.get("prob_draw")
                ),
            )
            comparison[2].metric(
                f"{away_team} outlook",
                pct(live["away_win_probability"]),
                delta=_pp_delta(
                    live["away_win_probability"], prediction_row.get("prob_away_win")
                ),
            )

        scorelines = pd.DataFrame(live.get("likely_scorelines", []))
        if not scorelines.empty:
            scorelines["probability"] = scorelines["probability"].map(pct)
            st.markdown("##### Most likely final scorelines")
            st.dataframe(
                scorelines.rename(
                    columns={"score": "Final score", "probability": "Probability"}
                ),
                use_container_width=True,
                hide_index=True,
            )
        st.caption(result["method_note"] + " These are estimates, not guarantees.")

    with qualification_tab:
        st.markdown("#### What does the current score mean for qualification?")
        team_columns = st.columns(2)
        for column, team in zip(team_columns, [home_team, away_team]):
            team_result = result.get("teams", {}).get(team, {})
            provisional = snapshot.get("team_status", {}).get(team, {})
            with column:
                st.markdown(f"##### {team}")
                st.metric(
                    "Live qualification probability",
                    pct(team_result.get("qualification_probability")),
                )
                details = st.columns(2)
                details[0].metric(
                    "Top-two probability",
                    pct(team_result.get("direct_top_two_probability")),
                )
                details[1].metric(
                    "Most likely group finish",
                    team_result.get("most_likely_position", "—"),
                )
                st.markdown(
                    f"**If the score held now:** "
                    f"{provisional.get('status_if_ended_now', 'Status unavailable')}"
                )
                st.caption(
                    f"Provisional position {provisional.get('position', '—')} · "
                    f"{provisional.get('points', '—')} points · "
                    f"goal difference {provisional.get('goal_difference', '—')}"
                )

    with group_tab:
        group = context["group"]
        st.markdown(f"#### Group {group} as one connected system")
        st.caption(
            "A goal in this match or another live match in the group can move several "
            "countries at once."
        )
        _render_score_cards(context["active"])
        st.markdown("##### Table if the current scores held")
        _render_table(snapshot.get("tables", {}).get(group, []))
        focus_team = st.radio(
            "Show next-goal impact for",
            [home_team, away_team],
            horizontal=True,
            key=f"live_goal_impact_{match_id}",
        )
        impacts = next_goal_impacts(matches, focus_team, context["strength"])
        if impacts:
            impact_frame = pd.DataFrame(impacts).rename(
                columns={
                    "event": "Possible next goal",
                    "position": "New position",
                    "status": "Qualification status if scores then held",
                    "position_change": "Position movement",
                }
            )
            st.markdown("##### What the next goal could change")
            st.dataframe(impact_frame, use_container_width=True, hide_index=True)

    with market_tab:
        st.markdown("#### What this could mean for the country market")
        st.warning(
            "These are not live trading prices. CupMarket publishes a new official "
            "price only after full time and a successful tournament-model update."
        )
        market_columns = st.columns(2)
        for column, team in zip(market_columns, [home_team, away_team]):
            row = _market_row(prices, team)
            team_result = result.get("teams", {}).get(team, {})
            live_qualification = team_result.get("qualification_probability")
            published_qualification = (
                row.get("prob_reach_round_32") if not row.empty else None
            )
            pressure = _pressure_label(live_qualification, published_qualification)
            with column:
                st.markdown(f"##### {team}")
                st.metric(
                    "Published CupMarket price",
                    f"{float(row.get('cupmarket_price')):.2f} CM"
                    if not row.empty and pd.notna(row.get("cupmarket_price"))
                    else "—",
                )
                details = st.columns(2)
                details[0].metric(
                    "Published market rank",
                    int(row.get("market_rank"))
                    if not row.empty and pd.notna(row.get("market_rank"))
                    else "—",
                )
                details[1].metric(
                    "Published champion chance",
                    pct(row.get("prob_champion")) if not row.empty else "—",
                )
                st.metric(
                    "Live qualification outlook",
                    pct(live_qualification),
                    delta=_pp_delta(live_qualification, published_qualification),
                )
                if pressure == "Likely upward pressure":
                    st.success(pressure)
                elif pressure == "Likely downward pressure":
                    st.error(pressure)
                else:
                    st.info(pressure)
        st.caption(
            "The direction compares the live qualification projection with the last "
            "published Round-of-32 probability. Final price movement can differ because "
            "the full tournament, Elo, form and knockout route are recalculated together."
        )

    with model_tab:
        st.markdown("#### The model view before kickoff")
        st.caption(
            "This forecast is intentionally frozen so it can be compared with the "
            "current match state."
        )
        if prediction_row.empty or pd.isna(prediction_row.get("prob_home_win")):
            st.info("A saved pre-match forecast is not available for this fixture.")
        else:
            outcomes = st.columns(3)
            outcomes[0].metric(
                f"{home_team} win", format_percent(prediction_row.get("prob_home_win"))
            )
            outcomes[1].metric("Draw", format_percent(prediction_row.get("prob_draw")))
            outcomes[2].metric(
                f"{away_team} win", format_percent(prediction_row.get("prob_away_win"))
            )
            details = st.columns(4)
            details[0].metric(
                "Home expected goals",
                format_number(prediction_row.get("expected_home_goals")),
            )
            details[1].metric(
                "Away expected goals",
                format_number(prediction_row.get("expected_away_goals")),
            )
            details[2].metric(
                "Most likely score", prediction_row.get("most_likely_score", "—")
            )
            details[3].metric(
                "Both teams score", format_percent(prediction_row.get("prob_btts_yes"))
            )
    return True


def _render_live_entries(matches: pd.DataFrame) -> None:
    live_matches = matches[matches["status"].isin(LIVE_STATUSES)].copy()
    if live_matches.empty:
        return
    live_matches = live_matches.sort_values(["utc_date", "match_id"])
    st.markdown("### Live now")
    st.caption(
        "Open a match to move from the score into live outlook, qualification, "
        "group effects and market context."
    )
    columns = st.columns(min(3, len(live_matches)))
    for index, row in enumerate(live_matches.itertuples(index=False)):
        series = pd.Series(row._asdict())
        with columns[index % len(columns)]:
            st.markdown(
                f'''
                <div class="cm-match-card">
                    <div class="cm-match-meta">● LIVE · {_minute_text(series)} · {str(series.get('group', '')).replace('GROUP_', 'Group ')}</div>
                    <div class="cm-match-teams">
                        <strong>{series.get('home_team', 'TBD')}</strong>
                        <span>{score_text(series)}</span>
                        <strong>{series.get('away_team', 'TBD')}</strong>
                    </div>
                    <div class="cm-match-meta">Open for outlook, qualification, group and market context.</div>
                </div>
                ''',
                unsafe_allow_html=True,
            )
            if st.button(
                "Open live match room",
                key=f"open_live_match_{int(series['match_id'])}",
                use_container_width=True,
            ):
                st.session_state["cupmarket_selected_match_id"] = int(
                    series["match_id"]
                )
                st.session_state["cupmarket_reset_status_filter"] = True
                st.rerun()


def _ordered_selectable(filtered: pd.DataFrame) -> pd.DataFrame:
    base = filtered[
        filtered["home_team"].notna() & filtered["away_team"].notna()
    ].copy()
    return pd.concat(
        [
            base[base["status"].isin(LIVE_STATUSES)].sort_values("utc_date"),
            base[base["status"].isin(["TIMED", "SCHEDULED"])].sort_values(
                "utc_date"
            ),
            base[base["status"] == "FINISHED"].sort_values(
                "utc_date", ascending=False
            ),
            base[
                ~base["status"].isin(
                    list(LIVE_STATUSES) + ["TIMED", "SCHEDULED", "FINISHED"]
                )
            ].sort_values("utc_date"),
        ],
        ignore_index=True,
    )


def render_live_match_centre(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    prices: pd.DataFrame,
) -> None:
    st.markdown("### Fixtures and match intelligence")
    st.caption(
        "Before kickoff, read the saved model forecast. During play, the same fixture "
        "becomes a live intelligence room."
    )
    if st.button(
        "Refresh live scores",
        help="Clears the 60-second score cache. Avoid repeated refreshes because the API is rate-limited.",
    ):
        st.cache_data.clear()
        st.rerun()
    if matches.empty:
        st.warning("No matches are available.")
        return

    _render_live_entries(matches)

    statuses = sorted(matches["status"].dropna().unique())
    filter_key = "cupmarket_match_status_filter"
    if st.session_state.pop("cupmarket_reset_status_filter", False):
        st.session_state[filter_key] = statuses
    selected_statuses = st.multiselect(
        "Show matches", statuses, default=statuses, key=filter_key
    )
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
    elif selector_key not in st.session_state or st.session_state[selector_key] not in option_rows:
        st.session_state[selector_key] = option_ids[0]

    st.markdown("### Open a match")
    selected_match_id = st.selectbox(
        "Choose a match",
        option_ids,
        format_func=lambda match_id: match_option_label(option_rows[match_id]),
        key=selector_key,
    )
    match = option_rows[int(selected_match_id)]
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
    kickoff = match.get("utc_date")
    kickoff_text = (
        kickoff.strftime("%A, %d %B · %H:%M UTC")
        if pd.notna(kickoff)
        else "Kickoff pending"
    )
    status = str(match.get("status", ""))
    state = (
        f"LIVE · {_minute_text(match)}"
        if status in LIVE_STATUSES
        else ("FULL TIME" if status == "FINISHED" else status)
    )
    st.markdown(
        f'''
        <div class="cm-match-card">
            <div class="cm-match-meta">{state} · {kickoff_text}</div>
            <div class="cm-match-teams">
                <strong>{match.get('home_team', 'TBD')}</strong>
                <span>{score_text(match)}</span>
                <strong>{match.get('away_team', 'TBD')}</strong>
            </div>
            <div class="cm-match-meta">{match.get('group', '')} · {match.get('stage', '')}</div>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    if _render_live_room(
        matches, predictions, prices, int(selected_match_id), prediction
    ):
        return

    if prediction.empty or pd.isna(prediction.get("prob_home_win")):
        st.info("A saved probability forecast is not available for this match yet.")
        return

    confidence, top_probability, separation = prediction_confidence(prediction)
    st.markdown("#### Pre-match outcome forecast")
    outcomes = st.columns(3)
    outcomes[0].metric(
        f"{match.get('home_team')} win", format_percent(prediction.get("prob_home_win"))
    )
    outcomes[1].metric("Draw", format_percent(prediction.get("prob_draw")))
    outcomes[2].metric(
        f"{match.get('away_team')} win", format_percent(prediction.get("prob_away_win"))
    )
    details = st.columns(4)
    details[0].metric(
        "Home expected goals", format_number(prediction.get("expected_home_goals"))
    )
    details[1].metric(
        "Away expected goals", format_number(prediction.get("expected_away_goals"))
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
        "Both teams to score", format_percent(prediction.get("prob_btts_yes"))
    )
    extras[1].metric(
        "Over 2.5 goals", format_percent(prediction.get("prob_over_2_5"))
    )
    extras[2].metric("Outcome separation", format_percent(separation))

    is_future_group_match = (
        match.get("stage") == "GROUP_STAGE"
        and match.get("status") in ["TIMED", "SCHEDULED"]
    )
    if is_future_group_match:
        with st.expander("What could this match mean for qualification?"):
            team = st.selectbox(
                "Analyse qualification impact for",
                [match.get("home_team"), match.get("away_team")],
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
                        predictions,
                        team,
                        tuple(sorted(strength.items())),
                        1500,
                    )
                render_qualification_result(result, compact=True)

    st.caption(
        "This is the saved pre-match forecast. Official country prices and tournament "
        "probabilities change after completed results are processed by the model pipeline."
    )
