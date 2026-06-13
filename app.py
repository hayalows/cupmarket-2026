
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import re

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(
    page_title="CupMarket 2026",
    page_icon="⚽",
    layout="wide",
)

APP_ROOT = Path(__file__).resolve().parent
DATA_DIR = APP_ROOT / "data"
HISTORY_DIR = DATA_DIR / "market_history"

PRICES_PATH = DATA_DIR / "cupmarket_prices_latest.csv"
PROBABILITIES_PATH = DATA_DIR / "tournament_probabilities_latest.csv"
GROUP_TABLES_PATH = DATA_DIR / "current_group_tables.csv"
PREDICTIONS_PATH = DATA_DIR / "world_cup_live_predictions_latest.csv"
MATCH_SNAPSHOT_PATH = DATA_DIR / "world_cup_2026_matches_latest.csv"

PHASE3_EVAL_PATH = DATA_DIR / "phase3_goal_model_evaluation.json"
PHASE4_EVAL_PATH = DATA_DIR / "phase4_live_evaluation.json"
PHASE5_META_PATH = DATA_DIR / "phase5_simulation_metadata.json"

API_URL = "https://api.football-data.org/v4/competitions/WC/matches"


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    frame = pd.read_csv(path)

    for column in [
        "utc_date",
        "generated_at_utc",
        "prediction_created_at",
        "last_updated",
    ]:
        if column in frame.columns:
            frame[column] = pd.to_datetime(
                frame[column],
                errors="coerce",
                utc=True,
            )

    return frame


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def format_percent(value, digits: int = 1) -> str:
    if pd.isna(value):
        return "—"
    return f"{100 * float(value):.{digits}f}%"


def format_number(value, digits: int = 2) -> str:
    if pd.isna(value):
        return "—"
    return f"{float(value):.{digits}f}"


def score_text(row: pd.Series) -> str:
    home = row.get("home_score_full_time")
    away = row.get("away_score_full_time")

    if pd.isna(home) or pd.isna(away):
        return "vs"

    return f"{int(home)}–{int(away)}"


def nested_get(dictionary, keys, default=None):
    current = dictionary

    for key in keys:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current is None:
            return default

    return current


def parse_api_matches(payload: dict) -> pd.DataFrame:
    rows = []

    for match in payload.get("matches", []):
        rows.append(
            {
                "match_id": match.get("id"),
                "utc_date": match.get("utcDate"),
                "status": match.get("status"),
                "stage": match.get("stage"),
                "group": match.get("group"),
                "home_team": nested_get(
                    match,
                    ["homeTeam", "name"],
                ),
                "away_team": nested_get(
                    match,
                    ["awayTeam", "name"],
                ),
                "home_score_full_time": nested_get(
                    match,
                    ["score", "fullTime", "home"],
                ),
                "away_score_full_time": nested_get(
                    match,
                    ["score", "fullTime", "away"],
                ),
                "last_updated": match.get("lastUpdated"),
            }
        )

    frame = pd.DataFrame(rows)

    if frame.empty:
        return frame

    frame["utc_date"] = pd.to_datetime(
        frame["utc_date"],
        errors="coerce",
        utc=True,
    )

    frame["last_updated"] = pd.to_datetime(
        frame["last_updated"],
        errors="coerce",
        utc=True,
    )

    return frame.sort_values("utc_date").reset_index(drop=True)


@st.cache_data(ttl=60, show_spinner=False)
def fetch_live_matches(token: str) -> tuple[pd.DataFrame, dict]:
    response = requests.get(
        API_URL,
        headers={"X-Auth-Token": token},
        timeout=30,
    )

    response.raise_for_status()

    metadata = {
        "requests_remaining": (
            response.headers.get("X-RequestsAvailable")
            or response.headers.get(
                "X-Requests-Available-Minute"
            )
        ),
        "counter_reset": response.headers.get(
            "X-RequestCounter-Reset"
        ),
        "fetched_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    return parse_api_matches(response.json()), metadata


def get_match_data() -> tuple[pd.DataFrame, dict]:
    token = None

    try:
        token = st.secrets.get(
            "FOOTBALL_DATA_TOKEN"
        )
    except Exception:
        token = None

    if token:
        try:
            matches, metadata = fetch_live_matches(
                str(token).strip()
            )
            metadata["source"] = "Live API"
            return matches, metadata
        except Exception as exc:
            fallback = read_csv(
                MATCH_SNAPSHOT_PATH
            )
            return fallback, {
                "source": "Saved snapshot",
                "warning": str(exc),
            }

    return read_csv(MATCH_SNAPSHOT_PATH), {
        "source": "Saved snapshot",
        "warning": (
            "No FOOTBALL_DATA_TOKEN was configured "
            "in Streamlit secrets."
        ),
    }


def load_price_history() -> pd.DataFrame:
    if not HISTORY_DIR.exists():
        return pd.DataFrame()

    rows = []

    for path in sorted(
        HISTORY_DIR.glob(
            "cupmarket_prices_*.csv"
        )
    ):
        frame = read_csv(path)

        if frame.empty:
            continue

        timestamp_match = re.search(
            r"(\d{8}T\d{6}Z)",
            path.name,
        )

        file_timestamp = pd.to_datetime(
            timestamp_match.group(1),
            format="%Y%m%dT%H%M%SZ",
            utc=True,
            errors="coerce",
        ) if timestamp_match else pd.NaT

        if "generated_at_utc" not in frame.columns:
            frame["generated_at_utc"] = (
                file_timestamp
            )

        rows.append(
            frame[
                [
                    "team",
                    "cupmarket_price",
                    "generated_at_utc",
                ]
            ]
        )

    if not rows:
        return pd.DataFrame()

    history = pd.concat(
        rows,
        ignore_index=True,
    )

    history = history.dropna(
        subset=[
            "team",
            "cupmarket_price",
            "generated_at_utc",
        ]
    )

    return (
        history
        .drop_duplicates(
            subset=[
                "team",
                "generated_at_utc",
            ],
            keep="last",
        )
        .sort_values(
            [
                "team",
                "generated_at_utc",
            ]
        )
        .reset_index(drop=True)
    )


prices = read_csv(PRICES_PATH)
probabilities = read_csv(PROBABILITIES_PATH)
group_tables = read_csv(GROUP_TABLES_PATH)
predictions = read_csv(PREDICTIONS_PATH)
price_history = load_price_history()

phase3_eval = read_json(PHASE3_EVAL_PATH)
phase4_eval = read_json(PHASE4_EVAL_PATH)
phase5_meta = read_json(PHASE5_META_PATH)

matches, match_metadata = get_match_data()

st.title("CupMarket 2026")
st.caption(
    "World Cup analytics, tournament simulation, "
    "and a virtual country market."
)

with st.sidebar:
    st.header("Navigation")

    page = st.radio(
        "Choose a page",
        [
            "Overview",
            "Match Centre",
            "Country Market",
            "Team Explorer",
            "Group Tables",
            "Model Health",
            "How It Works",
        ],
        label_visibility="collapsed",
    )

    st.divider()

    st.write(
        "**Score source:**",
        match_metadata.get(
            "source",
            "Unknown",
        ),
    )

    if match_metadata.get("warning"):
        st.caption(
            match_metadata["warning"]
        )

    if match_metadata.get(
        "fetched_at_utc"
    ):
        fetched_at = pd.to_datetime(
            match_metadata[
                "fetched_at_utc"
            ],
            utc=True,
        )

        st.caption(
            "Scores fetched "
            + fetched_at.strftime(
                "%Y-%m-%d %H:%M UTC"
            )
        )

    if phase5_meta.get(
        "generated_at_utc"
    ):
        simulation_time = pd.to_datetime(
            phase5_meta[
                "generated_at_utc"
            ],
            utc=True,
        )

        st.caption(
            "Simulation generated "
            + simulation_time.strftime(
                "%Y-%m-%d %H:%M UTC"
            )
        )

    st.caption(
        "Data provided by football-data.org"
    )


if page == "Overview":
    finished_count = int(
        (
            matches.get(
                "status",
                pd.Series(dtype=str),
            )
            == "FINISHED"
        ).sum()
    ) if not matches.empty else 0

    live_count = int(
        matches.get(
            "status",
            pd.Series(dtype=str),
        ).isin(
            ["IN_PLAY", "PAUSED"]
        ).sum()
    ) if not matches.empty else 0

    upcoming_count = int(
        matches.get(
            "status",
            pd.Series(dtype=str),
        ).isin(
            ["TIMED", "SCHEDULED"]
        ).sum()
    ) if not matches.empty else 0

    top_team = "—"
    top_price = "—"
    champion_probability = "—"

    if not prices.empty:
        leader = prices.sort_values(
            "cupmarket_price",
            ascending=False,
        ).iloc[0]

        top_team = leader["team"]
        top_price = format_number(
            leader["cupmarket_price"]
        )
        champion_probability = (
            format_percent(
                leader["prob_champion"]
            )
            if "prob_champion"
            in leader.index
            else "—"
        )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Finished matches",
        finished_count,
    )
    col2.metric(
        "Live matches",
        live_count,
    )
    col3.metric(
        "Upcoming matches",
        upcoming_count,
    )
    col4.metric(
        "Market leader",
        top_team,
        delta=(
            f"Price {top_price}"
            if top_price != "—"
            else None
        ),
    )

    st.subheader("Market leaders")

    if prices.empty:
        st.info(
            "No market-price file was found."
        )
    else:
        leader_table = prices[
            [
                "market_rank",
                "team",
                "group",
                "cupmarket_price",
                "prob_reach_round_32",
                "prob_reach_quarter_final",
                "prob_reach_final",
                "prob_champion",
            ]
        ].head(12).copy()

        for column in [
            "prob_reach_round_32",
            "prob_reach_quarter_final",
            "prob_reach_final",
            "prob_champion",
        ]:
            leader_table[column] = (
                leader_table[column]
                .map(format_percent)
            )

        st.dataframe(
            leader_table,
            width="stretch",
            hide_index=True,
        )

    st.subheader("Next matches")

    if matches.empty:
        st.info(
            "No match file was found."
        )
    else:
        next_matches = (
            matches[
                matches["status"].isin(
                    [
                        "TIMED",
                        "SCHEDULED",
                        "IN_PLAY",
                        "PAUSED",
                    ]
                )
            ]
            .sort_values("utc_date")
            .head(8)
            .copy()
        )

        if next_matches.empty:
            st.write(
                "No upcoming matches."
            )
        else:
            next_matches["kickoff_utc"] = (
                next_matches["utc_date"]
                .dt.strftime(
                    "%Y-%m-%d %H:%M"
                )
            )

            st.dataframe(
                next_matches[
                    [
                        "kickoff_utc",
                        "status",
                        "home_team",
                        "away_team",
                        "group",
                        "stage",
                    ]
                ],
                width="stretch",
                hide_index=True,
            )

    st.subheader("What the leader's probability means")
    st.write(
        f"{top_team} currently has the highest "
        f"CupMarket expected value. Its estimated "
        f"championship probability is "
        f"{champion_probability}. The price also "
        f"includes the value of reaching earlier "
        f"knockout stages, so it is not the same "
        f"as championship probability."
    )


elif page == "Match Centre":
    st.header("Match Centre")

    if st.button(
        "Refresh score cache",
        help=(
            "Clears the 60-second cache. "
            "Avoid repeated refreshes because "
            "the API is rate-limited."
        ),
    ):
        st.cache_data.clear()
        st.rerun()

    if matches.empty:
        st.warning(
            "No matches are available."
        )
    else:
        status_options = sorted(
            matches["status"]
            .dropna()
            .unique()
        )

        selected_statuses = st.multiselect(
            "Match status",
            status_options,
            default=status_options,
        )

        filtered = matches[
            matches["status"].isin(
                selected_statuses
            )
        ].copy()

        filtered["kickoff_utc"] = (
            filtered["utc_date"]
            .dt.strftime(
                "%Y-%m-%d %H:%M"
            )
        )

        filtered["score"] = filtered.apply(
            score_text,
            axis=1,
        )

        prediction_display = pd.DataFrame()

        if not predictions.empty:
            prediction_display = predictions[
                [
                    "match_id",
                    "expected_home_goals",
                    "expected_away_goals",
                    "prob_home_win",
                    "prob_draw",
                    "prob_away_win",
                    "display_label",
                    "most_likely_score",
                ]
            ].drop_duplicates(
                "match_id",
                keep="last",
            )

            filtered = filtered.merge(
                prediction_display,
                on="match_id",
                how="left",
            )

        display_columns = [
            "kickoff_utc",
            "status",
            "home_team",
            "score",
            "away_team",
            "group",
            "stage",
        ]

        for optional in [
            "expected_home_goals",
            "expected_away_goals",
            "prob_home_win",
            "prob_draw",
            "prob_away_win",
            "display_label",
            "most_likely_score",
        ]:
            if optional in filtered.columns:
                display_columns.append(
                    optional
                )

        st.dataframe(
            filtered[display_columns],
            width="stretch",
            hide_index=True,
        )

        if not prediction_display.empty:
            st.caption(
                "Match probabilities are the latest "
                "saved model outputs. Live scores can "
                "refresh every 60 seconds, but the "
                "probabilities update only when the "
                "model pipeline produces a new file."
            )


elif page == "Country Market":
    st.header("Country Market")

    if prices.empty:
        st.warning(
            "No CupMarket price file was found."
        )
    else:
        market_table = prices.copy()

        if "price_change_percent" in market_table.columns:
            market_table[
                "price_change_percent"
            ] = market_table[
                "price_change_percent"
            ].round(2)

        st.dataframe(
            market_table[
                [
                    column
                    for column in [
                        "market_rank",
                        "team",
                        "group",
                        "cupmarket_price",
                        "previous_price",
                        "price_change",
                        "price_change_percent",
                        "prob_reach_round_32",
                        "prob_reach_quarter_final",
                        "prob_reach_final",
                        "prob_champion",
                    ]
                    if column
                    in market_table.columns
                ]
            ],
            width="stretch",
            hide_index=True,
        )

        chart_data = prices.head(
            20
        ).sort_values(
            "cupmarket_price"
        )

        figure = px.bar(
            chart_data,
            x="cupmarket_price",
            y="team",
            orientation="h",
            title=(
                "Top 20 countries by "
                "CupMarket price"
            ),
        )

        st.plotly_chart(
            figure,
            width="stretch",
        )

        if not price_history.empty:
            selected_teams = st.multiselect(
                "Price-history teams",
                sorted(
                    price_history[
                        "team"
                    ].unique()
                ),
                default=list(
                    prices.head(5)[
                        "team"
                    ]
                ),
            )

            history_filtered = (
                price_history[
                    price_history[
                        "team"
                    ].isin(selected_teams)
                ]
            )

            if not history_filtered.empty:
                history_chart = px.line(
                    history_filtered,
                    x="generated_at_utc",
                    y="cupmarket_price",
                    color="team",
                    markers=True,
                    title=(
                        "CupMarket price history"
                    ),
                )

                st.plotly_chart(
                    history_chart,
                    width="stretch",
                )
        else:
            st.info(
                "Price history will appear after "
                "more than one simulation snapshot "
                "has been copied into the app."
            )


elif page == "Team Explorer":
    st.header("Team Explorer")

    if prices.empty:
        st.warning(
            "No tournament probability file "
            "was found."
        )
    else:
        team = st.selectbox(
            "Select a country",
            prices["team"].tolist(),
        )

        team_row = prices[
            prices["team"] == team
        ].iloc[0]

        col1, col2, col3, col4 = st.columns(
            4
        )

        col1.metric(
            "CupMarket price",
            format_number(
                team_row[
                    "cupmarket_price"
                ]
            ),
        )

        col2.metric(
            "Reach Round of 32",
            format_percent(
                team_row[
                    "prob_reach_round_32"
                ]
            ),
        )

        col3.metric(
            "Reach quarter-final",
            format_percent(
                team_row[
                    "prob_reach_quarter_final"
                ]
            ),
        )

        col4.metric(
            "Win tournament",
            format_percent(
                team_row[
                    "prob_champion"
                ]
            ),
        )

        stage_frame = pd.DataFrame(
            {
                "Stage": [
                    "Round of 32",
                    "Round of 16",
                    "Quarter-final",
                    "Semi-final",
                    "Final",
                    "Champion",
                ],
                "Probability": [
                    team_row[
                        "prob_reach_round_32"
                    ],
                    team_row[
                        "prob_reach_round_16"
                    ],
                    team_row[
                        "prob_reach_quarter_final"
                    ],
                    team_row[
                        "prob_reach_semi_final"
                    ],
                    team_row[
                        "prob_reach_final"
                    ],
                    team_row[
                        "prob_champion"
                    ],
                ],
            }
        )

        stage_chart = px.bar(
            stage_frame,
            x="Stage",
            y="Probability",
            title=(
                f"{team}: probability of "
                "reaching each stage"
            ),
        )

        stage_chart.update_yaxes(
            tickformat=".0%"
        )

        st.plotly_chart(
            stage_chart,
            width="stretch",
        )

        st.subheader("Group-position probabilities")

        group_position_frame = pd.DataFrame(
            {
                "Outcome": [
                    "Finish first",
                    "Finish second",
                    "Finish third",
                    "Qualify as best third",
                ],
                "Probability": [
                    team_row.get(
                        "prob_finish_1st_group",
                        0,
                    ),
                    team_row.get(
                        "prob_finish_2nd_group",
                        0,
                    ),
                    team_row.get(
                        "prob_finish_3rd_group",
                        0,
                    ),
                    team_row.get(
                        "prob_best_third_qualifier",
                        0,
                    ),
                ],
            }
        )

        st.dataframe(
            group_position_frame.assign(
                Probability=group_position_frame[
                    "Probability"
                ].map(format_percent)
            ),
            width="stretch",
            hide_index=True,
        )


elif page == "Group Tables":
    st.header("Current Group Tables")

    if group_tables.empty:
        st.warning(
            "No group-table file was found."
        )
    else:
        for group in sorted(
            group_tables["group"].unique()
        ):
            st.subheader(
                f"Group {group}"
            )

            table = (
                group_tables[
                    group_tables[
                        "group"
                    ] == group
                ]
                .sort_values("position")
                .copy()
            )

            st.dataframe(
                table[
                    [
                        "position",
                        "team",
                        "played",
                        "wins",
                        "draws",
                        "losses",
                        "goals_for",
                        "goals_against",
                        "goal_difference",
                        "points",
                    ]
                ],
                width="stretch",
                hide_index=True,
            )


elif page == "Model Health":
    st.header("Model Health")

    if phase3_eval:
        st.subheader(
            "Historical holdout performance"
        )

        metrics = [
            (
                "Outcome accuracy",
                phase3_eval.get(
                    "outcome_accuracy"
                ),
                "percent",
            ),
            (
                "Log loss",
                phase3_eval.get(
                    "outcome_log_loss"
                ),
                "number",
            ),
            (
                "Brier score",
                phase3_eval.get(
                    "outcome_multiclass_brier"
                ),
                "number",
            ),
            (
                "Exact-score accuracy",
                phase3_eval.get(
                    "exact_score_accuracy"
                ),
                "percent",
            ),
        ]

        columns = st.columns(4)

        for column, (
            label,
            value,
            format_type,
        ) in zip(columns, metrics):
            if value is None:
                displayed = "—"
            elif format_type == "percent":
                displayed = format_percent(
                    value
                )
            else:
                displayed = format_number(
                    value,
                    digits=4,
                )

            column.metric(
                label,
                displayed,
            )

    if phase4_eval:
        st.subheader(
            "Live published-prediction scorecard"
        )

        eligible = phase4_eval.get(
            "eligible_completed_predictions",
            0,
        )

        st.write(
            "Eligible completed predictions:",
            eligible,
        )

        if eligible:
            st.json(phase4_eval)
        else:
            st.info(
                phase4_eval.get(
                    "message",
                    "No eligible live results yet.",
                )
            )

    if phase5_meta:
        st.subheader(
            "Tournament simulation"
        )

        simulation_columns = st.columns(
            4
        )

        simulation_columns[0].metric(
            "Simulations",
            f"{phase5_meta.get('number_of_simulations', 0):,}",
        )

        simulation_columns[1].metric(
            "Finished group matches",
            phase5_meta.get(
                "finished_group_matches",
                0,
            ),
        )

        simulation_columns[2].metric(
            "Remaining group matches",
            phase5_meta.get(
                "remaining_group_matches",
                0,
            ),
        )

        simulation_columns[3].metric(
            "Runtime",
            (
                f"{phase5_meta.get('simulation_seconds', 0):.1f}s"
            ),
        )

        st.write(
            "**Bracket mode:**",
            phase5_meta.get(
                "bracket_mode",
                "Unknown",
            ),
        )

        limitations = phase5_meta.get(
            "limitations",
            [],
        )

        if limitations:
            st.write("**Known limitations:**")
            for limitation in limitations:
                st.write(
                    f"- {limitation}"
                )


elif page == "How It Works":
    st.header("How the system works")

    st.markdown(
        """
### Data layer

Historical international results build the original ratings and goal models.  
The football API supplies fixtures, statuses, and scores.

### Frozen baseline

The pre-tournament model remains unchanged. It records what the system believed before the tournament.

### Live state

After a match finishes, the live updater changes Elo ratings and recent attacking, defensive, and points form. It then creates new probabilities for future matches.

### Tournament simulator

Completed results are treated as facts. Remaining matches are simulated thousands of times. The engine builds group tables, selects the best third-placed teams, and simulates the knockout rounds.

### Country price

A country receives different settlement values depending on where it exits the tournament. Its current price is the probability-weighted value of all those possible outcomes.

### Current meaning of “live”

- Scores can refresh from the API every 60 seconds.
- Saved model probabilities update after the post-match pipeline runs.
- Tournament prices update after the simulator runs.
- In-play probabilities based on score and minute are not part of this version yet.
        """
    )

    st.warning(
        "CupMarket is a virtual analytics game. "
        "It does not accept real-money wagers."
    )
