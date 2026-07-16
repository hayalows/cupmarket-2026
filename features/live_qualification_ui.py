from __future__ import annotations

import pandas as pd
import streamlit as st

from backend.live_knockout import (
    is_live_knockout_match,
    run_live_knockout_projection,
)
from backend.live_qualification import LIVE_STATUSES, build_provisional_snapshot, next_goal_impacts, run_live_qualification_projection


def pct(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{100 * float(value):.1f}%"


@st.cache_data(ttl=60, show_spinner=False)
def cached_projection(matches, predictions, strength_items, selected_team, simulations=1400):
    return run_live_qualification_projection(
        matches,
        predictions,
        strength=dict(strength_items),
        selected_team=selected_team,
        n_simulations=simulations,
        random_seed=2026,
    )


@st.cache_data(ttl=60, show_spinner=False)
def cached_knockout_projection(matches, predictions, match_id, simulations=2600):
    return run_live_knockout_projection(
        matches,
        predictions,
        match_id=int(match_id),
        n_simulations=simulations,
        random_seed=2026,
    )


def _group(matches, team):
    frame = matches[(matches["stage"] == "GROUP_STAGE") & ((matches["home_team"] == team) | (matches["away_team"] == team))]
    return None if frame.empty else str(frame.iloc[0]["group"]).replace("GROUP_", "")


def _table(rows):
    frame = pd.DataFrame(rows)
    if frame.empty:
        return
    cols = ["position", "team", "played", "wins", "draws", "losses", "goal_difference", "points"]
    frame = frame[[c for c in cols if c in frame.columns]].rename(columns={
        "position": "Pos", "team": "Country", "played": "P", "wins": "W",
        "draws": "D", "losses": "L", "goal_difference": "GD", "points": "Pts",
    })
    st.dataframe(frame, width="stretch", hide_index=True)


def render_live_group(matches, predictions, prices, selected_team: str) -> bool:
    group = _group(matches, selected_team)
    if not group:
        return False
    active = matches[(matches["stage"] == "GROUP_STAGE") & (matches["group"].astype(str).str.replace("GROUP_", "") == group) & matches["status"].isin(LIVE_STATUSES)]
    if active.empty:
        return False

    strength = dict(zip(prices["team"], prices["cupmarket_price"])) if not prices.empty else {}
    snapshot = build_provisional_snapshot(matches, strength)
    current = snapshot["team_status"].get(selected_team)
    if not current:
        return False

    st.info("Live mode is active. Current scores shape this provisional view; the official model and country prices remain unchanged until the match is final.")
    st.markdown("#### Group matches live now")
    cols = st.columns(max(1, len(active)))
    for col, row in zip(cols, active.itertuples(index=False)):
        minute = getattr(row, "minute", None)
        minute_text = "HT" if row.status == "PAUSED" else (f"{int(minute)}'" if pd.notna(minute) else "LIVE")
        home = int(getattr(row, "home_score_full_time", 0) or 0)
        away = int(getattr(row, "away_score_full_time", 0) or 0)
        col.markdown(f'<div class="cm-match-card"><div class="cm-match-meta">{minute_text} · LIVE</div><div class="cm-match-teams"><strong>{row.home_team}</strong><span>{home}–{away}</span><strong>{row.away_team}</strong></div></div>', unsafe_allow_html=True)

    metrics = st.columns(4)
    metrics[0].metric("Live provisional position", current["position"])
    metrics[1].metric("Provisional points", current["points"])
    metrics[2].metric("Provisional goal difference", current["goal_difference"])
    metrics[3].metric("If matches ended now", "Qualifies" if current["qualifies_if_ended_now"] else "Outside")
    st.info(current["status_if_ended_now"])

    st.markdown("#### Table if the live scores held")
    _table(snapshot["tables"].get(group, []))
    st.caption("This is provisional. A goal in either simultaneous match can change it.")

    if current["position"] == 3:
        rows = []
        for rank, row in enumerate(snapshot["third_place_ranking"], start=1):
            rows.append({"Rank": rank, "Country": row["team"], "Group": row["group"], "Pts": row["points"], "GD": row["goal_difference"], "GF": row["goals_for"], "Line": "Qualifying" if rank <= 8 else "Outside"})
        st.markdown("#### Provisional best third-place ranking")
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    with st.spinner("Projecting the remaining minutes across all groups..."):
        result = cached_projection(matches, predictions, tuple(sorted(strength.items())), selected_team, 1400)
    if result.get("available"):
        team_result = result["teams"].get(selected_team, {})
        st.markdown("#### Projection from the current score")
        cols = st.columns(4)
        cols[0].metric("Qualify", pct(team_result.get("qualification_probability")))
        cols[1].metric("Top two", pct(team_result.get("direct_top_two_probability")))
        cols[2].metric("Best third", pct(team_result.get("best_third_probability")))
        cols[3].metric("Most likely finish", team_result.get("most_likely_position", "—"))
        helpful = result.get("selected_team_helpful_result")
        if helpful and helpful.get("lift", 0) > 0.01:
            st.success(f"Most helpful other result: {helpful['label']}. Qualification becomes about {pct(helpful['qualification_probability'])}.")
        st.caption(result["method_note"] + " These are estimates, not guarantees.")

    impacts = next_goal_impacts(matches, selected_team, strength)
    if impacts:
        st.markdown("#### What the next goal could change")
        frame = pd.DataFrame(impacts).rename(columns={"event": "Possible next goal", "position": "New position", "status": "Status if scores then held", "position_change": "Position movement"})
        st.dataframe(frame, width="stretch", hide_index=True)
    return True


def render_live_match(matches, predictions, prices, match_id: int) -> bool:
    rows = matches[matches["match_id"] == int(match_id)]
    if rows.empty:
        return False
    match = rows.iloc[0]
    if is_live_knockout_match(match):
        result = cached_knockout_projection(matches, predictions, int(match_id), 2600)
        live = result.get("matches", {}).get(int(match_id))
        if not live:
            st.info(
                "This knockout match is live, but a saved pre-match knockout "
                "forecast is needed before CupMarket can show live advance chances."
            )
            return True

        st.markdown("#### Live chance to advance")
        st.caption(
            f"Current state: {live['current_score']} after about "
            f"{live.get('minute', 0)} minutes."
        )
        cols = st.columns(2)
        cols[0].metric(
            f"{match.get('home_team')} chance to advance",
            pct(live.get("home_advance_probability")),
        )
        cols[1].metric(
            f"{match.get('away_team')} chance to advance",
            pct(live.get("away_advance_probability")),
        )
        scores = pd.DataFrame(live.get("likely_final_scorelines", []))
        if not scores.empty:
            scores["probability"] = scores["probability"].map(pct)
            st.dataframe(
                scores.rename(
                    columns={
                        "score": "Likely final score",
                        "probability": "Probability",
                    }
                ),
                width="stretch",
                hide_index=True,
            )
        st.caption(live["method_note"] + " The original pre-match forecast remains visible below.")
        return True

    if match.get("status") not in LIVE_STATUSES:
        return False
    if str(match.get("stage", "")).upper() != "GROUP_STAGE":
        return False
    strength = dict(zip(prices["team"], prices["cupmarket_price"])) if not prices.empty else {}
    result = cached_projection(matches, predictions, tuple(sorted(strength.items())), str(match.get("home_team")), 1200)
    live = result.get("matches", {}).get(int(match_id))
    if not live:
        return False

    st.markdown("#### Live projection from the current score")
    st.caption(f"Current state: {live['current_score']} after about {live.get('minute', 0)} minutes.")
    cols = st.columns(3)
    cols[0].metric(f"{match.get('home_team')} live win", pct(live["home_win_probability"]))
    cols[1].metric("Live draw", pct(live["draw_probability"]))
    cols[2].metric(f"{match.get('away_team')} live win", pct(live["away_win_probability"]))
    scores = pd.DataFrame(live.get("likely_scorelines", []))
    if not scores.empty:
        scores["probability"] = scores["probability"].map(pct)
        st.dataframe(scores.rename(columns={"score": "Likely final score", "probability": "Probability"}), width="stretch", hide_index=True)
    qcols = st.columns(2)
    for col, team in zip(qcols, [match.get("home_team"), match.get("away_team")]):
        team_result = result.get("teams", {}).get(str(team), {})
        col.metric(f"{team} live qualification", pct(team_result.get("qualification_probability")), delta=f"Top two {pct(team_result.get('direct_top_two_probability'))}")
    st.caption(result["method_note"] + " The original pre-match forecast remains visible below.")
    return True
