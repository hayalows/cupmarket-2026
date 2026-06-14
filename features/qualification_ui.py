from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from backend.group_scenarios import (
    current_team_summary,
    run_qualification_scenarios,
)
from features.live_group_table import build_live_group_table
from features.live_qualification_ui import render_live_group


def format_percent(value, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{100 * float(value):.{digits}f}%"


def polish_figure(figure):
    figure.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#ffffff",
        font=dict(color="#4b5568", size=13),
        margin=dict(l=24, r=24, t=64, b=24),
    )
    figure.update_xaxes(gridcolor="#edf0f5", zeroline=False)
    figure.update_yaxes(gridcolor="#edf0f5", zeroline=False)
    return figure


@st.cache_data(ttl=900, show_spinner=False)
def cached_qualification_scenarios(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    team: str,
    strength_items: tuple,
    simulations: int = 2000,
) -> dict:
    return run_qualification_scenarios(
        matches,
        predictions,
        team,
        strength=dict(strength_items),
        n_simulations=simulations,
        random_seed=2026,
    )


def render_qualification_result(result: dict, compact: bool = False) -> None:
    if not result.get("available"):
        st.info(result.get("reason", "Scenario analysis is unavailable."))
        return

    labels = {
        "WIN": "If they win",
        "DRAW": "If they draw",
        "LOSS": "If they lose",
    }
    columns = st.columns(3)
    chart_rows = []

    for column, outcome in zip(columns, ["WIN", "DRAW", "LOSS"]):
        scenario = result["scenarios"][outcome]
        column.metric(
            labels[outcome],
            format_percent(scenario["qualification_probability"]),
            delta=f'{scenario["points_after_next_match"]} points after match',
            delta_color="off",
        )
        column.caption(
            f'Most likely group finish: {scenario["most_likely_group_position"]} · '
            f'Expected final points: {scenario["expected_final_points"]:.1f}'
        )
        column.write(scenario["message"])
        support = scenario.get("supporting_result")
        if support and support.get("lift", 0) > 0.01:
            column.caption(
                "Helpful other result: "
                + support["label"]
                + " · qualification becomes "
                + format_percent(support["qualification_probability"])
            )
        chart_rows.append(
            {
                "Outcome": outcome.title(),
                "Top two": scenario["direct_top_two_probability"],
                "Best third": scenario["best_third_probability"],
            }
        )

    if not compact:
        with st.expander("Compare direct and best-third routes", expanded=False):
            chart = px.bar(
                pd.DataFrame(chart_rows),
                x="Outcome",
                y=["Top two", "Best third"],
                title=f'{result["team"]}: routes to the Round of 32',
                barmode="stack",
            )
            chart.update_yaxes(tickformat=".0%", range=[0, 1])
            st.plotly_chart(polish_figure(chart), use_container_width=True)


def _display_group_table(table: pd.DataFrame) -> None:
    if table.empty:
        return
    required = [
        "position",
        "team",
        "played",
        "wins",
        "draws",
        "losses",
        "goal_difference",
        "points",
    ]
    available = [column for column in required if column in table.columns]
    st.dataframe(
        table[available].rename(
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
        ),
        use_container_width=True,
        hide_index=True,
    )


def _render_current_detail(
    matches: pd.DataFrame,
    group_tables: pd.DataFrame,
    current: dict,
    strength: dict,
) -> None:
    with st.expander("Current table and team detail", expanded=False):
        details = st.columns(2)
        details[0].metric("Played", current["played"])
        details[1].metric("Goal difference", current["goal_difference"])

        live_table = build_live_group_table(
            matches,
            current["group"],
            strength,
        )
        if not live_table.empty:
            _display_group_table(live_table)
            st.caption("Group table calculated from the current score source.")
        elif not group_tables.empty:
            fallback_table = group_tables[
                group_tables["group"].astype(str) == current["group"]
            ].sort_values("position")
            _display_group_table(fallback_table)
            st.caption("Showing the latest saved group table.")


def render_qualification_lab(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    prices: pd.DataFrame,
    group_tables: pd.DataFrame,
    production_health: dict,
) -> None:
    st.markdown("### Your country’s route")

    group_matches = (
        matches[
            (matches["stage"] == "GROUP_STAGE")
            & matches["home_team"].notna()
            & matches["away_team"].notna()
        ].copy()
        if not matches.empty
        else pd.DataFrame()
    )
    if group_matches.empty:
        st.warning("No group-stage fixtures are available.")
        return

    teams = sorted(
        set(group_matches["home_team"]).union(set(group_matches["away_team"]))
    )
    selected_team = st.selectbox("Select a country", teams)
    strength = (
        dict(zip(prices["team"], prices["cupmarket_price"]))
        if not prices.empty
        else {}
    )

    if render_live_group(matches, predictions, prices, selected_team):
        return

    try:
        current = current_team_summary(matches, selected_team, strength)
    except ValueError as error:
        st.error(str(error))
        return

    summary = st.columns(3)
    summary[0].metric("Current position", current["current_position"])
    summary[1].metric("Points", current["current_points"])
    summary[2].metric("Matches left", current["matches_remaining"])

    if current.get("next_opponent"):
        kickoff = pd.to_datetime(
            current.get("next_kickoff_utc"), errors="coerce", utc=True
        )
        kickoff_text = (
            kickoff.strftime("%d %B · %H:%M UTC")
            if pd.notna(kickoff)
            else "time pending"
        )
        st.info(
            f'Next match: **{selected_team} vs {current["next_opponent"]}** · '
            f'{kickoff_text}'
        )
    else:
        st.info("This country has completed its group-stage matches.")

    if production_health.get("pending_finished_matches", 0):
        pending = int(production_health["pending_finished_matches"])
        st.warning(
            f"{pending} completed group match"
            + ("es are" if pending != 1 else " is")
            + " awaiting the published model update. Current scores and standings are "
            "live; remaining-match forecasts still use the last published model."
        )

    if current["matches_remaining"]:
        if st.button(
            "Compare win, draw and loss",
            type="primary",
            use_container_width=True,
            key=f"qualification_compare_{selected_team}",
        ):
            with st.spinner(
                "Running win, draw and loss simulations across all groups..."
            ):
                result = cached_qualification_scenarios(
                    matches,
                    predictions,
                    selected_team,
                    tuple(sorted(strength.items())),
                    2500,
                )
            st.session_state["qualification_lab_result"] = result
            st.session_state["qualification_lab_team"] = selected_team

        saved_result = st.session_state.get("qualification_lab_result")
        if (
            saved_result
            and st.session_state.get("qualification_lab_team") == selected_team
        ):
            render_qualification_result(saved_result)
            st.caption(
                f'Each outcome uses '
                f'{saved_result.get("n_simulations_per_scenario", 0):,} simulations. '
                "Finished matches come from the current score source; remaining matches "
                "use the latest published expected-goal forecasts."
            )

    _render_current_detail(matches, group_tables, current, strength)
