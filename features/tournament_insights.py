from __future__ import annotations

import pandas as pd
import streamlit as st

CONTINENT_MAP = {
    "Algeria": "Africa",
    "Argentina": "South America",
    "Australia": "Asia/Oceania",
    "Austria": "Europe",
    "Belgium": "Europe",
    "Bosnia-Herzegovina": "Europe",
    "Brazil": "South America",
    "Canada": "North America",
    "Cape Verde Islands": "Africa",
    "Colombia": "South America",
    "Congo DR": "Africa",
    "Croatia": "Europe",
    "Curaçao": "North America",
    "Czechia": "Europe",
    "Ecuador": "South America",
    "Egypt": "Africa",
    "England": "Europe",
    "France": "Europe",
    "Germany": "Europe",
    "Ghana": "Africa",
    "Haiti": "North America",
    "Iran": "Asia",
    "Iraq": "Asia",
    "Ivory Coast": "Africa",
    "Japan": "Asia",
    "Jordan": "Asia",
    "Mexico": "North America",
    "Morocco": "Africa",
    "Netherlands": "Europe",
    "New Zealand": "Oceania",
    "Norway": "Europe",
    "Panama": "North America",
    "Paraguay": "South America",
    "Portugal": "Europe",
    "Qatar": "Asia",
    "Saudi Arabia": "Asia",
    "Scotland": "Europe",
    "Senegal": "Africa",
    "South Africa": "Africa",
    "South Korea": "Asia",
    "Spain": "Europe",
    "Sweden": "Europe",
    "Switzerland": "Europe",
    "Tunisia": "Africa",
    "Turkey": "Europe",
    "United States": "North America",
    "Uruguay": "South America",
    "Uzbekistan": "Asia",
}


def _percent(value, digits: int = 1) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "—"
    return f"{100 * float(number):.{digits}f}%"


def _number(value, digits: int = 2) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "—"
    return f"{float(number):.{digits}f}"


def _timestamp(frame: pd.DataFrame) -> str:
    if frame.empty or "generated_at_utc" not in frame.columns:
        return "time unavailable"
    values = frame["generated_at_utc"].dropna()
    if values.empty:
        return "time unavailable"
    timestamp = pd.to_datetime(values.iloc[0], errors="coerce", utc=True)
    if pd.isna(timestamp):
        return "time unavailable"
    return timestamp.strftime("%d %b %Y · %H:%M UTC")


def _latest_event(movements: pd.DataFrame) -> str:
    if movements.empty or "trigger_matches" not in movements.columns:
        return "No recent match batch found."
    value = movements["trigger_matches"].dropna()
    if value.empty:
        return "No recent match batch found."
    return str(value.iloc[0]).replace(" | ", " · ")


def _qualifying_frame(prices: pd.DataFrame, threshold: float = 0.999) -> pd.DataFrame:
    if prices.empty or "prob_reach_round_32" not in prices.columns:
        return pd.DataFrame()
    frame = prices.copy()
    frame["prob_reach_round_32"] = pd.to_numeric(frame["prob_reach_round_32"], errors="coerce")
    return frame.loc[frame["prob_reach_round_32"] >= threshold].copy()


def _render_table(frame: pd.DataFrame, columns: list[str], labels: dict[str, str], percent_columns: list[str] | None = None) -> None:
    if frame.empty:
        st.caption("No data available for this section yet.")
        return
    display = frame[[column for column in columns if column in frame.columns]].copy()
    percent_columns = percent_columns or []
    for column in percent_columns:
        if column in display.columns:
            display[column] = display[column].map(_percent)
    for column in ["cupmarket_price", "previous_price", "price_change", "price_change_percent"]:
        if column in display.columns and column not in percent_columns:
            if column == "price_change_percent":
                display[column] = display[column].map(lambda value: f"{float(value):+.2f}%" if pd.notna(value) else "—")
            else:
                display[column] = display[column].map(lambda value: _number(value))
    display = display.rename(columns=labels)
    st.dataframe(display, hide_index=True, use_container_width=True)


def render_tournament_insights(prices: pd.DataFrame, tables: pd.DataFrame, movements: pd.DataFrame, path_status: pd.DataFrame) -> None:
    st.markdown("### What changed after the latest model run?")
    st.caption(f"Published model: {_timestamp(prices)}")
    st.info(_latest_event(movements))

    if not prices.empty:
        prices = prices.copy()
        prices["continent"] = prices["team"].map(CONTINENT_MAP).fillna("Other")
        for column in ["prob_reach_round_32", "cupmarket_price", "price_change_percent", "price_change"]:
            if column in prices.columns:
                prices[column] = pd.to_numeric(prices[column], errors="coerce")

    if not tables.empty:
        tables = tables.copy()
        for column in ["goals_for", "goals_against", "goal_difference", "points", "played", "wins", "draws", "losses"]:
            if column in tables.columns:
                tables[column] = pd.to_numeric(tables[column], errors="coerce")

    top_cards = st.columns(4)
    qualified = _qualifying_frame(prices)
    top_cards[0].metric("Round of 32 safe", len(qualified) if not qualified.empty else 0)
    top_cards[1].metric("Continents represented", qualified["continent"].nunique() if not qualified.empty else 0)
    if not tables.empty:
        top_cards[2].metric("Most goals by a team", int(tables["goals_for"].max()))
        top_cards[3].metric("Worst goals against", int(tables["goals_against"].max()))
    else:
        top_cards[2].metric("Most goals by a team", "—")
        top_cards[3].metric("Worst goals against", "—")

    st.markdown("### Biggest model winners")
    if not prices.empty and "price_change_percent" in prices.columns:
        winners = prices.dropna(subset=["price_change_percent"]).sort_values("price_change_percent", ascending=False).head(8)
        _render_table(
            winners,
            ["team", "continent", "cupmarket_price", "price_change_percent", "prob_reach_round_32", "prob_champion"],
            {
                "team": "Country",
                "continent": "Continent",
                "cupmarket_price": "Price",
                "price_change_percent": "Move",
                "prob_reach_round_32": "Reach R32",
                "prob_champion": "Champion",
            },
            percent_columns=["prob_reach_round_32", "prob_champion"],
        )

    st.markdown("### Biggest model losers")
    if not prices.empty and "price_change_percent" in prices.columns:
        losers = prices.dropna(subset=["price_change_percent"]).sort_values("price_change_percent", ascending=True).head(8)
        _render_table(
            losers,
            ["team", "continent", "cupmarket_price", "price_change_percent", "prob_reach_round_32", "prob_group_exit"],
            {
                "team": "Country",
                "continent": "Continent",
                "cupmarket_price": "Price",
                "price_change_percent": "Move",
                "prob_reach_round_32": "Reach R32",
                "prob_group_exit": "Group exit",
            },
            percent_columns=["prob_reach_round_32", "prob_group_exit"],
        )

    st.markdown("### Non-obvious tournament facts")
    facts = []
    if not tables.empty:
        no_goals = tables.loc[tables["goals_for"] == 0, "team"].astype(str).tolist()
        if no_goals:
            facts.append(f"Teams with no goals: {', '.join(no_goals)}.")
        most_for = tables.loc[tables["goals_for"] == tables["goals_for"].max(), ["team", "goals_for"]]
        facts.append("Most goals scored: " + ", ".join(f"{row.team} ({int(row.goals_for)})" for row in most_for.itertuples()) + ".")
        most_against = tables.loc[tables["goals_against"] == tables["goals_against"].max(), ["team", "goals_against"]]
        facts.append("Most goals conceded: " + ", ".join(f"{row.team} ({int(row.goals_against)})" for row in most_against.itertuples()) + ".")
        unbeaten = tables.loc[(tables["losses"] == 0) & (tables["played"] > 0), "team"].astype(str).tolist()
        if unbeaten:
            facts.append(f"Unbeaten teams so far: {', '.join(unbeaten)}.")
        winless_qualified = pd.DataFrame()
        if not qualified.empty:
            winless_qualified = qualified.merge(tables[["team", "wins", "draws", "points"]], on="team", how="left")
            winless_qualified = winless_qualified.loc[(winless_qualified["wins"] == 0) & (winless_qualified["prob_reach_round_32"] >= 0.999)]
        if not winless_qualified.empty:
            facts.append("Qualified without winning: " + ", ".join(winless_qualified["team"].astype(str).tolist()) + ".")
    for fact in facts:
        st.write(f"- {fact}")

    st.markdown("### Continents in the Round of 32 picture")
    if not qualified.empty:
        continent_counts = (
            qualified.groupby("continent")["team"]
            .agg([("Countries", "count"), ("Teams", lambda values: ", ".join(sorted(values.astype(str))))])
            .reset_index()
            .sort_values("Countries", ascending=False)
        )
        continent_counts = continent_counts.rename(columns={"continent": "Continent"})
        st.dataframe(continent_counts, hide_index=True, use_container_width=True)
        st.caption("This uses teams with at least 99.9% Round-of-32 probability in the latest CupMarket model.")

    st.markdown("### Teams still on the edge")
    if not prices.empty and "prob_reach_round_32" in prices.columns:
        edge = prices.loc[(prices["prob_reach_round_32"] > 0.0) & (prices["prob_reach_round_32"] < 0.999)].sort_values("prob_reach_round_32", ascending=False)
        _render_table(
            edge,
            ["team", "continent", "prob_reach_round_32", "prob_group_exit", "cupmarket_price"],
            {
                "team": "Country",
                "continent": "Continent",
                "prob_reach_round_32": "Reach R32",
                "prob_group_exit": "Group exit",
                "cupmarket_price": "Price",
            },
            percent_columns=["prob_reach_round_32", "prob_group_exit"],
        )

    st.markdown("### Likely bracket stories")
    if isinstance(path_status, pd.DataFrame) and not path_status.empty:
        cols = ["team", "fixture_status", "current_group_position", "prob_reach_round_32", "most_likely_opponent", "most_likely_opponent_probability_given_qualification"]
        display = path_status[[column for column in cols if column in path_status.columns]].copy()
        if "prob_reach_round_32" in display.columns:
            display["prob_reach_round_32"] = display["prob_reach_round_32"].map(_percent)
        if "most_likely_opponent_probability_given_qualification" in display.columns:
            display["most_likely_opponent_probability_given_qualification"] = display["most_likely_opponent_probability_given_qualification"].map(_percent)
        display = display.rename(
            columns={
                "team": "Country",
                "fixture_status": "Path state",
                "current_group_position": "Group pos",
                "prob_reach_round_32": "Reach R32",
                "most_likely_opponent": "Likely opponent",
                "most_likely_opponent_probability_given_qualification": "Opponent chance if qualified",
            }
        )
        st.dataframe(display, hide_index=True, use_container_width=True)
