from __future__ import annotations

import pandas as pd
import streamlit as st


RATING_BASE = 1500.0
PRICE_RATING_SCALE = 6.0
MATCH_CONFIDENCE_CAP = 6


def _num(value, default=0.0) -> float:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return float(default)
    return float(number)


def _confidence(matches_played: int, price_points: int) -> tuple[str, float]:
    match_score = min(max(matches_played, 0), MATCH_CONFIDENCE_CAP) / MATCH_CONFIDENCE_CAP
    history_score = min(max(price_points, 0), 8) / 8
    score = 0.7 * match_score + 0.3 * history_score
    if score >= 0.68:
        return "High", round(score, 2)
    if score >= 0.34:
        return "Medium", round(score, 2)
    return "Low", round(score, 2)


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
        away = str(row.get("away_team"))
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
        base_rating = RATING_BASE + PRICE_RATING_SCALE * opening_price
        live_rating = RATING_BASE + PRICE_RATING_SCALE * price
        rating_change = live_rating - base_rating
        mp = max(int(stats["matches_played"]), 1)
        attack_signal = stats["goals_for"] / mp
        defence_signal = stats["goals_against"] / mp
        points = 3 * stats["wins"] + stats["draws"]
        momentum_signal = points / (3 * mp)
        confidence_label, confidence_score = _confidence(int(stats["matches_played"]), price_points)
        direction = "improved" if rating_change > 1 else "weakened" if rating_change < -1 else "held steady"
        explanation = (
            f"{team} has {direction} by {rating_change:+.1f} rating points from the earliest stored market view. "
            f"The audit layer uses {stats['matches_played']} processed match(es), current market price, and stored price history."
        )
        rows.append({
            "team": team,
            "base_rating": round(base_rating, 1),
            "live_rating": round(live_rating, 1),
            "rating_change": round(rating_change, 1),
            "matches_played": int(stats["matches_played"]),
            "goals_for": int(stats["goals_for"]),
            "goals_against": int(stats["goals_against"]),
            "attack_signal": round(attack_signal, 2),
            "defence_signal": round(defence_signal, 2),
            "momentum_signal": round(momentum_signal, 2),
            "confidence_level": confidence_label,
            "confidence_score": confidence_score,
            "price_points": price_points,
            "explanation": explanation,
        })
    result = pd.DataFrame(rows)
    return result.sort_values("rating_change", ascending=False).reset_index(drop=True)


def render_country_learning(team: str, ratings: pd.DataFrame) -> None:
    st.markdown("### What the model has learned")
    st.caption("Phase 9A audit layer. This shows how CupMarket's belief has moved; it does not change prediction logic yet.")
    if not team or ratings.empty or "team" not in ratings.columns:
        st.info("Adaptive rating data is not available yet.")
        return
    rows = ratings.loc[ratings["team"].astype(str).eq(str(team))]
    if rows.empty:
        st.info("No adaptive rating row is available for this country yet.")
        return
    row = rows.iloc[0]
    cols = st.columns(4)
    cols[0].metric("Base rating", f"{row['base_rating']:.1f}")
    cols[1].metric("Live rating", f"{row['live_rating']:.1f}")
    cols[2].metric("Rating change", f"{row['rating_change']:+.1f}")
    cols[3].metric("Confidence", str(row["confidence_level"]))
    st.write(str(row["explanation"]))
    detail = pd.DataFrame([{ 
        "Matches": int(row["matches_played"]),
        "Goals for": int(row["goals_for"]),
        "Goals against": int(row["goals_against"]),
        "Attack signal": row["attack_signal"],
        "Defence signal": row["defence_signal"],
        "Momentum": row["momentum_signal"],
    }])
    st.dataframe(detail, hide_index=True, use_container_width=True)


def render_adaptive_ratings_insights(ratings: pd.DataFrame) -> None:
    st.markdown("## Adaptive Tournament Ratings")
    st.caption("Phase 9A visibility layer: shows what CupMarket has learned from stored tournament evidence before this signal is allowed to change predictions.")
    if ratings.empty:
        st.info("Adaptive ratings are not available yet.")
        return
    cols = st.columns(4)
    cols[0].metric("Teams tracked", len(ratings))
    cols[1].metric("Avg change", f"{ratings['rating_change'].mean():+.1f}")
    cols[2].metric("High confidence", int((ratings["confidence_level"] == "High").sum()))
    cols[3].metric("Matches used", int(ratings["matches_played"].sum()))
    tab1, tab2, tab3 = st.tabs(["Risers", "Fallers", "All teams"])
    columns = ["team", "base_rating", "live_rating", "rating_change", "matches_played", "attack_signal", "defence_signal", "momentum_signal", "confidence_level"]
    with tab1:
        st.dataframe(ratings.sort_values("rating_change", ascending=False)[columns].head(12), hide_index=True, use_container_width=True)
    with tab2:
        st.dataframe(ratings.sort_values("rating_change", ascending=True)[columns].head(12), hide_index=True, use_container_width=True)
    with tab3:
        st.dataframe(ratings[columns], hide_index=True, use_container_width=True)
    with st.expander("How to read this", expanded=False):
        st.write("Base rating comes from the earliest stored market view. Live rating comes from the latest market view. The match signals summarize tournament evidence from the processed ledger. Phase 9A is an audit layer only; predictions are not changed by these values yet.")
