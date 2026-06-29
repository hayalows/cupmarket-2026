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


def _percentage_points(value, digits: int = 1) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "—"
    return f"{100 * float(number):+.{digits}f} pts"


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
    label = str(value.iloc[0]).replace(" | ", " · ")
    movement_type = ""
    if "movement_type" in movements.columns:
        movement_values = movements["movement_type"].dropna()
        if not movement_values.empty:
            movement_type = str(movement_values.iloc[0])
    if movement_type == "publication_refresh":
        return f"Latest market publication: {label}."
    return f"Latest match event: {label}."


def _qualifying_frame(prices: pd.DataFrame, threshold: float = 0.999) -> pd.DataFrame:
    if prices.empty or "prob_reach_round_32" not in prices.columns:
        return pd.DataFrame()
    frame = prices.copy()
    frame["prob_reach_round_32"] = pd.to_numeric(frame["prob_reach_round_32"], errors="coerce")
    return frame.loc[frame["prob_reach_round_32"] >= threshold].copy()


def _render_table(frame: pd.DataFrame, columns: list[str], labels: dict[str, str], percent_columns: list[str] | None = None, pp_columns: list[str] | None = None) -> None:
    if frame.empty:
        st.caption("No data available for this section yet.")
        return
    display = frame[[column for column in columns if column in frame.columns]].copy()
    percent_columns = percent_columns or []
    pp_columns = pp_columns or []
    for column in percent_columns:
        if column in display.columns:
            display[column] = display[column].map(_percent)
    for column in pp_columns:
        if column in display.columns:
            display[column] = display[column].map(_percentage_points)
    for column in ["cupmarket_price", "opening_price", "current_price", "price_change", "price_gain", "price_change_percent"]:
        if column in display.columns and column not in percent_columns and column not in pp_columns:
            if column == "price_change_percent":
                display[column] = display[column].map(lambda value: f"{float(value):+.2f}%" if pd.notna(value) else "—")
            else:
                display[column] = display[column].map(lambda value: _number(value))
    display = display.rename(columns=labels)
    st.dataframe(display, hide_index=True, use_container_width=True)


def _prepare_prices(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()
    frame = prices.copy()
    frame["continent"] = frame["team"].map(CONTINENT_MAP).fillna("Other") if "team" in frame.columns else "Other"
    numeric_columns = [
        "prob_reach_round_32",
        "prob_group_exit",
        "prob_champion",
        "cupmarket_price",
        "price_change_percent",
        "price_change",
        "market_rank",
    ]
    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _prepare_tables(tables: pd.DataFrame) -> pd.DataFrame:
    if tables.empty:
        return pd.DataFrame()
    frame = tables.copy()
    for column in ["goals_for", "goals_against", "goal_difference", "points", "played", "wins", "draws", "losses"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _snapshot_change_frame(snapshots: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    if snapshots.empty or "team" not in snapshots.columns:
        return pd.DataFrame()
    frame = snapshots.copy()
    if "generated_at_utc" not in frame.columns:
        return pd.DataFrame()
    frame["generated_at_utc"] = pd.to_datetime(frame["generated_at_utc"], errors="coerce", utc=True)
    frame = frame.dropna(subset=["generated_at_utc", "team"])
    for column in ["cupmarket_price", "prob_reach_round_32", "prob_champion", "market_rank"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame.empty:
        return pd.DataFrame()

    earliest = frame.sort_values("generated_at_utc").groupby("team", as_index=False).first()
    latest_from_snapshots = frame.sort_values("generated_at_utc").groupby("team", as_index=False).last()

    latest = latest_from_snapshots
    if not prices.empty and "team" in prices.columns:
        latest_prices = prices.copy()
        for column in ["cupmarket_price", "prob_reach_round_32", "prob_champion", "market_rank"]:
            if column in latest_prices.columns:
                latest_prices[column] = pd.to_numeric(latest_prices[column], errors="coerce")
        latest_prices["generated_at_utc"] = pd.to_datetime(latest_prices.get("generated_at_utc"), errors="coerce", utc=True) if "generated_at_utc" in latest_prices.columns else pd.NaT
        latest = pd.concat([latest_from_snapshots, latest_prices], ignore_index=True, sort=False).sort_values("generated_at_utc").groupby("team", as_index=False).last()

    merged = earliest.merge(latest, on="team", suffixes=("_opening", "_current"))
    if merged.empty:
        return merged
    merged["continent"] = merged["team"].map(CONTINENT_MAP).fillna("Other")
    merged["opening_time"] = merged.get("generated_at_utc_opening")
    merged["current_time"] = merged.get("generated_at_utc_current")
    merged["opening_price"] = merged.get("cupmarket_price_opening")
    merged["current_price"] = merged.get("cupmarket_price_current")
    merged["price_gain"] = merged["current_price"] - merged["opening_price"]
    merged["opening_r32"] = merged.get("prob_reach_round_32_opening")
    merged["current_r32"] = merged.get("prob_reach_round_32_current")
    merged["r32_change"] = merged["current_r32"] - merged["opening_r32"]
    merged["opening_champion"] = merged.get("prob_champion_opening")
    merged["current_champion"] = merged.get("prob_champion_current")
    merged["champion_change"] = merged["current_champion"] - merged["opening_champion"]
    return merged


def _prediction_review(prediction_ledger: pd.DataFrame) -> pd.DataFrame:
    if prediction_ledger.empty:
        return pd.DataFrame()
    required = {"match_id", "home_team", "away_team", "predicted_result", "actual_home_score", "actual_away_score"}
    if not required.issubset(prediction_ledger.columns):
        return pd.DataFrame()
    frame = prediction_ledger.copy()
    frame["generated_at_utc"] = pd.to_datetime(frame.get("generated_at_utc"), errors="coerce", utc=True)
    frame["actual_home_score"] = pd.to_numeric(frame["actual_home_score"], errors="coerce")
    frame["actual_away_score"] = pd.to_numeric(frame["actual_away_score"], errors="coerce")
    frame = frame.dropna(subset=["match_id", "actual_home_score", "actual_away_score"])
    if "created_before_kickoff" in frame.columns:
        created = frame["created_before_kickoff"].astype(str).str.lower().isin(["true", "1", "yes"])
        frame = frame.loc[created | frame["prediction_type"].astype(str).str.contains("pre", case=False, na=False)]
    frame = frame.sort_values("generated_at_utc").drop_duplicates("match_id", keep="first")
    if frame.empty:
        return frame

    def actual(row: pd.Series) -> str:
        if row["actual_home_score"] > row["actual_away_score"]:
            return "HOME_WIN"
        if row["actual_home_score"] < row["actual_away_score"]:
            return "AWAY_WIN"
        return "DRAW"

    frame["actual_result"] = frame.apply(actual, axis=1)
    frame["model_correct"] = frame["predicted_result"].astype(str) == frame["actual_result"].astype(str)
    probability_columns = {"HOME_WIN": "prob_home_win", "DRAW": "prob_draw", "AWAY_WIN": "prob_away_win"}
    for column in probability_columns.values():
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["actual_result_probability"] = frame.apply(lambda row: row.get(probability_columns.get(row["actual_result"], ""), pd.NA), axis=1)
    frame["scoreline"] = frame["actual_home_score"].astype(int).astype(str) + "-" + frame["actual_away_score"].astype(int).astype(str)
    frame["match"] = frame["home_team"].astype(str) + " " + frame["scoreline"] + " " + frame["away_team"].astype(str)
    return frame


def _render_tournament_so_far(prices: pd.DataFrame, snapshots: pd.DataFrame, prediction_ledger: pd.DataFrame) -> None:
    st.markdown("## Tournament So Far")
    st.caption("This section compares the earliest stored CupMarket snapshot with the latest model output. If the first snapshot is not pre-tournament, the label stays honest: earliest stored snapshot.")
    changes = _snapshot_change_frame(snapshots, prices)
    reviews = _prediction_review(prediction_ledger)

    if changes.empty:
        st.info("No team snapshot history found yet. Once snapshots exist, this section will show full tournament movement.")
        return

    opening_time = pd.to_datetime(changes["opening_time"], errors="coerce", utc=True).min()
    current_time = pd.to_datetime(changes["current_time"], errors="coerce", utc=True).max()
    cols = st.columns(4)
    cols[0].metric("Teams tracked", len(changes))
    cols[1].metric("Baseline", opening_time.strftime("%d %b") if pd.notna(opening_time) else "—")
    cols[2].metric("Latest", current_time.strftime("%d %b · %H:%M") if pd.notna(current_time) else "—")
    if not reviews.empty:
        accuracy = reviews["model_correct"].mean()
        cols[3].metric("Pre-match calls", f"{100 * accuracy:.1f}%")
    else:
        cols[3].metric("Pre-match calls", "—")

    tab1, tab2, tab3, tab4 = st.tabs(["Overperformers", "Underperformers", "Market journey", "Model calls"])

    with tab1:
        st.markdown("### Biggest Round-of-32 probability gainers")
        gainers = changes.dropna(subset=["r32_change"]).sort_values("r32_change", ascending=False).head(10)
        _render_table(
            gainers,
            ["team", "continent", "opening_r32", "current_r32", "r32_change", "opening_price", "current_price", "price_gain"],
            {
                "team": "Country",
                "continent": "Continent",
                "opening_r32": "Opening R32",
                "current_r32": "Current R32",
                "r32_change": "R32 change",
                "opening_price": "Opening price",
                "current_price": "Current price",
                "price_gain": "Price gain",
            },
            percent_columns=["opening_r32", "current_r32"],
            pp_columns=["r32_change"],
        )
        st.caption("Use this to spot teams that moved from doubt to safety.")

    with tab2:
        st.markdown("### Biggest Round-of-32 probability fallers")
        fallers = changes.dropna(subset=["r32_change"]).sort_values("r32_change", ascending=True).head(10)
        _render_table(
            fallers,
            ["team", "continent", "opening_r32", "current_r32", "r32_change", "opening_price", "current_price", "price_gain"],
            {
                "team": "Country",
                "continent": "Continent",
                "opening_r32": "Opening R32",
                "current_r32": "Current R32",
                "r32_change": "R32 change",
                "opening_price": "Opening price",
                "current_price": "Current price",
                "price_gain": "Price gain",
            },
            percent_columns=["opening_r32", "current_r32"],
            pp_columns=["r32_change"],
        )
        st.caption("Use this to spot teams that lost control of their tournament path.")

    with tab3:
        st.markdown("### Biggest price risers since earliest stored snapshot")
        price_risers = changes.dropna(subset=["price_gain"]).sort_values("price_gain", ascending=False).head(10)
        _render_table(
            price_risers,
            ["team", "continent", "opening_price", "current_price", "price_gain", "opening_champion", "current_champion", "champion_change"],
            {
                "team": "Country",
                "continent": "Continent",
                "opening_price": "Opening price",
                "current_price": "Current price",
                "price_gain": "Price gain",
                "opening_champion": "Opening champion",
                "current_champion": "Current champion",
                "champion_change": "Champion change",
            },
            percent_columns=["opening_champion", "current_champion"],
            pp_columns=["champion_change"],
        )
        st.markdown("### Biggest price fallers")
        price_fallers = changes.dropna(subset=["price_gain"]).sort_values("price_gain", ascending=True).head(8)
        _render_table(
            price_fallers,
            ["team", "continent", "opening_price", "current_price", "price_gain", "opening_r32", "current_r32", "r32_change"],
            {
                "team": "Country",
                "continent": "Continent",
                "opening_price": "Opening price",
                "current_price": "Current price",
                "price_gain": "Price gain",
                "opening_r32": "Opening R32",
                "current_r32": "Current R32",
                "r32_change": "R32 change",
            },
            percent_columns=["opening_r32", "current_r32"],
            pp_columns=["r32_change"],
        )

    with tab4:
        if reviews.empty:
            st.caption("Prediction ledger review is not available yet.")
        else:
            st.markdown("### Strongest model calls")
            correct = reviews.loc[reviews["model_correct"]].sort_values("actual_result_probability", ascending=False).head(8)
            _render_table(
                correct,
                ["match", "predicted_result", "actual_result", "actual_result_probability"],
                {
                    "match": "Match",
                    "predicted_result": "Model call",
                    "actual_result": "Actual",
                    "actual_result_probability": "Model confidence",
                },
                percent_columns=["actual_result_probability"],
            )
            st.markdown("### Biggest model surprises")
            surprises = reviews.sort_values("actual_result_probability", ascending=True).head(8)
            _render_table(
                surprises,
                ["match", "predicted_result", "actual_result", "actual_result_probability"],
                {
                    "match": "Match",
                    "predicted_result": "Model call",
                    "actual_result": "Actual",
                    "actual_result_probability": "Actual-result probability",
                },
                percent_columns=["actual_result_probability"],
            )


def render_tournament_insights(prices: pd.DataFrame, tables: pd.DataFrame, movements: pd.DataFrame, path_status: pd.DataFrame, snapshots: pd.DataFrame | None = None, prediction_ledger: pd.DataFrame | None = None) -> None:
    prices = _prepare_prices(prices)
    tables = _prepare_tables(tables)
    snapshots = snapshots if isinstance(snapshots, pd.DataFrame) else pd.DataFrame()
    prediction_ledger = prediction_ledger if isinstance(prediction_ledger, pd.DataFrame) else pd.DataFrame()

    st.markdown("### What changed after the latest model run?")
    st.caption(f"Published model: {_timestamp(prices)}")
    st.info(_latest_event(movements))

    top_cards = st.columns(4)
    qualified = _qualifying_frame(prices)
    top_cards[0].metric("Reached Round of 32", len(qualified) if not qualified.empty else 0)
    top_cards[1].metric("Continents represented", qualified["continent"].nunique() if not qualified.empty else 0)
    if not tables.empty:
        top_cards[2].metric("Most goals by a team", int(tables["goals_for"].max()))
        top_cards[3].metric("Worst goals against", int(tables["goals_against"].max()))
    else:
        top_cards[2].metric("Most goals by a team", "—")
        top_cards[3].metric("Worst goals against", "—")

    _render_tournament_so_far(prices, snapshots, prediction_ledger)

    st.markdown("## Latest Model Run")
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

    st.markdown("### Teams that were on the group-stage edge")
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

    st.markdown("### Bracket path stories")
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
