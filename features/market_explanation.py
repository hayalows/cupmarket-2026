"""Plain-language country-market explanations built from published outputs."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def _number(value) -> float | None:
    number = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(number) else float(number)


def _percent(value) -> str:
    number = _number(value)
    return "Unavailable" if number is None else f"{100 * number:.1f}%"


def _time(value) -> str:
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    return "Unavailable" if pd.isna(timestamp) else timestamp.strftime("%d %b %Y · %H:%M UTC")


def _bracket_note(team: str, progress: pd.DataFrame, price: pd.Series) -> str:
    if bool(price.get("is_eliminated", False)):
        return "This country is out, so its bracket path is now locked at the settlement stage."
    if progress.empty:
        return "The official bracket path is not available yet."
    rows = progress.loc[
        progress.get("home_team", pd.Series(dtype=str)).astype(str).eq(team)
        | progress.get("away_team", pd.Series(dtype=str)).astype(str).eq(team)
    ].copy()
    if rows.empty:
        return "The model is carrying the route forward until an official fixture is populated."
    upcoming = rows.loc[rows.get("status", pd.Series(dtype=str)).astype(str).isin({"TIMED", "SCHEDULED"})]
    fixture = upcoming.iloc[0] if not upcoming.empty else rows.iloc[-1]
    home = str(fixture.get("home_team") or "TBD")
    away = str(fixture.get("away_team") or "TBD")
    stage = str(fixture.get("stage") or "Tournament").replace("_", " ").title()
    return f"{stage}: {home} vs {away}."


def render_market_explanation(
    *,
    team: str,
    price: pd.Series,
    movement: pd.Series,
    progress: pd.DataFrame,
    adaptive_ratings: pd.DataFrame,
    manifest: dict,
) -> None:
    """Render the six causal inputs users need to interpret a country price."""
    with st.expander("Why this moved", expanded=False):
        trigger = str(movement.get("trigger_matches") or "") if not movement.empty else ""
        scope = str(movement.get("attribution_scope") or "") if not movement.empty else ""
        result_text = trigger or "No newly completed result was attached to this publication."
        if scope == "publication_refresh":
            result_text = "Official knockout model refresh. The move reflects the full updated path, not one isolated match."

        columns = st.columns(3)
        columns[0].metric("Current CM value", f"{_number(price.get('cupmarket_price')) or 0:.2f}")
        columns[1].metric("Champion chance", _percent(price.get("prob_champion")))
        delta = _number(movement.get("champion_probability_change")) if not movement.empty else None
        columns[2].metric("Title chance move", "Unavailable" if delta is None else f"{100 * delta:+.1f} pp")

        st.markdown("**Result or publication**")
        st.write(result_text)
        st.markdown("**Bracket path**")
        st.write(_bracket_note(team, progress, price))

        settlement_value = _number(price.get("adjusted_settlement_value"))
        if settlement_value is None:
            settlement = "Still active: CM value is the simulation's expected settlement value."
        else:
            floor = _number(price.get("exit_stage_floor")) or 0.0
            premium = _number(price.get("performance_premium")) or 0.0
            settlement = f"Settlement locked at {settlement_value:.2f} CM: floor {floor:.2f} plus {premium:.2f} performance premium."
        st.markdown("**Settlement effect**")
        st.write(settlement)

        adaptive_row = adaptive_ratings.loc[
            adaptive_ratings.get("team", pd.Series(dtype=str)).astype(str).eq(team)
        ] if not adaptive_ratings.empty else pd.DataFrame()
        if adaptive_row.empty:
            adaptive_text = "No adaptive rating row is available for this publication."
        else:
            row = adaptive_row.iloc[0]
            adaptive_text = (
                f"Rating change {(_number(row.get('rating_change')) or 0):+.1f}; "
                f"match signal {(_number(row.get('match_signal')) or 0):+.1f}; "
                f"guardrail {str(row.get('guardrail_decision') or 'collecting evidence').replace('_', ' ')}."
            )
        st.markdown("**Adaptive signal**")
        st.write(adaptive_text)

        publication = manifest.get("publication", {}) if isinstance(manifest, dict) else {}
        st.caption(
            "Published source: "
            + _time(publication.get("model_generated_at_utc"))
            + " · checked "
            + _time(publication.get("last_checked_at_utc"))
        )
