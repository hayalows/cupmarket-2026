from __future__ import annotations

import pandas as pd
import streamlit as st

from features.tournament_path_data import round_of_16_build
from features.tournament_path_data import stage_label, status_label


STAGE_ALIASES = {
    "Round of 32": ["ROUND_OF_32", "LAST_32", "R32"],
    "Round of 16": ["ROUND_OF_16", "LAST_16", "R16"],
    "Quarter-finals": ["QUARTER_FINALS", "QUARTER_FINAL", "QF"],
    "Semi-finals": ["SEMI_FINALS", "SEMI_FINAL", "SF"],
    "Final": ["FINAL"],
}

STAGE_FORECAST_COLUMNS = {
    "Round of 32": "prob_reach_round_32",
    "Round of 16": "prob_reach_round_16",
    "Quarter-finals": "prob_reach_quarter_final",
    "Semi-finals": "prob_reach_semi_final",
    "Final": "prob_reach_final",
}


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


def _clean_team(value) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "null", "tbd"}:
        return "TBD"
    return text


def _score(row: pd.Series) -> str:
    home = pd.to_numeric(row.get("home_score"), errors="coerce")
    away = pd.to_numeric(row.get("away_score"), errors="coerce")
    if pd.isna(home) or pd.isna(away):
        return "vs"
    return f"{int(home)}–{int(away)}"


def _card(label: str, title: str, body: str, footer: str = "") -> None:
    footer_html = f"<span>{footer}</span>" if footer else ""
    st.markdown(
        f'''
        <div class="cm-project-card">
            <div class="cm-project-label">{label}</div>
            <strong>{title}</strong>
            <p>{body}</p>
            {footer_html}
        </div>
        ''',
        unsafe_allow_html=True,
    )


def _confirmed_source(data: dict) -> pd.DataFrame:
    progress = data.get("progress", pd.DataFrame())
    bracket = data.get("bracket", pd.DataFrame())
    if isinstance(progress, pd.DataFrame) and not progress.empty:
        return progress.copy()
    if isinstance(bracket, pd.DataFrame) and not bracket.empty:
        return bracket.copy()
    return pd.DataFrame()


def _top_opponent(opponents: pd.DataFrame, team: str) -> tuple[str, float | None]:
    if opponents.empty or not {"team", "opponent"}.issubset(opponents.columns):
        return "TBD", None
    rows = opponents.loc[opponents["team"].astype(str) == str(team)].copy()
    if rows.empty:
        return "TBD", None
    probability_column = (
        "probability_given_qualification"
        if "probability_given_qualification" in rows.columns
        else "probability_unconditional"
    )
    probability = None
    if probability_column in rows.columns:
        rows[probability_column] = pd.to_numeric(rows[probability_column], errors="coerce")
        rows = rows.sort_values(probability_column, ascending=False)
        probability = rows.iloc[0].get(probability_column)
    return _clean_team(rows.iloc[0].get("opponent")), probability


def _price_lookup(prices: pd.DataFrame) -> dict[str, dict]:
    if prices.empty or "team" not in prices.columns:
        return {}
    lookup = {}
    for row in prices.itertuples(index=False):
        values = row._asdict()
        lookup[str(values.get("team"))] = values
    return lookup


def _projected_round32(data: dict) -> pd.DataFrame:
    path_status = data.get("path_status", pd.DataFrame())
    opponents = data.get("opponents", pd.DataFrame())
    prices = data.get("prices", pd.DataFrame())
    if not isinstance(path_status, pd.DataFrame) or path_status.empty or "team" not in path_status.columns:
        return pd.DataFrame()

    prices_by_team = _price_lookup(prices if isinstance(prices, pd.DataFrame) else pd.DataFrame())
    rows = []
    seen = set()

    for row in path_status.itertuples(index=False):
        values = row._asdict()
        team = _clean_team(values.get("team"))
        if team == "TBD":
            continue
        fixture_status = str(values.get("fixture_status") or "projected")
        if fixture_status == "eliminated":
            continue

        opponent = _clean_team(values.get("most_likely_opponent"))
        opponent_probability = values.get("most_likely_opponent_probability")
        if opponent == "TBD":
            opponent, opponent_probability = _top_opponent(opponents, team)

        pair_key = tuple(sorted([team, opponent])) if opponent != "TBD" else (team, "TBD")
        if pair_key in seen:
            continue
        seen.add(pair_key)

        price_row = prices_by_team.get(team, {})
        reach_probability = values.get("prob_reach_round_32") or price_row.get("prob_reach_round_32")
        slot = values.get("confirmed_slot") or values.get("projected_slot") or values.get("slot")
        if not slot:
            slot = "Projected Round-of-32 slot"

        if fixture_status == "confirmed":
            state = "Confirmed"
        elif "confirmed" in fixture_status:
            state = "Part-confirmed"
        else:
            state = "Projected"

        rows.append(
            {
                "team": team,
                "opponent": opponent,
                "slot": slot,
                "state": state,
                "reach_probability": pd.to_numeric(reach_probability, errors="coerce"),
                "opponent_probability": pd.to_numeric(opponent_probability, errors="coerce"),
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(
        ["state", "reach_probability"],
        ascending=[True, False],
        na_position="last",
    ).reset_index(drop=True)


def _render_confirmed_cards(source: pd.DataFrame, stage_name: str, limit: int = 8) -> bool:
    if source.empty or "stage" not in source.columns:
        return False
    if stage_name == "Round of 16":
        slots = round_of_16_build(source)
        if not slots.empty:
            for _, row in slots.head(limit).iterrows():
                _card(
                    f"Round of 16 - Match {int(row['match_number'])}",
                    str(row["fixture"]),
                    f"{row['state']} - {_timestamp(row.get('kickoff_utc'))}",
                    "Built from Round-of-32 winners",
                )
            return True
    aliases = STAGE_ALIASES.get(stage_name, [])
    rows = source.loc[source["stage"].astype(str).isin(aliases)].copy()
    if rows.empty:
        return False
    if "utc_date" in rows.columns:
        rows["utc_date"] = pd.to_datetime(rows["utc_date"], errors="coerce", utc=True)
        rows = rows.sort_values("utc_date", na_position="last")
    for index, row in rows.head(limit).iterrows():
        home = _clean_team(row.get("home_team"))
        away = _clean_team(row.get("away_team"))
        match_number = row.get("logical_match_number") or row.get("bracket_match_number") or index + 1
        status = str(row.get("status") or "Pending").replace("_", " ").title()
        advancing = _clean_team(row.get("advancing_team"))
        footer = "Confirmed fixture" if home != "TBD" and away != "TBD" else "Waiting for teams"
        if advancing != "TBD":
            footer = f"Result fixed · Advanced: {advancing}"
        _card(
            f"{stage_name} · Match {match_number}",
            f"{home} {_score(row)} {away}",
            f"{status} · {_timestamp(row.get('utc_date'))}",
            footer,
        )
    return True


def _render_projected_r32(projected: pd.DataFrame, limit: int = 16) -> bool:
    if projected.empty:
        return False
    for index, row in projected.head(limit).iterrows():
        reach = _percent(row.get("reach_probability"))
        opponent_chance = _percent(row.get("opponent_probability"))
        footer = f"Team reach chance: {reach}"
        if opponent_chance != "—":
            footer += f" · Opponent chance: {opponent_chance}"
        _card(
            f"Round of 32 · {row.get('state')}",
            f"{row.get('team')} vs {row.get('opponent')}",
            str(row.get("slot") or f"Projected slot {index + 1}"),
            footer,
        )
    return True


def _render_stage_forecast(prices: pd.DataFrame, stage_name: str, limit: int = 6) -> bool:
    probability_column = STAGE_FORECAST_COLUMNS.get(stage_name)
    if not probability_column or prices.empty or not {"team", probability_column}.issubset(prices.columns):
        return False
    rows = prices[["team", probability_column]].copy()
    rows[probability_column] = pd.to_numeric(rows[probability_column], errors="coerce")
    rows = rows.dropna(subset=[probability_column]).sort_values(probability_column, ascending=False).head(limit)
    if rows.empty:
        return False
    for _, row in rows.iterrows():
        _card(
            f"{stage_name} · Forecast",
            str(row["team"]),
            f"Reach chance: {_percent(row[probability_column])}",
            "Exact pairing updates after the model publishes a locked path.",
        )
    return True


def render_dynamic_bracket_view(data: dict) -> None:
    st.markdown("### Full bracket view")
    st.caption(
        "Confirmed fixtures come from the official knockout feed. Projected fixtures come "
        "from the latest CupMarket model run and update after the next successful publication."
    )

    source = _confirmed_source(data)
    projected_r32 = _projected_round32(data)
    prices = data.get("prices", pd.DataFrame())
    if not isinstance(prices, pd.DataFrame):
        prices = pd.DataFrame()

    mode = st.radio(
        "Bracket mode",
        ["Confirmed + projected", "Confirmed only", "Projected only"],
        horizontal=True,
        key="cupmarket_bracket_mode",
    )

    columns = st.columns(5)
    for column, stage_name in zip(columns, STAGE_ALIASES.keys()):
        with column:
            st.markdown(f"#### {stage_name}")
            rendered = False
            if mode != "Projected only":
                rendered = _render_confirmed_cards(source, stage_name)
            if not rendered and mode != "Confirmed only":
                if stage_name == "Round of 32":
                    rendered = _render_projected_r32(projected_r32)
                else:
                    rendered = _render_stage_forecast(prices, stage_name)
            if not rendered:
                st.caption("Waiting for bracket data.")

    with st.expander("How to read the bracket view", expanded=False):
        st.markdown(
            "**Confirmed** means the fixture exists in the official knockout feed.\n\n"
            "**Part-confirmed** means one country or slot is known, but the other side still depends on remaining results.\n\n"
            "**Projected** means CupMarket is showing the model's current most likely matchup.\n\n"
            "Later rounds show the strongest projected stage paths until exact pairings become available."
        )
