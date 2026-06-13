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
        use_container_width=True,
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
        use_container_width=True,
        hide_index=True,
    )
