from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from backend.group_scenarios import (
    current_team_summary,
    run_qualification_scenarios,
)


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
        chart = px.bar(
            pd.DataFrame(chart_rows),
            x="Outcome",
            y=["Top two", "Best third"],
            title=f'{result["team"]}: routes to the Round of 32',
            barmode="stack",
        )
        chart.update_yaxes(tickformat=".0%", range=[0, 1])
        st.plotly_chart(polish_figure(chart), use_container_width=True)


def render_qualification_lab(
    matches: pd.DataFrame,
    predictions: pd.DataFrame,
    prices: pd.DataFrame,
    group_tables: pd.DataFrame,
    production_health: dict,
) -> None:
    st.markdown("### Win, draw or lose")
    st.caption(
        "Condition the next group match and simulate what each result means "
        "for qualification."
    )

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

    try:
        current = current_team_summary(matches, selected_team, strength)
    except ValueError as error:
        st.error(str(error))
        return

    current_columns = st.columns(5)
    current_columns[0].metric("Current position", current["current_position"])
    current_columns[1].metric("Points", current["current_points"])
    current_columns[2].metric("Played", current["played"])
    current_columns[3].metric("Goal difference", current["goal_difference"])
    current_columns[4].metric("Matches left", current["matches_remaining"])

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

    if not group_tables.empty:
        table = group_tables[
            group_tables["group"].astype(str) == current["group"]
        ].sort_values("position")
        if not table.empty:
            st.dataframe(
                table[
                    [
                        "position",
                        "team",
                        "played",
                        "wins",
                        "draws",
                        "losses",
                        "goal_difference",
                        "points",
                    ]
                ].rename(
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

    if production_health.get("pending_finished_matches", 0):
        st.warning(
            "A completed match is waiting to enter the published model. "
            "The live score is included, but remaining-match probabilities "
            "may refresh after the next workflow run."
        )

    if not current["matches_remaining"]:
        return

    if st.button(
        "Run qualification scenarios",
        type="primary",
        use_container_width=True,
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
            "Finished matches are fixed; remaining matches use the latest "
            "expected-goal forecasts."
        )
