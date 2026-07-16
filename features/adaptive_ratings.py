from __future__ import annotations

import numpy as np
import pandas as pd

try:
    import streamlit as st
except ImportError:  # Backend-only jobs should still use the adjustment helpers.
    st = None


RATING_BASE = 1500.0
PRICE_RATING_SCALE = 6.0
MATCH_CONFIDENCE_CAP = 5
ATTACK_BASELINE = 1.25
DEFENCE_BASELINE = 1.25
MOMENTUM_BASELINE = 0.45

ADAPTIVE_MODEL_VERSION = "phase9b_adaptive_prediction_v1"
MAX_ADAPTIVE_ELO_ADJUSTMENT = 25.0

CONFIDENCE_MULTIPLIERS = {
    "low": 0.15,
    "medium": 0.30,
    "high": 0.45,
}
RISK_MULTIPLIERS = {
    "stable signal": 1.00,
    "normal watch": 0.80,
    "high sample risk": 0.45,
    "context risk": 0.45,
    "possible overreaction": 0.55,
}
STAGE_MULTIPLIERS = {
    "group_stage": 0.75,
    "round_32": 1.00,
    "round_16": 1.05,
    "quarter_final": 1.10,
    "semi_final": 1.15,
    "final": 1.20,
}
STAGE_ALIASES = {
    "GROUP_STAGE": "group_stage",
    "LAST_32": "round_32",
    "ROUND_OF_32": "round_32",
    "R32": "round_32",
    "LAST_16": "round_16",
    "ROUND_OF_16": "round_16",
    "R16": "round_16",
    "QUARTER_FINALS": "quarter_final",
    "QUARTER_FINAL": "quarter_final",
    "QF": "quarter_final",
    "SEMI_FINALS": "semi_final",
    "SEMI_FINAL": "semi_final",
    "SF": "semi_final",
    "FINAL": "final",
}


def _num(value, default=0.0) -> float:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return float(default)
    return float(number)


def _text_key(value) -> str:
    return str(value or "").strip().lower().replace("_", " ")


def _confidence(
    matches_played: int,
    price_points: int,
    context_penalty: float,
) -> tuple[str, float]:
    match_score = min(max(matches_played, 0), MATCH_CONFIDENCE_CAP) / MATCH_CONFIDENCE_CAP
    history_score = min(max(price_points, 0), 10) / 10
    raw = 0.68 * match_score + 0.32 * history_score - min(max(context_penalty, 0.0), 0.35)
    score = float(max(0.0, min(1.0, raw)))
    if score >= 0.7:
        return "High", round(score, 2)
    if score >= 0.38:
        return "Medium", round(score, 2)
    return "Low", round(score, 2)


def _risk_label(
    matches_played: int,
    goal_difference: int,
    confidence_score: float,
    context_penalty: float,
) -> str:
    if matches_played <= 1:
        return "High sample risk"
    if context_penalty >= 0.2:
        return "Context risk"
    if abs(goal_difference) >= 5 and confidence_score < 0.55:
        return "Possible overreaction"
    if confidence_score >= 0.7:
        return "Stable signal"
    return "Normal watch"


def _team_match_stats(team: str, processed: pd.DataFrame) -> dict[str, float]:
    stats = {
        "matches_played": 0,
        "goals_for": 0,
        "goals_against": 0,
        "wins": 0,
        "draws": 0,
        "losses": 0,
    }
    if not isinstance(processed, pd.DataFrame) or processed.empty:
        return stats
    required = {"home_team", "away_team", "home_score", "away_score"}
    if not required.issubset(processed.columns):
        return stats
    games = processed.loc[
        processed["home_team"].astype(str).eq(team)
        | processed["away_team"].astype(str).eq(team)
    ].copy()
    if games.empty:
        return stats
    for _, row in games.iterrows():
        home = str(row.get("home_team"))
        hs = pd.to_numeric(row.get("home_score"), errors="coerce")
        aw = pd.to_numeric(row.get("away_score"), errors="coerce")
        if pd.isna(hs) or pd.isna(aw):
            continue
        gf = int(hs) if home == team else int(aw)
        ga = int(aw) if home == team else int(hs)
        stats["matches_played"] += 1
        stats["goals_for"] += gf
        stats["goals_against"] += ga
        if gf > ga:
            stats["wins"] += 1
        elif gf == ga:
            stats["draws"] += 1
        else:
            stats["losses"] += 1
    return stats


def _learning_summary(row: pd.Series) -> str:
    team = str(row["team"])
    change = float(row["rating_change"])
    attack = float(row["attack_signal"])
    defence = float(row["defence_signal"])
    momentum = float(row["momentum_signal"])
    risk = str(row["overreaction_risk"])
    direction = (
        "improved"
        if change > 1
        else "weakened"
        if change < -1
        else "held steady"
    )
    reasons = []
    if attack > ATTACK_BASELINE + 0.35:
        reasons.append("attack output is above the tournament baseline")
    if defence < DEFENCE_BASELINE - 0.25:
        reasons.append("defence has allowed fewer goals than baseline")
    if momentum > MOMENTUM_BASELINE + 0.18:
        reasons.append("results momentum is strong")
    if not reasons:
        reasons.append("the stored market and match signals are still mixed")
    return (
        f"{team} has {direction} by {change:+.1f} rating points. "
        f"Main read: {', '.join(reasons)}. Risk flag: {risk}."
    )


def build_adaptive_ratings(
    prices: pd.DataFrame,
    history: pd.DataFrame,
    processed: pd.DataFrame,
    guardrail_state: dict | None = None,
) -> pd.DataFrame:
    if not isinstance(prices, pd.DataFrame) or prices.empty or "team" not in prices.columns:
        return pd.DataFrame()
    frame = prices.copy()
    for column in [
        "cupmarket_price",
        "previous_price",
        "prob_champion",
        "prob_reach_round_32",
    ]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    history_counts = pd.DataFrame(columns=["team", "price_points", "opening_price"])
    if (
        isinstance(history, pd.DataFrame)
        and not history.empty
        and {"team", "cupmarket_price"}.issubset(history.columns)
    ):
        hist = history.copy()
        hist["generated_at_utc"] = pd.to_datetime(
            hist.get("generated_at_utc"),
            errors="coerce",
            utc=True,
        )
        hist["cupmarket_price"] = pd.to_numeric(
            hist["cupmarket_price"],
            errors="coerce",
        )
        hist = hist.dropna(subset=["team", "cupmarket_price"])
        if not hist.empty:
            opening = (
                hist.sort_values("generated_at_utc")
                .groupby("team", as_index=False)
                .first()[["team", "cupmarket_price"]]
                .rename(columns={"cupmarket_price": "opening_price"})
            )
            counts = hist.groupby("team").size().reset_index(name="price_points")
            history_counts = counts.merge(opening, on="team", how="left")
    guardrail_state = guardrail_state or {}
    guardrail_decision = str(guardrail_state.get("decision") or "collecting_evidence")
    rows = []
    for _, row in frame.iterrows():
        team = str(row.get("team"))
        price = _num(row.get("cupmarket_price"), 0.0)
        hist_row = history_counts.loc[history_counts["team"].astype(str).eq(team)]
        price_points = int(hist_row["price_points"].iloc[0]) if not hist_row.empty else 1
        opening_price = _num(hist_row["opening_price"].iloc[0], price) if not hist_row.empty else price
        stats = _team_match_stats(team, processed)
        mp = max(int(stats["matches_played"]), 1)
        attack_signal = stats["goals_for"] / mp
        defence_signal = stats["goals_against"] / mp
        goal_difference = int(stats["goals_for"] - stats["goals_against"])
        points = 3 * stats["wins"] + stats["draws"]
        momentum_signal = points / (3 * mp)
        attack_component = (attack_signal - ATTACK_BASELINE) * 9.0
        defence_component = (DEFENCE_BASELINE - defence_signal) * 8.0
        momentum_component = (momentum_signal - MOMENTUM_BASELINE) * 14.0
        market_component = (price - opening_price) * PRICE_RATING_SCALE
        raw_match_signal = attack_component + defence_component + momentum_component
        context_penalty = 0.0
        if stats["matches_played"] <= 1:
            context_penalty += 0.18
        if abs(goal_difference) >= 5 and stats["matches_played"] <= 3:
            context_penalty += 0.18
        capped_match_signal = max(-24.0, min(24.0, raw_match_signal))
        adaptive_change = 0.55 * market_component + 0.45 * capped_match_signal
        base_rating = RATING_BASE + PRICE_RATING_SCALE * opening_price
        live_rating = base_rating + adaptive_change
        confidence_label, confidence_score = _confidence(
            int(stats["matches_played"]),
            price_points,
            context_penalty,
        )
        risk_label = _risk_label(
            int(stats["matches_played"]),
            goal_difference,
            confidence_score,
            context_penalty,
        )
        item = {
            "team": team,
            "base_rating": round(base_rating, 1),
            "live_rating": round(live_rating, 1),
            "adaptive_rating": round(live_rating, 1),
            "rating_change": round(adaptive_change, 1),
            "market_signal": round(market_component, 1),
            "match_signal": round(capped_match_signal, 1),
            "attack_signal": round(attack_signal, 2),
            "defence_signal": round(defence_signal, 2),
            "momentum_signal": round(momentum_signal, 2),
            "context_penalty": round(context_penalty, 2),
            "overreaction_risk": risk_label,
            "confidence_level": confidence_label,
            "confidence_score": confidence_score,
            "matches_played": int(stats["matches_played"]),
            "goals_for": int(stats["goals_for"]),
            "goals_against": int(stats["goals_against"]),
            "goal_difference": goal_difference,
            "price_points": price_points,
            "adaptive_model_version": ADAPTIVE_MODEL_VERSION,
            "guardrail_decision": guardrail_decision,
        }
        item["explanation"] = _learning_summary(pd.Series(item))
        rows.append(item)
    result = pd.DataFrame(rows)
    return result.sort_values("rating_change", ascending=False).reset_index(drop=True)


def stage_key(stage) -> str:
    return STAGE_ALIASES.get(str(stage or "").upper(), "group_stage")


def stage_multiplier(stage) -> float:
    return STAGE_MULTIPLIERS.get(stage_key(stage), 1.0)


def confidence_level_from_score(score) -> str:
    value = _num(score, default=np.nan)
    if pd.isna(value):
        return "Low"
    if value >= 0.70:
        return "High"
    if value >= 0.45:
        return "Medium"
    return "Low"


def confidence_multiplier(row: pd.Series) -> float:
    label = _text_key(row.get("confidence_level"))
    if label not in CONFIDENCE_MULTIPLIERS:
        label = confidence_level_from_score(row.get("confidence_score")).lower()
    return CONFIDENCE_MULTIPLIERS.get(label, CONFIDENCE_MULTIPLIERS["low"])


def risk_multiplier(row: pd.Series) -> float:
    label = _text_key(row.get("overreaction_risk"))
    if label not in RISK_MULTIPLIERS:
        label = "normal watch"
    return RISK_MULTIPLIERS[label]


def cap_adjustment(value: float) -> float:
    return float(
        np.clip(
            value,
            -MAX_ADAPTIVE_ELO_ADJUSTMENT,
            MAX_ADAPTIVE_ELO_ADJUSTMENT,
        )
    )


def adaptive_rating_adjustment(
    team: str,
    adaptive_rating_frame: pd.DataFrame | None,
    stage=None,
) -> float:
    if (
        adaptive_rating_frame is None
        or adaptive_rating_frame.empty
        or "team" not in adaptive_rating_frame
    ):
        return 0.0
    matches = adaptive_rating_frame.loc[
        adaptive_rating_frame["team"].astype(str) == str(team)
    ]
    if matches.empty:
        return 0.0
    row = matches.iloc[-1]
    guardrail_decision = str(
        row.get("guardrail_decision") or "collecting_evidence"
    ).lower()
    if guardrail_decision not in {"monitor", "trusted"}:
        return 0.0
    raw_adjustment = _num(row.get("rating_change"), default=0.0)
    if raw_adjustment == 0.0:
        return 0.0
    final_adjustment = (
        raw_adjustment
        * confidence_multiplier(row)
        * risk_multiplier(row)
        * stage_multiplier(stage)
    )
    return cap_adjustment(final_adjustment)


def adaptive_adjustment_detail(
    team: str,
    adaptive_rating_frame: pd.DataFrame | None,
    stage=None,
) -> dict:
    adjustment = adaptive_rating_adjustment(team, adaptive_rating_frame, stage)
    row = pd.Series(dtype=object)
    if (
        adaptive_rating_frame is not None
        and not adaptive_rating_frame.empty
        and "team" in adaptive_rating_frame
    ):
        rows = adaptive_rating_frame.loc[
            adaptive_rating_frame["team"].astype(str) == str(team)
        ]
        if not rows.empty:
            row = rows.iloc[-1]
    return {
        "team": str(team),
        "adaptive_adjustment": adjustment,
        "rating_change": _num(row.get("rating_change"), default=0.0),
        "confidence_level": row.get("confidence_level", "Low"),
        "confidence_multiplier": confidence_multiplier(row),
        "overreaction_risk": row.get("overreaction_risk", "Normal watch"),
        "risk_multiplier": risk_multiplier(row),
        "stage_multiplier": stage_multiplier(stage),
        "adaptive_model_version": ADAPTIVE_MODEL_VERSION,
    }


def render_country_learning(team: str, ratings: pd.DataFrame) -> None:
    st.markdown("### What CupMarket has learned")
    st.caption(
        "A simple audit view. It explains how the team's rating has moved, "
        "while Phase 9B applies only a small capped nudge to predictions."
    )
    if not team or ratings.empty or "team" not in ratings.columns:
        st.info("Adaptive rating data is not available yet.")
        return
    rows = ratings.loc[ratings["team"].astype(str).eq(str(team))]
    if rows.empty:
        st.info("No adaptive rating row is available for this country yet.")
        return
    row = rows.iloc[0]
    cols = st.columns(4)
    cols[0].metric("Base", f"{row['base_rating']:.1f}")
    cols[1].metric("Now", f"{row['adaptive_rating']:.1f}")
    cols[2].metric("Move", f"{row['rating_change']:+.1f}")
    cols[3].metric("Trust", str(row["confidence_level"]))
    st.info(str(row["explanation"]))
    with st.expander("See the evidence", expanded=False):
        detail = pd.DataFrame(
            [
                {
                    "Matches": int(row["matches_played"]),
                    "Goals for": int(row["goals_for"]),
                    "Goals against": int(row["goals_against"]),
                    "Market signal": row["market_signal"],
                    "Match signal": row["match_signal"],
                    "Context penalty": row["context_penalty"],
                    "Risk": row["overreaction_risk"],
                }
            ]
        )
        st.dataframe(detail, hide_index=True, width="stretch")
        st.caption(
            "Phase 9B uses this audited row only through capped, "
            "confidence-weighted prediction Elo adjustments."
        )


def _story_card(title: str, row: pd.Series | None) -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        if row is None:
            st.caption("No data yet.")
            return
        st.metric(str(row["team"]), f"{row['rating_change']:+.1f}")
        st.caption(str(row["explanation"]))


def render_adaptive_ratings_insights(ratings: pd.DataFrame) -> None:
    st.markdown("## Adaptive Tournament Ratings")
    st.caption(
        "Phase 9A shows what CupMarket thinks it has learned. Phase 9B "
        "uses these signals as a capped prediction nudge, not as a new model."
    )
    if ratings.empty:
        st.info("Adaptive ratings are not available yet.")
        return
    riser = ratings.sort_values("rating_change", ascending=False).iloc[0]
    faller = ratings.sort_values("rating_change", ascending=True).iloc[0]
    risky = ratings.loc[
        ratings["overreaction_risk"].isin(
            ["High sample risk", "Context risk", "Possible overreaction"]
        )
    ]
    risky_row = (
        risky.sort_values("confidence_score", ascending=True).iloc[0]
        if not risky.empty
        else None
    )
    cols = st.columns(4)
    cols[0].metric("Teams tracked", len(ratings))
    cols[1].metric("Avg move", f"{ratings['rating_change'].mean():+.1f}")
    cols[2].metric("High trust", int((ratings["confidence_level"] == "High").sum()))
    cols[3].metric("Risk flags", len(risky))
    st.markdown("### What changed most")
    story_cols = st.columns(3)
    with story_cols[0]:
        _story_card("Biggest improver", riser)
    with story_cols[1]:
        _story_card("Biggest drop", faller)
    with story_cols[2]:
        _story_card("Needs caution", risky_row)
    tab1, tab2, tab3, tab4 = st.tabs(["Signals", "Risers", "Fallers", "All teams"])
    columns = [
        "team",
        "rating_change",
        "market_signal",
        "match_signal",
        "attack_signal",
        "defence_signal",
        "momentum_signal",
        "overreaction_risk",
        "confidence_level",
    ]
    with tab1:
        st.dataframe(
            ratings.sort_values("match_signal", ascending=False)[columns].head(16),
            hide_index=True,
            width="stretch",
        )
    with tab2:
        st.dataframe(
            ratings.sort_values("rating_change", ascending=False)[columns].head(16),
            hide_index=True,
            width="stretch",
        )
    with tab3:
        st.dataframe(
            ratings.sort_values("rating_change", ascending=True)[columns].head(16),
            hide_index=True,
            width="stretch",
        )
    with tab4:
        st.dataframe(ratings[columns], hide_index=True, width="stretch")
    with st.expander("How Phase 9B uses this", expanded=False):
        st.write(
            "Future predictions still come from the trained goal models and live Elo. "
            "Phase 9B converts the audited rating change into a small Elo-style "
            "adjustment using confidence, risk, and stage multipliers, then caps "
            "the result at +/-25 Elo."
        )
