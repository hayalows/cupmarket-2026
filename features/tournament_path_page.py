from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from features.product_ui import render_official_data_caption
from features.market_explanation import render_market_explanation
from features.tournament_path_data import (
    available_teams,
    load_tournament_path_data,
    preferred_team,
    stage_label,
    status_label,
    team_next_knockout_slot,
    team_summary,
    tournament_summary,
)


STAGE_ORDER = {
    "LAST_32": 1,
    "ROUND_OF_32": 1,
    "R32": 1,
    "LAST_16": 2,
    "ROUND_OF_16": 2,
    "R16": 2,
    "QUARTER_FINALS": 3,
    "QUARTER_FINAL": 3,
    "QF": 3,
    "SEMI_FINALS": 4,
    "SEMI_FINAL": 4,
    "SF": 4,
    "THIRD_PLACE": 5,
    "FINAL": 6,
}


NEXT_STAGE_LABELS = {
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

NEXT_STAGE_PROBABILITY_COLUMNS = {
    "LAST_32": ("Reach Round of 16", "prob_reach_round_16"),
    "ROUND_OF_32": ("Reach Round of 16", "prob_reach_round_16"),
    "R32": ("Reach Round of 16", "prob_reach_round_16"),
    "LAST_16": ("Reach Quarter-final", "prob_reach_quarter_final"),
    "ROUND_OF_16": ("Reach Quarter-final", "prob_reach_quarter_final"),
    "R16": ("Reach Quarter-final", "prob_reach_quarter_final"),
    "QUARTER_FINALS": ("Reach Semi-final", "prob_reach_semi_final"),
    "QUARTER_FINAL": ("Reach Semi-final", "prob_reach_semi_final"),
    "QF": ("Reach Semi-final", "prob_reach_semi_final"),
    "SEMI_FINALS": ("Reach Final", "prob_reach_final"),
    "SEMI_FINAL": ("Reach Final", "prob_reach_final"),
    "SF": ("Reach Final", "prob_reach_final"),
    "FINAL": ("Become champion", "prob_champion"),
}


PREDICTION_EXPLAINER = (
    "Future knockout fixtures can be missing match-level predictions when one or both teams "
    "are still placeholders. The model needs real teams to calculate expected goals, win "
    "probabilities and likely scores. Until then, CupMarket shows path probabilities, likely "
    "opponents and stage chances instead of pretending the fixture is known."
)


def _number(value, digits: int = 2, suffix: str = "") -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "—"
    return f"{float(number):.{digits}f}{suffix}"


def _percent(value, digits: int = 1) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "—"
    return f"{100 * float(number):.{digits}f}%"


def _timestamp(value) -> str:
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(timestamp):
        return "Time pending"
    return timestamp.strftime("%d %b %Y · %H:%M UTC")


def _score(row: pd.Series) -> str:
    home = pd.to_numeric(row.get("home_score"), errors="coerce")
    away = pd.to_numeric(row.get("away_score"), errors="coerce")
    if pd.isna(home) or pd.isna(away):
        return "vs"
    score = f"{int(home)}–{int(away)}"
    home_penalties = pd.to_numeric(row.get("home_penalties"), errors="coerce")
    away_penalties = pd.to_numeric(row.get("away_penalties"), errors="coerce")
    if pd.notna(home_penalties) and pd.notna(away_penalties):
        score += f" · pens {int(home_penalties)}–{int(away_penalties)}"
    return score


def _clean_team(value) -> str:
    try:
        if pd.isna(value):
            return "TBD"
    except (TypeError, ValueError):
        pass
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "null", "tbd"}:
        return "TBD"
    return text


def _stage_sort_key(value) -> tuple[int, str]:
    text = str(value or "")
    return STAGE_ORDER.get(text, 99), stage_label(text)


def _fixture_readiness(row: pd.Series) -> str:
    home = _clean_team(row.get("home_team"))
    away = _clean_team(row.get("away_team"))
    status = str(row.get("status") or "").upper()
    if status == "FINISHED":
        return "Result fixed"
    if home != "TBD" and away != "TBD":
        return "Prediction ready when model publishes"
    if home != "TBD" or away != "TBD":
        return "One side confirmed"
    return "Waiting for teams"


def _latest_finished_fixture(fixtures: pd.DataFrame) -> pd.Series:
    if fixtures.empty or "status" not in fixtures.columns:
        return pd.Series(dtype=object)
    rows = fixtures.loc[
        fixtures["status"].astype(str).str.upper().isin({"FINISHED", "AWARDED"})
    ].copy()
    if rows.empty:
        return pd.Series(dtype=object)
    if "utc_date" in rows.columns:
        rows["utc_date"] = pd.to_datetime(rows["utc_date"], errors="coerce", utc=True)
        rows = rows.sort_values("utc_date", ascending=False, na_position="last")
    return rows.iloc[0]


def _advancing_team(fixture: pd.Series) -> str:
    advancing = _clean_team(fixture.get("advancing_team"))
    if advancing != "TBD":
        return advancing
    home = _clean_team(fixture.get("home_team"))
    away = _clean_team(fixture.get("away_team"))
    winner = str(fixture.get("winner", "") or "").upper()
    if winner == "HOME_TEAM":
        return home
    if winner == "AWAY_TEAM":
        return away
    home_score = pd.to_numeric(
        fixture.get("home_score", fixture.get("home_score_full_time")),
        errors="coerce",
    )
    away_score = pd.to_numeric(
        fixture.get("away_score", fixture.get("away_score_full_time")),
        errors="coerce",
    )
    if pd.notna(home_score) and pd.notna(away_score):
        if home_score > away_score:
            return home
        if away_score > home_score:
            return away
    return ""


def _team_result_state(fixture: pd.Series, team: str) -> dict[str, str]:
    if fixture.empty:
        return {}
    home = _clean_team(fixture.get("home_team"))
    away = _clean_team(fixture.get("away_team"))
    opponent = away if home == team else home
    advancing = _advancing_team(fixture)
    stage = str(fixture.get("stage") or "")
    score = _score(fixture)
    result = f"{home} {score} {away}"
    if advancing == team:
        next_stage = NEXT_STAGE_LABELS.get(stage, "next round")
        status = "Champion" if next_stage == "Champion" else f"Advanced to {next_stage}"
        message = f"Result fixed: **{team} advanced** after {result}."
        outcome = "Advanced"
    else:
        status = f"Eliminated in {stage_label(stage)}"
        message = f"Result fixed: **{team} is out** after {result}."
        outcome = "Eliminated"
    return {
        "status": status,
        "message": message,
        "outcome": outcome,
        "opponent": opponent,
        "result": result,
        "stage": stage,
    }


def _reach_metric_for_state(
    price: pd.Series,
    path: pd.Series,
    fixture: pd.Series,
) -> tuple[str, object]:
    if not fixture.empty:
        stage = str(fixture.get("stage") or "")
        label, column = NEXT_STAGE_PROBABILITY_COLUMNS.get(
            stage,
            ("Reach Round of 16", "prob_reach_round_16"),
        )
        return label, price.get(column)
    return (
        "Reach Round of 32",
        path.get("prob_reach_round_32")
        if not path.empty
        else price.get("prob_reach_round_32"),
    )


def _team_fixture_table(fixtures: pd.DataFrame, team: str) -> pd.DataFrame:
    if fixtures.empty:
        return fixtures
    rows = []
    for row in fixtures.itertuples(index=False):
        values = row._asdict()
        home = _clean_team(values.get("home_team"))
        away = _clean_team(values.get("away_team"))
        opponent = away if home == team else home
        series = pd.Series(values)
        advancing = _clean_team(values.get("advancing_team"))
        status = str(values.get("status", "") or "").upper()
        outcome = "Pending"
        if status in {"FINISHED", "AWARDED"} and advancing != "TBD":
            outcome = "Advanced" if str(advancing) == team else "Eliminated"
        decision = values.get("decision_method")
        decision_text = "—" if pd.isna(decision) else str(decision).replace("_", " ").title()
        rows.append(
            {
                "Stage": stage_label(values.get("stage")),
                "Outcome": outcome,
                "Fixture": f"{home} {_score(series)} {away}",
                "Kickoff · UTC": _timestamp(values.get("utc_date")),
                "Opponent": opponent,
                "Status": str(values.get("status", "Pending")).replace("_", " ").title(),
                "Score": _score(series),
                "Decision": decision_text,
                "Team outcome": outcome,
            }
        )
    table = pd.DataFrame(rows)
    first_columns = ["Stage", "Outcome", "Fixture", "Opponent"]
    ordered_columns = first_columns + [
        column for column in table.columns if column not in first_columns
    ]
    return table[ordered_columns]


def _render_next_knockout_slot(progress: pd.DataFrame, team: str) -> None:
    slot = team_next_knockout_slot(progress, team)
    if slot.empty:
        return
    kickoff = pd.to_datetime(slot.get("kickoff_utc"), errors="coerce", utc=True)
    kickoff_text = "Time pending" if pd.isna(kickoff) else kickoff.strftime("%d %b %Y - %H:%M UTC")
    stage = str(slot.get("stage_label") or "Knockout match")
    fixture = str(slot.get("fixture") or f"{team} vs opponent pending")
    match_number = slot.get("match_number")
    match_text = f"match {int(match_number)}" if pd.notna(match_number) else "fixture"

    st.markdown("### Next knockout match")
    st.success(f"**{team}'s next {stage.lower()} {match_text}:** {fixture}.")
    columns = st.columns(3)
    columns[0].metric("Stage", stage)
    columns[1].metric("State", slot.get("state", "Pending"))
    columns[2].metric("Kickoff", kickoff_text)

def _render_path_message(
    path: pd.Series,
    opponents: pd.DataFrame,
    fixture_result: pd.Series,
    team: str,
) -> None:
    result_state = _team_result_state(fixture_result, team)
    if result_state:
        if result_state["outcome"] == "Advanced":
            st.success(result_state["message"])
        else:
            st.error(result_state["message"])
        st.caption(
            "This is based on the completed knockout fixture, so projected opponent "
            "tables are hidden for this completed round."
        )
        return

    if path.empty:
        st.info(
            "A projected opponent path has not been published yet. The current price and "
            "tournament probabilities remain available below."
        )
        return

    fixture_status = str(path.get("fixture_status", "projected"))
    label = status_label(fixture_status)
    opponent = path.get("most_likely_opponent")
    slot = path.get("confirmed_slot")

    if fixture_status == "eliminated":
        st.error("This country has been eliminated from the tournament.")
    elif fixture_status == "confirmed" and pd.notna(opponent):
        st.success(f"Official fixture confirmed: **{path.get('team')} vs {opponent}**.")
    elif fixture_status == "slot_confirmed_opponent_pending":
        st.info(
            f"**{label}.** {slot or 'The knockout slot'} is fixed, but the official "
            "third-place opponent is still pending."
        )
    elif fixture_status == "slot_confirmed":
        st.info(
            f"**{label}.** {slot or 'The knockout slot'} is fixed. The other side of "
            "the fixture is still being decided."
        )
    elif fixture_status == "third_place_ranking_pending":
        st.info(
            "The country finished third and is waiting for the cross-group third-place "
            "ranking and official allocation."
        )
    else:
        st.info(
            "This path is still projected. It will become more certain as the remaining "
            "group matches finish."
        )

    if opponents.empty:
        return
    probability_column = (
        "probability_given_qualification"
        if "probability_given_qualification" in opponents.columns
        else "probability_unconditional"
    )
    display_columns = ["opponent", "opponent_group", probability_column]
    display = opponents[[column for column in display_columns if column in opponents.columns]].copy()
    display = display.rename(
        columns={
            "opponent": "Possible opponent",
            "opponent_group": "Group",
            probability_column: "Chance if qualified",
        }
    )
    if "Chance if qualified" in display.columns:
        display["Chance if qualified"] = display["Chance if qualified"].map(_percent)
    st.markdown("#### Likely Round-of-32 opponents")
    st.dataframe(display, hide_index=True, use_container_width=True)
    st.caption(
        "Conditional probability answers: if this country qualifies, how often does each "
        "opponent appear in its Round-of-32 fixture?"
    )


def _render_stage_probability_ladder(price: pd.Series, team: str) -> None:
    if price.empty:
        return
    stage_columns = [
        ("Round of 32", "prob_reach_round_32"),
        ("Round of 16", "prob_reach_round_16"),
        ("Quarter-final", "prob_reach_quarter_final"),
        ("Semi-final", "prob_reach_semi_final"),
        ("Final", "prob_reach_final"),
        ("Champion", "prob_champion"),
    ]
    rows = []
    for label, column in stage_columns:
        if column in price.index:
            rows.append({"Stage": label, "Probability": pd.to_numeric(price.get(column), errors="coerce")})
    ladder = pd.DataFrame(rows).dropna(subset=["Probability"])
    if ladder.empty:
        return
    figure = px.bar(
        ladder,
        x="Stage",
        y="Probability",
        title=f"{team}: full tournament path forecast",
    )
    figure.update_yaxes(tickformat=".0%", title=None, gridcolor="#edf0f5")
    figure.update_xaxes(title=None)
    figure.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#ffffff",
        margin=dict(l=16, r=16, t=52, b=16),
        height=360,
    )
    st.plotly_chart(figure, use_container_width=True)


def _render_market_reaction(
    movement: pd.Series,
    history: pd.DataFrame,
    team: str,
    price: pd.Series | None = None,
    latest_movement: pd.Series | None = None,
) -> None:
    st.markdown("### Market reaction")
    if movement.empty:
        st.info(
            "A direct country market reaction will appear after this country has a completed result or a model refresh changes its price."
        )
    else:
        movement_type = str(movement.get("movement_type") or "match_event")
        is_match_event = movement_type == "match_event"
        trigger = str(movement.get("trigger_matches") or "")
        model_version = str(movement.get("model_version") or "")
        is_settlement = (
            not is_match_event
            and (
                "knockout" in trigger.lower()
                or "knockout" in model_version.lower()
            )
        )
        current_price = pd.to_numeric(
            price.get("cupmarket_price") if isinstance(price, pd.Series) else None,
            errors="coerce",
        )
        after_price = pd.to_numeric(movement.get("price_after"), errors="coerce")
        before_label = (
            "Before result"
            if is_match_event
            else "Before settlement"
            if is_settlement
            else "Before refresh"
        )
        after_label = (
            "After result"
            if is_match_event
            else "After settlement"
            if is_settlement
            else "After refresh"
        )
        move_label = (
            "Result move"
            if is_match_event
            else "Settlement move"
            if is_settlement
            else "Refresh move"
        )
        columns = st.columns(4)
        columns[0].metric(
            before_label,
            _number(movement.get("price_before"), suffix=" CM"),
        )
        columns[1].metric(
            after_label,
            _number(movement.get("price_after"), suffix=" CM"),
        )
        change = pd.to_numeric(movement.get("price_change"), errors="coerce")
        percent = pd.to_numeric(movement.get("price_change_percent"), errors="coerce")
        delta = "—" if pd.isna(change) else f"{float(change):+.2f} CM"
        if pd.notna(percent):
            delta += f" · {float(percent):+.2f}%"
        columns[2].metric(move_label, delta)
        columns[3].metric(
            "Current price now",
            f"{float(current_price):.2f} CM" if pd.notna(current_price) else "—",
        )
        settlement_value = pd.to_numeric(
            price.get("adjusted_settlement_value")
            if isinstance(price, pd.Series)
            else None,
            errors="coerce",
        )
        settlement_floor = pd.to_numeric(
            price.get("exit_stage_floor") if isinstance(price, pd.Series) else None,
            errors="coerce",
        )
        settlement_premium = pd.to_numeric(
            price.get("performance_premium") if isinstance(price, pd.Series) else None,
            errors="coerce",
        )
        settlement_reason = (
            str(price.get("settlement_reason") or "")
            if isinstance(price, pd.Series)
            else ""
        )
        if pd.notna(settlement_value):
            if pd.notna(settlement_floor) and pd.notna(settlement_premium):
                st.caption(
                    "Settlement value: "
                    f"{float(settlement_value):.2f} CM "
                    f"(floor {float(settlement_floor):.2f} "
                    f"+ performance premium {float(settlement_premium):.2f})."
                )
            else:
                st.caption(f"Settlement value: {float(settlement_value):.2f} CM.")
            if settlement_reason:
                with st.expander("Why this settlement value?", expanded=False):
                    st.write(settlement_reason)
        if pd.notna(current_price) and pd.notna(after_price):
            since_event = float(current_price) - float(after_price)
            if abs(since_event) > 0.005:
                st.info(
                    f"{team}'s current price is {since_event:+.2f} CM from the "
                    f"{'result' if is_match_event else 'settlement' if is_settlement else 'refresh'} price shown here. "
                    "That gap comes from later official model publications."
                )
        if trigger:
            st.caption(f"{'Trigger' if is_match_event else 'Publication'}: {trigger}")
        snapshot_time = movement.get("snapshot_id")
        if snapshot_time:
            st.caption(f"Movement snapshot: {_timestamp(snapshot_time)}.")
        source = str(movement.get("before_source") or "").replace("_", " ")
        if source:
            st.caption(f"Before value source: {source}.")
        if (
            isinstance(latest_movement, pd.Series)
            and not latest_movement.empty
            and str(latest_movement.get("snapshot_id")) != str(movement.get("snapshot_id"))
        ):
            latest_type = str(latest_movement.get("movement_type") or "").replace("_", " ")
            st.caption(
                "Latest official price movement: "
                f"{_number(latest_movement.get('price_before'), suffix=' CM')} -> "
                f"{_number(latest_movement.get('price_after'), suffix=' CM')} "
                f"({_number(latest_movement.get('price_change'), suffix=' CM')})"
                f" from {latest_type or 'model refresh'}."
            )
        st.caption(
            "Use current price for where the market stands now. Older matches can still "
            "move a country later when other results change its projected path."
        )

    if history.empty or "team" not in history.columns:
        return
    team_history = history.loc[history["team"].astype(str) == team].copy()
    if len(team_history) < 2:
        return
    team_history["generated_at_utc"] = pd.to_datetime(
        team_history["generated_at_utc"], errors="coerce", utc=True
    )
    team_history["cupmarket_price"] = pd.to_numeric(
        team_history["cupmarket_price"], errors="coerce"
    )
    team_history = team_history.dropna(
        subset=["generated_at_utc", "cupmarket_price"]
    ).sort_values("generated_at_utc")
    if len(team_history) < 2:
        return
    figure = px.line(
        team_history,
        x="generated_at_utc",
        y="cupmarket_price",
        markers=True,
        title=f"{team} official CupMarket price history",
    )
    figure.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#ffffff",
        margin=dict(l=16, r=16, t=52, b=16),
        height=360,
    )
    figure.update_xaxes(title=None, gridcolor="#edf0f5")
    figure.update_yaxes(title="CupMarket price", gridcolor="#edf0f5")
    st.plotly_chart(figure, use_container_width=True)


def _render_fixture_cards(filtered: pd.DataFrame) -> None:
    if filtered.empty:
        st.info("No fixtures are available for this stage yet.")
        return

    for start in range(0, len(filtered), 2):
        columns = st.columns(2)
        for column, (_, row) in zip(columns, filtered.iloc[start : start + 2].iterrows()):
            home = _clean_team(row.get("home_team"))
            away = _clean_team(row.get("away_team"))
            match_number = row.get("logical_match_number") or row.get("bracket_match_number") or "—"
            readiness = _fixture_readiness(row)
            status = str(row.get("status") or "Pending").replace("_", " ").title()
            score = _score(row)
            advanced = _clean_team(row.get("advancing_team"))
            advanced_text = "" if advanced == "TBD" else f"<br><strong>Advanced:</strong> {advanced}"
            with column:
                st.markdown(
                    f'''
                    <div class="cm-project-card">
                        <div class="cm-project-label">Match {match_number} · {status}</div>
                        <strong>{home} {score} {away}</strong>
                        <p>{_timestamp(row.get('utc_date'))}</p>
                        <span>{readiness}{advanced_text}</span>
                    </div>
                    ''',
                    unsafe_allow_html=True,
                )


def _render_bracket_flow(source: pd.DataFrame) -> None:
    if source.empty or "stage" not in source.columns:
        return

    stage_values = sorted(
        source["stage"].dropna().astype(str).unique(),
        key=_stage_sort_key,
    )
    if not stage_values:
        return

    st.markdown("#### Bracket flow")
    tabs = st.tabs([stage_label(stage) for stage in stage_values])
    for tab, stage in zip(tabs, stage_values):
        with tab:
            stage_rows = source.loc[source["stage"].astype(str) == stage].copy()
            if "utc_date" in stage_rows.columns:
                stage_rows["utc_date"] = pd.to_datetime(
                    stage_rows["utc_date"], errors="coerce", utc=True
                )
                stage_rows = stage_rows.sort_values("utc_date", na_position="last")
            _render_fixture_cards(stage_rows)


def _render_tournament_fixtures(data: dict) -> None:
    st.markdown("### Tournament bracket and knockout progress")
    progress = data["progress"]
    bracket = data["bracket"]
    source = progress if not progress.empty else bracket

    with st.expander("Why some future fixtures may show no prediction", expanded=False):
        st.write(PREDICTION_EXPLAINER)

    if source.empty:
        st.info(
            "The official knockout bracket is not locked yet. CupMarket will move from "
            "projected paths to confirmed fixtures after the group-stage picture becomes clearer."
        )
        return

    _render_bracket_flow(source)

    stage_column = "stage" if "stage" in source.columns else None
    filtered = source.copy()
    if stage_column:
        stages = sorted(
            [value for value in filtered[stage_column].dropna().astype(str).unique()],
            key=_stage_sort_key,
        )
        if stages:
            selected_stage = st.selectbox(
                "Detailed table stage",
                stages,
                format_func=stage_label,
                key="cupmarket_path_stage",
            )
            filtered = filtered.loc[filtered[stage_column].astype(str) == selected_stage]

    columns = [
        column
        for column in [
            "logical_match_number",
            "bracket_match_number",
            "utc_date",
            "status",
            "home_team",
            "home_score",
            "away_score",
            "away_team",
            "decision_method",
            "advancing_team",
        ]
        if column in filtered.columns
    ]
    display = filtered[columns].copy()
    if "utc_date" in display.columns:
        display["utc_date"] = display["utc_date"].map(_timestamp)
    if {"home_score", "away_score"}.issubset(display.columns):
        display["Score"] = display.apply(_score, axis=1)
        display = display.drop(columns=["home_score", "away_score"])
    display["Forecast state"] = filtered.apply(_fixture_readiness, axis=1).values
    display = display.rename(
        columns={
            "logical_match_number": "Match",
            "bracket_match_number": "Match",
            "utc_date": "Kickoff · UTC",
            "status": "Status",
            "home_team": "Home",
            "away_team": "Away",
            "decision_method": "Decision",
            "advancing_team": "Advanced",
        }
    )
    for column in ["Home", "Away", "Advanced"]:
        if column in display.columns:
            display[column] = display[column].map(_clean_team)
    if "Decision" in display.columns:
        display["Decision"] = display["Decision"].map(
            lambda value: str(value).replace("_", " ").title() if pd.notna(value) else "—"
        )
    st.dataframe(display, hide_index=True, use_container_width=True)


def _render_tournament_forecast(data: dict) -> None:
    prices = data.get("prices", pd.DataFrame())
    path_status = data.get("path_status", pd.DataFrame())
    opponents = data.get("opponents", pd.DataFrame())

    st.markdown("### What the model can still forecast")
    st.caption(
        "This view is useful before all knockout fixtures are official. It uses stage "
        "probabilities and projected paths rather than fake match predictions."
    )

    if isinstance(path_status, pd.DataFrame) and not path_status.empty and "fixture_status" in path_status.columns:
        status_counts = (
            path_status["fixture_status"]
            .fillna("projected")
            .map(status_label)
            .value_counts()
            .rename_axis("Path state")
            .reset_index(name="Countries")
        )
        st.dataframe(status_counts, hide_index=True, use_container_width=True)

    if not isinstance(prices, pd.DataFrame) or prices.empty:
        return

    required = [
        "team",
        "prob_reach_round_32",
        "prob_reach_round_16",
        "prob_reach_quarter_final",
        "prob_reach_final",
        "prob_champion",
    ]
    available = [column for column in required if column in prices.columns]
    if "team" not in available:
        return
    forecast = prices[available].copy()
    for column in available:
        if column != "team":
            forecast[column] = pd.to_numeric(forecast[column], errors="coerce")
    if "prob_champion" in forecast.columns:
        forecast = forecast.sort_values("prob_champion", ascending=False)
    forecast = forecast.head(12)
    rename_map = {
        "team": "Country",
        "prob_reach_round_32": "Reach R32",
        "prob_reach_round_16": "Reach R16",
        "prob_reach_quarter_final": "Reach QF",
        "prob_reach_final": "Reach final",
        "prob_champion": "Champion",
    }
    forecast = forecast.rename(columns=rename_map)
    for column in forecast.columns:
        if column != "Country":
            forecast[column] = forecast[column].map(_percent)
    st.markdown("#### Strongest future paths right now")
    st.dataframe(forecast, hide_index=True, use_container_width=True)

    if isinstance(opponents, pd.DataFrame) and not opponents.empty:
        st.caption(
            "Projected opponent probabilities appear in each country profile. They are not "
            "the same as fixed fixture predictions."
        )


def _render_country_page_v2() -> None:
    st.markdown(
        '''
        <div class="cm-hero">
            <div class="cm-eyebrow">CupMarket 2026 - Country</div>
            <h1>One country. The route, price and next match.</h1>
            <p>Pick a country, then move through its snapshot, route, market story and fixture timeline.</p>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    data = load_tournament_path_data()
    summary = tournament_summary(data)
    metrics = st.columns(4)
    metrics[0].metric("Tournament stage", summary["current_stage"])
    metrics[1].metric("Bracket", summary["bracket_status"])
    metrics[2].metric("Knockout matches finished", summary["completed_knockout_matches"])
    metrics[3].metric("Knockout matches live", summary["live_knockout_matches"])

    teams = available_teams(data)
    if not teams:
        st.warning(
            "Tournament-path data is not available yet. The model and market pages remain "
            "available while the next official publication is prepared."
        )
        _render_tournament_fixtures(data)
        return

    with st.expander("How this country page is organized", expanded=False):
        st.write(PREDICTION_EXPLAINER)
        st.caption(
            "Snapshot is the fast answer. Path explains the road ahead. Market explains "
            "the CM price. Fixtures keeps the match timeline in one place."
        )

    requested = st.session_state.pop("cupmarket_path_requested_team", None)
    default_team = preferred_team(teams, requested, data["prices"])
    if st.session_state.get("cupmarket_path_team") not in teams:
        st.session_state["cupmarket_path_team"] = default_team
    team = st.selectbox("Country", teams, key="cupmarket_path_team")
    selected = team_summary(data, team)
    price = selected["price"]
    path = selected["path"]
    latest_fixture_result = _latest_finished_fixture(selected["fixtures"])
    result_state = _team_result_state(latest_fixture_result, team)
    reach_label, reach_value = _reach_metric_for_state(
        price,
        path,
        latest_fixture_result,
    )

    st.markdown(f"## {team}")
    cards = st.columns(4)
    cards[0].metric(
        "Current price",
        _number(price.get("cupmarket_price"), suffix=" CM") if not price.empty else "-",
    )
    cards[1].metric(
        "Path status",
        result_state.get("status")
        or (
            status_label(path.get("fixture_status"))
            if not path.empty
            else "Awaiting path data"
        ),
    )
    cards[2].metric(reach_label, _percent(reach_value))
    cards[3].metric("Become champion", _percent(price.get("prob_champion")) if not price.empty else "-")

    snapshot_tab, path_tab, market_tab, fixtures_tab = st.tabs(
        ["Snapshot", "Path", "Market", "Fixtures"]
    )

    with snapshot_tab:
        _render_path_message(path, selected["opponents"], latest_fixture_result, team)
        _render_next_knockout_slot(data["progress"], team)
        st.caption(
            "Use this tab when you only need the answer: status, next slot and headline odds."
        )

    with path_tab:
        _render_stage_probability_ladder(price, team)
        _render_tournament_forecast(data)
        _render_tournament_fixtures(data)

    with market_tab:
        render_market_explanation(
            team=team,
            price=price,
            movement=selected["movement"],
            progress=data["progress"],
            adaptive_ratings=data.get("adaptive_ratings", pd.DataFrame()),
            manifest=data.get("publication_manifest", {}),
        )
        _render_market_reaction(
            selected["movement"],
            data["history"],
            team,
            price,
            selected.get("latest_movement", pd.Series(dtype=object)),
        )

    with fixtures_tab:
        st.markdown("### Country fixture timeline")
        fixture_display = _team_fixture_table(selected["fixtures"], team)
        if fixture_display.empty:
            st.info(
                "A confirmed knockout fixture is not available for this country yet. Use the "
                "path forecast until the official bracket slot is known."
            )
        else:
            st.dataframe(fixture_display, hide_index=True, use_container_width=True)
        st.caption(
            "This table follows the selected country only. Open the Bracket page for the "
            "full tournament layout."
        )

    render_official_data_caption(data["prices"], label="Country market")
    with st.expander("How to read this page", expanded=False):
        st.markdown(
            "**Projected path** means earlier results are still changing the likely opponent.\n\n"
            "**Slot confirmed** means the country has secured a knockout position, but the "
            "other side of the fixture is not final.\n\n"
            "**Fixture confirmed** means the official bracket contains both countries.\n\n"
            "**Advanced** or **Eliminated** appears after a knockout result is processed.\n\n"
            "**Prediction unavailable** does not always mean the model failed. It usually "
            "means the fixture still contains unknown teams, so the app should show path "
            "probabilities instead of fake match odds.\n\n"
            "During knockout matches, official CupMarket values remain frozen until full "
            "time. Completed winners are then fixed in every future simulation."
        )


def render_tournament_path_page() -> None:
    _render_country_page_v2()
