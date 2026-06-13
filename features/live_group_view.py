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
