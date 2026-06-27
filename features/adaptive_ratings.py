from __future__ import annotations

import pandas as pd
import streamlit as st

RATING_BASE = 1500.0
PRICE_RATING_SCALE = 6.0
MATCH_CONFIDENCE_CAP = 5
ATTACK_BASELINE = 1.25
DEFENCE_BASELINE = 1.25
MOMENTUM_BASELINE = 0.45


def _num(value, default=0.0) -> float:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return float(default)
    return float(number)


def _confidence(matches_played: int, price_points: int, context_penalty: float) -> tuple[str, float]:
    match_score = min(max(matches_played, 0), MATCH_CONFIDENCE_CAP) / MATCH_CONFIDENCE_CAP
    history_score = min(max(price_points, 0), 10) / 10
    raw = 0.68 * match_score + 0.32 * history_score - min(max(context_penalty, 0.0), 0.35)
    score = float(max(0.0, min(1.0, raw)))
    if score >= 0.7:
        return "High", round(score, 2)
    if score >= 0.38:
        return "Medium", round(score, 2)
    return "Low", round(score, 2)


def _risk_label(matches_played: int, goal_difference: int, confidence_score: float, context_penalty: float) -> str:
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
    stats = {"matches_played": 0, "goals_for": 0, "goals_against": 0, "wins": 0, "draws": 0, "losses": 0}
    if not isinstance(processed, pd.DataFrame) or processed.empty:
        return stats
    required = {"home_team", "away_team", "home_score", "away_score"}
    if not required.issubset(processed.columns):
        return stats
    games = processed.loc[processed["home_team"].astype(str).eq(team) | processed["away_team"].astype(str).eq(team)].copy()
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
    direction = "improved" if change > 1 else "weakened" if change < -1 else "held steady"
    reasons = []
    if attack > ATTACK_BASELINE + 0.35:
        reasons.append("attack output is above the tournament baseline")
    if defence < DEFENCE_BASELINE - 0.25:
        reasons.append("defence has allowed fewer goals than baseline")
    if momentum > MOMENTUM_BASELINE + 0.18:
        reasons.append("results momentum is strong")
    if not reasons:
        reasons.append("the stored market and match signals are still mixed")
    return f"{team} has {direction} by {change:+.1f} rating points. Main read: {', '.join(reasons)}. Risk flag: {risk}."


def build_adaptive_ratings(prices: pd.DataFrame, history: pd.DataFrame, processed: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(prices, pd.DataFrame) or prices.empty or "team" not in prices.columns:
        return pd.DataFrame()
    frame = prices.copy()
    for column in ["cupmarket_price", "previous_price", "prob_champion", "prob_reach_round_32"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    history_counts = pd.DataFrame(columns=["team", "price_points", "opening_price"])
    if isinstance(history, pd.DataFrame) and not history.empty and {"team", "cupmarket_price"}.issubset(history.columns):
        hist = history.copy()
        hist["generated_at_utc"] = pd.to_datetime(hist.get("generated_at_utc"), errors="coerce", utc=True)
        hist["cupmarket_price"] = pd.to_numeric(hist["cupmarket_price"], errors="coerce")
        hist = hist.dropna(subset=["team", "cupmarket_price"])
        if not hist.empty:
            opening = hist.sort_values("generated_at_utc").groupby("team", as_index=False).first()[["team", "cupmarket_price"]].rename(columns={"cupmarket_price": "opening_price"})
            counts = hist.groupby("team").size().reset_index(name="price_points")
            history_counts = counts.merge(opening, on="team", how="left")
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
        confidence_label, confidence_score = _confidence(int(stats["matches_played"]), price_points, context_penalty)
        risk_label = _risk_label(int(stats["matches_played"]), goal_difference, confidence_score, context_penalty)
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
        }
        item["explanation"] = _learning_summary(pd.Series(item))
        rows.append(item)
    result = pd.DataFrame(rows)
    return result.sort_values("rating_change", ascending=False).reset_index(drop=True)


def render_country_learning(team: str, ratings: pd.DataFrame) -> None:
    st.markdown("### What CupMarket has learned")
    st.caption("A simple audit view. It explains how the team's rating has moved, but it does not change predictions yet.")
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
        detail = pd.DataFrame([{
            "Matches": int(row["matches_played"]),
            "Goals for": int(row["goals_for"]),
            "Goals against": int(row["goals_against"]),
            "Market signal": row["market_signal"],
            "Match signal": row["match_signal"],
            "Context penalty": row["context_penalty"],
            "Risk": row["overreaction_risk"],
        }])
        st.dataframe(detail, hide_index=True, use_container_width=True)
        st.caption("Phase 9B can later use these signals in predictions only after the audit layer looks sensible.")


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
    st.caption("Phase 9A shows what CupMarket thinks it has learned. It supports trust; it does not change predictions yet.")
    if ratings.empty:
        st.info("Adaptive ratings are not available yet.")
        return
    riser = ratings.sort_values("rating_change", ascending=False).iloc[0] if not ratings.empty else None
    faller = ratings.sort_values("rating_change", ascending=True).iloc[0] if not ratings.empty else None
    risky = ratings.loc[ratings["overreaction_risk"].isin(["High sample risk", "Context risk", "Possible overreaction"])]
    risky_row = risky.sort_values("confidence_score", ascending=True).iloc[0] if not risky.empty else None
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
    columns = ["team", "rating_change", "market_signal", "match_signal", "attack_signal", "defence_signal", "momentum_signal", "overreaction_risk", "confidence_level"]
    with tab1:
        st.dataframe(ratings.sort_values("match_signal", ascending=False)[columns].head(16), hide_index=True, use_container_width=True)
    with tab2:
        st.dataframe(ratings.sort_values("rating_change", ascending=False)[columns].head(16), hide_index=True, use_container_width=True)
    with tab3:
        st.dataframe(ratings.sort_values("rating_change", ascending=True)[columns].head(16), hide_index=True, use_container_width=True)
    with tab4:
        st.dataframe(ratings[columns], hide_index=True, use_container_width=True)
    with st.expander("How this prepares Phase 9B", expanded=False):
        st.write("Phase 9B can blend these audited signals into future match predictions. The risk flags and confidence scores are guardrails, so one strange match does not distort the model too much.")
