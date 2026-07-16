from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from features.team_projection import project_team


def percent(value: float) -> str:
    return f"{100 * float(value):.1f}%"


def table_view(rows: list[dict]) -> pd.DataFrame:
    columns = [
        "position", "team", "played", "wins", "draws", "losses",
        "goal_difference", "points",
    ]
    return pd.DataFrame(rows)[columns].rename(
        columns={
            "position": "Pos", "team": "Country", "played": "P",
            "wins": "W", "draws": "D", "losses": "L",
            "goal_difference": "GD", "points": "Pts",
        }
    )


def render_provisional(context: dict) -> None:
    metrics = st.columns(4)
    metrics[0].metric("Provisional position", context["position"])
    metrics[1].metric("Provisional points", context["points"])
    metrics[2].metric("Goal difference", context["goal_difference"])
    metrics[3].metric("If matches ended now", context["status_if_ended_now"])

    st.dataframe(
        table_view(context["table"]),
        width="stretch",
        hide_index=True,
    )

    thirds = pd.DataFrame(context["ranked_thirds"])
    if thirds.empty:
        return
    thirds.insert(0, "rank", range(1, len(thirds) + 1))
    thirds["status"] = thirds["rank"].map(
        lambda rank: "Qualifying" if rank <= 8 else "Outside"
    )
    st.subheader("Provisional best third-place ranking")
    st.dataframe(
        thirds[
            ["rank", "team", "group", "points", "goal_difference", "goals_for", "status"]
        ].rename(
            columns={
                "rank": "Rank", "team": "Country", "group": "Group",
                "points": "Pts", "goal_difference": "GD",
                "goals_for": "GF", "status": "Status",
            }
        ),
        width="stretch",
        hide_index=True,
    )


def render_projection(
    matches,
    predictions,
    team: str,
    strength: dict[str, float],
) -> None:
    if st.button(
        "Update live projection",
        type="primary",
        width="stretch",
    ):
        with st.spinner("Simulating the remaining group stage from the current scores..."):
            result = project_team(
                matches, predictions, team, strength, simulations=2500
            )
        st.session_state["live_group_projection"] = result
        st.session_state["live_group_team"] = team

    result = st.session_state.get("live_group_projection")
    if not result or st.session_state.get("live_group_team") != team:
        return

    metrics = st.columns(5)
    metrics[0].metric(
        "Live qualification probability",
        percent(result["qualification_probability"]),
    )
    metrics[1].metric(
        "Direct top-two probability",
        percent(result["direct_probability"]),
    )
    metrics[2].metric(
        "Best-third probability",
        percent(result["best_third_probability"]),
    )
    metrics[3].metric(
        "Expected final points",
        f'{result["expected_final_points"]:.1f}',
    )
    metrics[4].metric(
        "Most likely final score",
        result.get("most_likely_final_score") or "—",
    )

    position_frame = pd.DataFrame(
        {
            "Position": ["1st", "2nd", "3rd", "4th"],
            "Probability": [
                result["position_probabilities"].get(position, 0.0)
                for position in range(1, 5)
            ],
        }
    )
    chart = px.bar(
        position_frame,
        x="Position",
        y="Probability",
        title=f'{team}: projected group finish from the current score state',
    )
    chart.update_yaxes(tickformat=".0%", range=[0, 1])
    chart.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#ffffff",
    )
    st.plotly_chart(chart, width="stretch")
    st.caption(result["method"])
    st.warning(
        "This is an approximate live projection, not the official CupMarket model. "
        "Official ratings and country prices remain unchanged until the match is final."
    )
