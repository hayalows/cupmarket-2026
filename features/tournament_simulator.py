from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from backend.live_knockout import run_live_knockout_projection


SETTLEMENT_VALUES = {
    "group_exit": 5.0,
    "round_32_exit": 15.0,
    "round_16_exit": 30.0,
    "quarter_final_exit": 50.0,
    "semi_final_exit": 70.0,
    "runner_up": 85.0,
    "champion": 100.0,
}

STAGE_CONFIG = {
    "LAST_32": ("Round of 32", "prob_reach_round_16", 15.0, 30.0),
    "ROUND_OF_32": ("Round of 32", "prob_reach_round_16", 15.0, 30.0),
    "LAST_16": ("Round of 16", "prob_reach_quarter_final", 30.0, 50.0),
    "ROUND_OF_16": ("Round of 16", "prob_reach_quarter_final", 30.0, 50.0),
    "QUARTER_FINALS": ("Quarter-final", "prob_reach_semi_final", 50.0, 70.0),
    "QUARTER_FINAL": ("Quarter-final", "prob_reach_semi_final", 50.0, 70.0),
    "SEMI_FINALS": ("Semi-final", "prob_reach_final", 70.0, 85.0),
    "SEMI_FINAL": ("Semi-final", "prob_reach_final", 70.0, 85.0),
    "FINAL": ("Final", "prob_champion", 85.0, 100.0),
}

UPCOMING_STATUSES = {"TIMED", "SCHEDULED"}
LIVE_STATUSES = {"IN_PLAY", "LIVE", "PAUSED", "SUSPENDED"}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none", "null", "tbd"} else text


def _numeric(value: Any, default: float = 0.0) -> float:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return default
    return float(number)


def _pct(value: Any) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "-"
    return f"{100 * float(number):.1f}%"


def _price(value: Any) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "-"
    return f"{float(number):.2f} CM"


def _stage_config(stage: Any) -> tuple[str, str, float, float]:
    key = _clean_text(stage).upper()
    return STAGE_CONFIG.get(key, ("Knockout", "prob_champion", 15.0, 100.0))


def _real_team(value: Any) -> bool:
    return bool(_clean_text(value))


def _knockout_fixtures(matches: pd.DataFrame) -> pd.DataFrame:
    if matches.empty or "stage" not in matches.columns:
        return pd.DataFrame()
    frame = matches.copy()
    status = frame.get("status", pd.Series(index=frame.index, dtype=str)).astype(str)
    stage = frame.get("stage", pd.Series(index=frame.index, dtype=str)).astype(str)
    mask = (
        status.isin(UPCOMING_STATUSES | LIVE_STATUSES)
        & stage.ne("GROUP_STAGE")
        & frame.get("home_team", pd.Series(index=frame.index)).map(_real_team)
        & frame.get("away_team", pd.Series(index=frame.index)).map(_real_team)
    )
    result = frame.loc[mask].copy()
    if "utc_date" in result.columns:
        result["utc_date"] = pd.to_datetime(result["utc_date"], errors="coerce", utc=True)
        result = result.sort_values("utc_date", na_position="last")
    return result.reset_index(drop=True)


def _prediction_for_match(predictions: pd.DataFrame, match_id: int) -> pd.Series:
    if predictions.empty or "match_id" not in predictions.columns:
        return pd.Series(dtype=object)
    rows = predictions.copy()
    rows["match_id"] = pd.to_numeric(rows["match_id"], errors="coerce")
    rows = rows.loc[rows["match_id"].eq(int(match_id))].copy()
    if rows.empty:
        return pd.Series(dtype=object)
    if "generated_at_utc" in rows.columns:
        rows["generated_at_utc"] = pd.to_datetime(
            rows["generated_at_utc"], errors="coerce", utc=True
        )
        rows = rows.sort_values("generated_at_utc")
    return rows.iloc[-1]


def _advance_probabilities(
    match: pd.Series,
    predictions: pd.DataFrame,
) -> tuple[float, float]:
    prediction = _prediction_for_match(predictions, int(match.get("match_id")))
    if not prediction.empty:
        home_advance = pd.to_numeric(prediction.get("prob_home_advance"), errors="coerce")
        away_advance = pd.to_numeric(prediction.get("prob_away_advance"), errors="coerce")
        if pd.notna(home_advance) and pd.notna(away_advance):
            total = float(home_advance) + float(away_advance)
            if total > 0:
                return float(home_advance) / total, float(away_advance) / total

        home_win = _numeric(prediction.get("prob_home_win"))
        away_win = _numeric(prediction.get("prob_away_win"))
        draw = _numeric(prediction.get("prob_draw"))
        total = home_win + away_win + draw
        if total > 0:
            return (home_win + 0.5 * draw) / total, (away_win + 0.5 * draw) / total
    return 0.5, 0.5


def _price_lookup(prices: pd.DataFrame) -> dict[str, pd.Series]:
    if prices.empty or "team" not in prices.columns:
        return {}
    return {
        str(row.team): pd.Series(row._asdict())
        for row in prices.itertuples(index=False)
    }


def _conditional_advance_price(
    current_price: float,
    advance_probability: float,
    loser_value: float,
    winner_floor: float,
) -> float:
    probability = max(0.0, min(1.0, float(advance_probability)))
    if probability <= 0.02:
        projected = max(current_price, winner_floor)
    else:
        projected = (current_price - (1.0 - probability) * loser_value) / probability
    return round(max(winner_floor, min(100.0, projected)), 2)


def _scenario_rows(
    prices: pd.DataFrame,
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    choices: dict[int, str],
) -> pd.DataFrame:
    lookup = _price_lookup(prices)
    projected = {
        team: _numeric(row.get("cupmarket_price"))
        for team, row in lookup.items()
    }
    notes: dict[str, str] = {}

    for match_id, winner_side in choices.items():
        match_rows = matches.loc[
            pd.to_numeric(matches.get("match_id"), errors="coerce").eq(int(match_id))
        ]
        if match_rows.empty:
            continue
        match = match_rows.iloc[-1]
        home_team = _clean_text(match.get("home_team"))
        away_team = _clean_text(match.get("away_team"))
        if not home_team or not away_team:
            continue
        stage_label, _, loser_value, winner_floor = _stage_config(match.get("stage"))
        home_probability, away_probability = _advance_probabilities(match, predictions)
        if winner_side == "HOME":
            winner, loser = home_team, away_team
            winner_probability = home_probability
        else:
            winner, loser = away_team, home_team
            winner_probability = away_probability

        winner_current = projected.get(
            winner,
            _numeric(lookup.get(winner, pd.Series(dtype=object)).get("cupmarket_price")),
        )
        winner_price = _conditional_advance_price(
            winner_current,
            winner_probability,
            loser_value,
            winner_floor,
        )
        projected[winner] = max(projected.get(winner, winner_current), winner_price)
        projected[loser] = loser_value
        notes[winner] = f"Advances from {stage_label}"
        notes[loser] = f"Out at {stage_label}"

    rows = []
    for team, row in lookup.items():
        current = _numeric(row.get("cupmarket_price"))
        scenario = projected.get(team, current)
        delta = scenario - current
        if abs(delta) < 0.005 and team not in notes:
            continue
        rows.append(
            {
                "Country": team,
                "Current": current,
                "Scenario": scenario,
                "Move": delta,
                "Note": notes.get(team, "Path affected by selected results"),
            }
        )
    result = pd.DataFrame(rows)
    if not result.empty:
        result["abs_move"] = result["Move"].abs()
        result = result.sort_values("abs_move", ascending=False).drop(columns="abs_move")
    return result.reset_index(drop=True)


def _display_scenario_table(frame: pd.DataFrame) -> None:
    if frame.empty:
        st.caption("No visible CM movement for this sandbox scenario yet.")
        return
    display = frame.copy()
    for column in ["Current", "Scenario"]:
        display[column] = display[column].map(_price)
    display["Move"] = display["Move"].map(lambda value: f"{float(value):+.2f} CM")
    st.dataframe(display, hide_index=True, use_container_width=True)


def _match_label(row: pd.Series) -> str:
    stage_label, _, _, _ = _stage_config(row.get("stage"))
    kickoff = pd.to_datetime(row.get("utc_date"), errors="coerce", utc=True)
    time_text = "" if pd.isna(kickoff) else kickoff.strftime("%d %b %H:%M UTC")
    return (
        f"{_clean_text(row.get('home_team'))} vs {_clean_text(row.get('away_team'))}"
        f" - {stage_label}"
        + (f" - {time_text}" if time_text else "")
    )


def _render_match_what_if(
    fixtures: pd.DataFrame,
    prices: pd.DataFrame,
    predictions: pd.DataFrame,
) -> None:
    st.markdown("#### One-match what-if")
    if fixtures.empty:
        st.info("No upcoming knockout fixture with two known teams is available.")
        return

    labels = {_match_label(row): int(row.match_id) for row in fixtures.itertuples(index=False)}
    selected_label = st.selectbox("Fixture", list(labels), key="sim_match_fixture")
    match_id = labels[selected_label]
    match = fixtures.loc[
        pd.to_numeric(fixtures["match_id"], errors="coerce").eq(match_id)
    ].iloc[-1]
    home_team = _clean_text(match.get("home_team"))
    away_team = _clean_text(match.get("away_team"))
    home_probability, away_probability = _advance_probabilities(match, predictions)

    columns = st.columns(2)
    columns[0].metric(f"{home_team} model advance", _pct(home_probability))
    columns[1].metric(f"{away_team} model advance", _pct(away_probability))

    outcome = st.radio(
        "Scenario result",
        [f"{home_team} advances", f"{away_team} advances", "Custom score"],
        horizontal=True,
        key="sim_match_outcome",
    )
    if outcome == "Custom score":
        score_cols = st.columns(3)
        home_score = score_cols[0].number_input(home_team, min_value=0, max_value=12, value=1, step=1)
        away_score = score_cols[1].number_input(away_team, min_value=0, max_value=12, value=0, step=1)
        if home_score == away_score:
            shootout = score_cols[2].selectbox("Advances on penalties", [home_team, away_team])
            winner_side = "HOME" if shootout == home_team else "AWAY"
        else:
            winner_side = "HOME" if home_score > away_score else "AWAY"
    else:
        winner_side = "HOME" if outcome.startswith(home_team) else "AWAY"

    scenario = _scenario_rows(prices, fixtures, predictions, {match_id: winner_side})
    _display_scenario_table(scenario)
    st.caption(
        "Sandbox output. Official CupMarket prices change only after the backend "
        "settles a real result."
    )


def _render_bracket_builder(
    fixtures: pd.DataFrame,
    prices: pd.DataFrame,
    predictions: pd.DataFrame,
) -> None:
    st.markdown("#### Bracket scenario builder")
    if fixtures.empty:
        st.info("No upcoming knockout fixtures with two known teams are available.")
        return

    st.caption("Pick winners for several known fixtures, then compare projected CM movement.")
    choices: dict[int, str] = {}
    for row in fixtures.head(8).itertuples(index=False):
        match = pd.Series(row._asdict())
        home_team = _clean_text(match.get("home_team"))
        away_team = _clean_text(match.get("away_team"))
        label = _match_label(match)
        choice = st.selectbox(
            label,
            ["No pick", home_team, away_team],
            key=f"sim_bracket_{int(match.get('match_id'))}",
        )
        if choice == home_team:
            choices[int(match.get("match_id"))] = "HOME"
        elif choice == away_team:
            choices[int(match.get("match_id"))] = "AWAY"

    if not choices:
        st.caption("Choose at least one winner to build a bracket scenario.")
        return

    scenario = _scenario_rows(prices, fixtures, predictions, choices)
    _display_scenario_table(scenario.head(16))


def _render_live_from_here(matches: pd.DataFrame, predictions: pd.DataFrame) -> None:
    st.markdown("#### Live from here")
    result = run_live_knockout_projection(
        matches,
        predictions,
        match_id=None,
        n_simulations=2200,
        random_seed=2026,
    )
    if not result.get("available"):
        st.info(str(result.get("reason") or "No live knockout projection is available."))
        fixtures = _knockout_fixtures(matches)
        if not fixtures.empty:
            st.caption(f"Next known knockout fixture: {_match_label(fixtures.iloc[0])}")
        return

    projections = result.get("matches", {})
    for projection in projections.values():
        st.markdown(
            f"**{projection['home_team']} vs {projection['away_team']}**"
            f" - {projection.get('current_score')} after about {projection.get('minute')} minutes"
        )
        columns = st.columns(3)
        columns[0].metric(
            f"{projection['home_team']} advance",
            _pct(projection.get("home_advance_probability")),
        )
        columns[1].metric(
            f"{projection['away_team']} advance",
            _pct(projection.get("away_advance_probability")),
        )
        columns[2].metric(
            "Penalty edge",
            _pct(projection.get("penalty_home_probability")),
        )

        scorelines = pd.DataFrame(projection.get("likely_final_scorelines") or [])
        if not scorelines.empty:
            scorelines["probability"] = scorelines["probability"].map(_pct)
            st.dataframe(
                scorelines.rename(
                    columns={"score": "Likely final score", "probability": "Chance"}
                ),
                hide_index=True,
                use_container_width=True,
            )
        st.caption(str(projection.get("method_note") or result.get("method_note") or ""))


def render_tournament_simulator(
    matches: pd.DataFrame,
    prices: pd.DataFrame,
    predictions: pd.DataFrame,
) -> None:
    st.markdown("### Simulator")
    st.caption(
        "Sandbox scenarios only. They help you explore what a result could mean, "
        "but they never overwrite official CupMarket prices."
    )
    fixtures = _knockout_fixtures(matches)
    match_tab, bracket_tab, live_tab = st.tabs(
        ["Match what-if", "Bracket builder", "Live from here"]
    )
    with match_tab:
        _render_match_what_if(fixtures, prices, predictions)
    with bracket_tab:
        _render_bracket_builder(fixtures, prices, predictions)
    with live_tab:
        _render_live_from_here(matches, predictions)
