from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from backend.live_knockout import (
    LIVE_STATUSES as KNOCKOUT_LIVE_STATUSES,
    is_live_knockout_match,
    next_stage_probability_column,
    run_live_knockout_projection,
)
from backend.live_qualification import (
    LIVE_STATUSES as GROUP_LIVE_STATUSES,
    build_provisional_snapshot,
    next_goal_impacts,
)
from features.live_qualification_ui import cached_projection, pct
from features.match_ui import (
    clean_text,
    format_number,
    match_stage_label,
    match_option_label,
    prediction_confidence,
    score_text,
)
from features.qualification_ui import (
    cached_qualification_scenarios,
    format_percent,
    render_qualification_result,
)
from features.tournament_path_data import KNOCKOUT_PROGRESS_PATH


LIVE_STATUSES = GROUP_LIVE_STATUSES | KNOCKOUT_LIVE_STATUSES
NEXT_ROUND_SOURCES = {
    89: (74, 77),
    90: (73, 75),
    91: (76, 78),
    92: (79, 80),
    93: (83, 84),
    94: (81, 82),
    95: (86, 88),
    96: (85, 87),
    97: (89, 90),
    98: (93, 94),
    99: (91, 92),
    100: (95, 96),
    101: (97, 98),
    102: (99, 100),
    104: (101, 102),
}
DESTINATION_LABELS = {
    "LAST_32": "Round of 16",
    "ROUND_OF_32": "Round of 16",
    "R32": "Round of 16",
    "LAST_16": "Quarter-final",
    "ROUND_OF_16": "Quarter-final",
    "R16": "Quarter-final",
    "QUARTER_FINALS": "Semi-final",
    "QUARTER_FINAL": "Semi-final",
    "QF": "Semi-final",
    "SEMI_FINALS": "Final",
    "SEMI_FINAL": "Final",
    "SF": "Final",
    "FINAL": "Champion",
}


@st.cache_data(ttl=60, show_spinner=False)
def cached_knockout_projection(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    match_id: int,
    simulations: int = 3000,
) -> dict[str, Any]:
    return run_live_knockout_projection(
        matches,
        predictions,
        match_id=int(match_id),
        n_simulations=simulations,
        random_seed=2026,
    )


@st.cache_data(ttl=60, show_spinner=False)
def cached_knockout_progress() -> pd.DataFrame:
    try:
        return pd.read_csv(KNOCKOUT_PROGRESS_PATH)
    except (OSError, pd.errors.ParserError):
        return pd.DataFrame()


def _minute_text(row: pd.Series) -> str:
    if str(row.get("status", "")) == "PAUSED":
        return "HT"
    minute = row.get("minute")
    return f"{int(minute)}'" if minute is not None and pd.notna(minute) else "LIVE"


def _live_meta_text(row: pd.Series) -> str:
    minute = _minute_text(row)
    parts = ["LIVE"]
    if minute != "LIVE":
        parts.append(minute)
    context = match_stage_label(row)
    if context:
        parts.append(context)
    return " \u00b7 ".join(parts)


def _pp_delta(current, baseline) -> str | None:
    if current is None or baseline is None or pd.isna(current) or pd.isna(baseline):
        return None
    return f"{100 * (float(current) - float(baseline)):+.1f} pp vs published model"


def _current_score_caption(live: dict[str, Any]) -> str:
    score = live.get("current_score", "0-0")
    minute = pd.to_numeric(live.get("minute"), errors="coerce")
    source = str(live.get("minute_source") or "").lower()
    if source == "unavailable" or pd.isna(minute) or (not source and minute <= 0):
        return f"Current score: {score}. Match minute unavailable from feed."
    minute_text = int(minute)
    if source == "api":
        return f"Current score: {score} after {minute_text} minutes."
    return f"Current score: {score} after about {minute_text} minutes."


def _progress_rows_by_number(progress: pd.DataFrame) -> dict[int, pd.Series]:
    if progress.empty or "logical_match_number" not in progress.columns:
        return {}
    rows = {}
    for _, row in progress.iterrows():
        number = pd.to_numeric(row.get("logical_match_number"), errors="coerce")
        if pd.notna(number):
            rows[int(number)] = row
    return rows


def _clean_team(value) -> str:
    return clean_text(value)


def _source_winner_label(rows: dict[int, pd.Series], source_number: int) -> dict[str, Any]:
    source = rows.get(source_number)
    if source is None:
        return {
            "label": "",
            "locked": False,
            "note": "Next opponent not locked yet. CupMarket will update after the connected fixture is decided.",
        }
    advancing = _clean_team(source.get("advancing_team"))
    if advancing:
        return {"label": advancing, "locked": True, "note": ""}
    home = _clean_team(source.get("home_team"))
    away = _clean_team(source.get("away_team"))
    if home and away:
        return {
            "label": f"{home}/{away} winner",
            "locked": False,
            "note": "Opponent comes from the connected fixture and locks after that result.",
        }
    return {
        "label": "",
        "locked": False,
        "note": "Next opponent not locked yet. CupMarket will update after the connected fixture is decided.",
    }


def _advance_consequence(match: pd.Series, progress: pd.DataFrame) -> dict[str, Any]:
    stage = clean_text(match.get("stage")).upper()
    destination = DESTINATION_LABELS.get(stage, "next round")
    if destination == "Champion":
        return {
            "destination": destination,
            "target_match": None,
            "opponent_label": "",
            "opponent_locked": True,
            "note": "",
        }

    if progress.empty or "api_match_id" not in progress.columns:
        return {
            "destination": destination,
            "target_match": None,
            "opponent_label": "",
            "opponent_locked": False,
            "note": "Next opponent not locked yet. CupMarket will update after the connected fixture is decided.",
        }

    match_id = pd.to_numeric(match.get("match_id"), errors="coerce")
    if pd.isna(match_id):
        return {
            "destination": destination,
            "target_match": None,
            "opponent_label": "",
            "opponent_locked": False,
            "note": "Next opponent not locked yet. CupMarket will update after the connected fixture is decided.",
        }

    working = progress.copy()
    working["api_match_id"] = pd.to_numeric(
        working["api_match_id"], errors="coerce"
    )
    current_rows = working.loc[working["api_match_id"] == int(match_id)]
    if current_rows.empty:
        return {
            "destination": destination,
            "target_match": None,
            "opponent_label": "",
            "opponent_locked": False,
            "note": "Next opponent not locked yet. CupMarket will update after the connected fixture is decided.",
        }

    source_number = pd.to_numeric(
        current_rows.iloc[0].get("logical_match_number"),
        errors="coerce",
    )
    if pd.isna(source_number):
        return {
            "destination": destination,
            "target_match": None,
            "opponent_label": "",
            "opponent_locked": False,
            "note": "Next opponent not locked yet. CupMarket will update after the connected fixture is decided.",
        }

    source_number = int(source_number)
    for target_match, (left_source, right_source) in NEXT_ROUND_SOURCES.items():
        if source_number not in {left_source, right_source}:
            continue
        opponent_source = right_source if source_number == left_source else left_source
        opponent = _source_winner_label(
            _progress_rows_by_number(progress),
            opponent_source,
        )
        return {
            "destination": destination,
            "target_match": target_match,
            "opponent_label": opponent["label"],
            "opponent_locked": opponent["locked"],
            "note": opponent["note"],
        }

    return {
        "destination": destination,
        "target_match": None,
        "opponent_label": "",
        "opponent_locked": False,
        "note": "Next opponent not locked yet. CupMarket will update after the connected fixture is decided.",
    }


def _render_clock_debug(live: dict[str, Any]) -> None:
    source = str(live.get("minute_source") or "unavailable")
    if source == "api":
        return
    with st.expander("Live feed clock details", expanded=False):
        rows = pd.DataFrame(
            [
                {
                    "Minute source": source,
                    "Provider status": live.get("raw_status", ""),
                    "Kickoff UTC": live.get("kickoff_utc") or "Unavailable",
                }
            ]
        )
        st.dataframe(rows, width="stretch", hide_index=True)


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
    st.dataframe(frame, width="stretch", hide_index=True)


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
                    <div class="cm-match-meta">&bull; {_live_meta_text(series)}</div>
                    <div class="cm-match-teams">
                        <strong>{series.get('home_team', 'TBD')}</strong>
                        <span>{score_text(series)}</span>
                        <strong>{series.get('away_team', 'TBD')}</strong>
                    </div>
                </div>
                ''',
                unsafe_allow_html=True,
            )


def _is_group_stage_match(row: pd.Series) -> bool:
    return str(row.get("stage", "")).upper() == "GROUP_STAGE"


def _build_group_context(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    prices: pd.DataFrame,
    match_id: int,
) -> dict[str, Any] | None:
    rows = matches[matches["match_id"] == int(match_id)]
    if rows.empty or rows.iloc[0].get("status") not in GROUP_LIVE_STATUSES:
        return None
    match = rows.iloc[0]
    if not _is_group_stage_match(match):
        return None
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


def _method_probability_rows(live: dict[str, Any]) -> pd.DataFrame:
    labels = {
        "normal_time": "Normal time",
        "extra_time": "Extra time",
        "penalties": "Penalties",
    }
    rows = [
        {
            "Decision path": label,
            "Probability": pct(live.get("method_probabilities", {}).get(key)),
        }
        for key, label in labels.items()
    ]
    return pd.DataFrame(rows)


def _price_column_label(column: str | None) -> str:
    labels = {
        "prob_reach_round_16": "Published chance to reach Round of 16",
        "prob_reach_quarter_final": "Published chance to reach quarter-final",
        "prob_reach_semi_final": "Published chance to reach semi-final",
        "prob_reach_final": "Published chance to reach final",
        "prob_champion": "Published chance to win the tournament",
    }
    return labels.get(column or "", "Published next-stage chance")


def _render_knockout_consequence_view(
    match: pd.Series,
    prices: pd.DataFrame,
    home_team: str,
    away_team: str,
) -> None:
    progress = cached_knockout_progress()
    consequence = _advance_consequence(match, progress)
    destination = consequence["destination"]
    price_column = next_stage_probability_column(match.get("stage"))
    label = _price_column_label(price_column)

    st.markdown("#### What advancing unlocks next")
    columns = st.columns(2)
    for column, team in zip(columns, [home_team, away_team]):
        row = _market_row(prices, team)
        published_probability = (
            row.get(price_column)
            if price_column and not row.empty and price_column in row.index
            else None
        )
        champion_probability = row.get("prob_champion") if not row.empty else None
        opponent = consequence.get("opponent_label")
        if destination == "Champion":
            next_line = f"If {team} advance, they become champion."
        elif opponent:
            next_line = f"If {team} advance, they enter the {destination} against {opponent}."
        else:
            next_line = (
                f"If {team} advance, their {destination} opponent is not locked yet."
            )
        with column:
            st.markdown(f"##### {team}")
            st.write(next_line)
            if consequence.get("target_match"):
                st.caption(f"Connected bracket slot: match {consequence['target_match']}.")
            if consequence.get("note"):
                st.caption(consequence["note"])
            st.metric(label, pct(published_probability))
            st.metric("Published champion chance", pct(champion_probability))


def _render_knockout_live_room(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    prices: pd.DataFrame,
    match_id: int,
    prediction_row: pd.Series,
) -> bool:
    rows = matches[matches["match_id"] == int(match_id)]
    if rows.empty:
        return False
    match = rows.iloc[0]
    result = cached_knockout_projection(matches, predictions, int(match_id), 3200)
    if not result.get("available"):
        st.info(
            "This knockout match is live, but CupMarket cannot build an in-play "
            "advance projection until a saved pre-match knockout forecast is available."
        )
        return True

    live = result.get("matches", {}).get(int(match_id))
    if not live:
        st.info("A live knockout projection is not available for this fixture yet.")
        return True

    home_team = str(match.get("home_team"))
    away_team = str(match.get("away_team"))
    st.info(
        "Knockout Live Room is active. Scores and in-play advance chances can change "
        "when the feed refreshes. Official country prices still update only after the "
        "result is final and the model pipeline publishes."
    )
    outlook_tab, advance_tab, market_tab, model_tab = st.tabs(
        [
            "Live outlook",
            "Advance picture",
            "Market context",
            "Pre-match model",
        ]
    )

    with outlook_tab:
        st.markdown("#### Who is most likely to advance from here?")
        st.caption(_current_score_caption(live))
        columns = st.columns(2)
        columns[0].metric(
            f"{home_team} chance to advance",
            pct(live.get("home_advance_probability")),
            delta=_pp_delta(
                live.get("home_advance_probability"),
                live.get("prematch_home_advance_probability"),
            ),
        )
        columns[1].metric(
            f"{away_team} chance to advance",
            pct(live.get("away_advance_probability")),
            delta=_pp_delta(
                live.get("away_advance_probability"),
                live.get("prematch_away_advance_probability"),
            ),
        )

        scorelines = pd.DataFrame(live.get("likely_final_scorelines", []))
        if not scorelines.empty:
            scorelines["probability"] = scorelines["probability"].map(pct)
            st.markdown("##### Most likely final scorelines")
            st.dataframe(
                scorelines.rename(
                    columns={"score": "Final score", "probability": "Probability"}
                ),
                width="stretch",
                hide_index=True,
            )
        st.caption(live["method_note"] + " These are estimates, not guarantees.")
        _render_clock_debug(live)

    with advance_tab:
        _render_knockout_consequence_view(
            match,
            prices,
            home_team,
            away_team,
        )
        st.markdown("#### How the match is likely to be decided")
        st.caption(
            "The decision path starts from the current score and the match clock, "
            "then follows normal time, extra time and penalties if needed."
        )
        method_rows = _method_probability_rows(live)
        st.dataframe(method_rows, width="stretch", hide_index=True)
        st.metric(
            f"{home_team} penalty edge",
            pct(live.get("penalty_home_probability")),
            delta=f"{away_team} {pct(1 - float(live.get('penalty_home_probability', 0.5)))}",
            delta_color="off",
        )
        st.caption(
            "Penalty estimates are deliberately bounded, so Elo can tilt the shootout "
            "without pretending penalties are highly predictable."
        )

    with market_tab:
        st.markdown("#### What this could mean for the country market")
        st.warning(
            "These are not live trading prices. CupMarket publishes new official "
            "prices only after the knockout result is processed."
        )
        price_column = next_stage_probability_column(match.get("stage"))
        label = _price_column_label(price_column)
        market_columns = st.columns(2)
        for column, team, live_probability in zip(
            market_columns,
            [home_team, away_team],
            [
                live.get("home_advance_probability"),
                live.get("away_advance_probability"),
            ],
        ):
            row = _market_row(prices, team)
            published_probability = (
                row.get(price_column)
                if price_column and not row.empty and price_column in row.index
                else None
            )
            pressure = _pressure_label(live_probability, published_probability)
            with column:
                st.markdown(f"##### {team}")
                st.metric(
                    "Published CupMarket price",
                    f"{float(row.get('cupmarket_price')):.2f} CM"
                    if not row.empty and pd.notna(row.get("cupmarket_price"))
                    else "—",
                )
                st.metric(label, pct(published_probability))
                st.metric(
                    "Live chance to advance",
                    pct(live_probability),
                    delta=_pp_delta(live_probability, published_probability),
                )
                if pressure == "Likely upward pressure":
                    st.success(pressure)
                elif pressure == "Likely downward pressure":
                    st.error(pressure)
                else:
                    st.info(pressure)
        st.caption(
            "The direction compares the live chance to advance with the last "
            "published next-stage probability. Final price movement can differ because "
            "the full bracket, Elo and future paths are recalculated together."
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
            advance = st.columns(2)
            advance[0].metric(
                f"{home_team} pre-match chance to advance",
                pct(prediction_row.get("prob_home_advance")),
            )
            advance[1].metric(
                f"{away_team} pre-match chance to advance",
                pct(prediction_row.get("prob_away_advance")),
            )
            outcomes = st.columns(3)
            outcomes[0].metric(
                f"{home_team} 90-minute win",
                format_percent(prediction_row.get("prob_home_win")),
            )
            outcomes[1].metric(
                "90-minute draw",
                format_percent(prediction_row.get("prob_draw")),
            )
            outcomes[2].metric(
                f"{away_team} 90-minute win",
                format_percent(prediction_row.get("prob_away_win")),
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


def _render_live_room(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    prices: pd.DataFrame,
    match_id: int,
    prediction_row: pd.Series,
) -> bool:
    rows = matches[matches["match_id"] == int(match_id)]
    if rows.empty or str(rows.iloc[0].get("status", "")).upper() not in LIVE_STATUSES:
        return False

    match = rows.iloc[0]
    if is_live_knockout_match(match):
        return _render_knockout_live_room(
            matches,
            predictions,
            prices,
            match_id,
            prediction_row,
        )

    context = _build_group_context(matches, predictions, prices, match_id)
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
        st.caption(_current_score_caption(live))
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
                width="stretch",
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
            st.dataframe(impact_frame, width="stretch", hide_index=True)

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
    knockout_live_count = int(live_matches.apply(is_live_knockout_match, axis=1).sum())
    group_live_count = int(
        (
            live_matches["stage"].astype(str).str.upper() == "GROUP_STAGE"
        ).sum()
    )
    if knockout_live_count and not group_live_count:
        caption = (
            "Open a match to move from the score into live outlook, chance to "
            "advance and market context."
        )
    elif knockout_live_count and group_live_count:
        caption = (
            "Open a match to move from the score into the right live room: "
            "advancement for knockouts, group pressure for group matches."
        )
    else:
        caption = (
            "Open a match to move from the score into live outlook, qualification, "
            "group effects and market context."
        )
    st.caption(caption)
    columns = st.columns(min(3, len(live_matches)))
    for index, row in enumerate(live_matches.itertuples(index=False)):
        series = pd.Series(row._asdict())
        action_text = (
            "Open for outlook, chance to advance and market context."
            if is_live_knockout_match(series)
            else "Open for outlook, qualification, group and market context."
        )
        with columns[index % len(columns)]:
            st.markdown(
                f'''
                <div class="cm-match-card">
                    <div class="cm-match-meta">● {_live_meta_text(series)}</div>
                    <div class="cm-match-teams">
                        <strong>{series.get('home_team', 'TBD')}</strong>
                        <span>{score_text(series)}</span>
                        <strong>{series.get('away_team', 'TBD')}</strong>
                    </div>
                    <div class="cm-match-meta">{action_text}</div>
                </div>
                ''',
                unsafe_allow_html=True,
            )
            if st.button(
                "Open live match room",
                key=f"open_live_match_{int(series['match_id'])}",
                width="stretch",
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
    elif filter_key not in st.session_state:
        st.session_state[filter_key] = statuses
    selected_statuses = st.multiselect(
        "Show matches", statuses, key=filter_key
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
        _live_meta_text(match)
        if status in LIVE_STATUSES
        else ("FULL TIME" if status == "FINISHED" else status)
    )
    context = match_stage_label(match)
    context_line = (
        f'<div class="cm-match-meta">{context}</div>' if context else ""
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
            {context_line}
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
