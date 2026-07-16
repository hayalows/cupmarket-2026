from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from features.market_movement import add_rank_movement, rank_movement_text
from features.market_board import render_market_board
from features.match_ui import match_stage_label
from features.official_data import load_latest_csv
from features.product_guidance import (
    render_start_here_panel,
    render_todays_story,
)
from features.product_ui import render_official_data_caption
from features.tournament_data import load_static_data
from features.tournament_path_data import round_of_16_build

ROOT = Path(__file__).resolve().parents[1]
KNOCKOUT_PROGRESS_PATH = ROOT / "data" / "knockout_progress_latest.csv"
LIVE_STATUSES = {"IN_PLAY", "LIVE", "PAUSED", "SUSPENDED"}
UPCOMING_STATUSES = {"TIMED", "SCHEDULED"}
FINISHED_STATUSES = {"FINISHED", "AWARDED"}
EXIT_STAGE_COLUMNS = [
    ("prob_group_exit", "Group stage"),
    ("prob_round_32_exit", "Round of 32"),
    ("prob_round_16_exit", "Round of 16"),
    ("prob_quarter_final_exit", "Quarter-final"),
    ("prob_semi_final_exit", "Semi-final"),
    ("prob_runner_up", "Final"),
]
STAGE_OPTIONS = [
    ("GROUP_STAGE", "Group stage", {"GROUP_STAGE", "GROUP", "GROUPS"}),
    ("LAST_32", "Round of 32", {"LAST_32", "ROUND_OF_32", "R32"}),
    ("LAST_16", "Round of 16", {"LAST_16", "ROUND_OF_16", "R16"}),
    ("QUARTER_FINALS", "Quarter-finals", {"QUARTER_FINALS", "QUARTER_FINAL", "QF"}),
    ("SEMI_FINALS", "Semi-finals", {"SEMI_FINALS", "SEMI_FINAL", "SF"}),
    ("FINAL", "Final", {"FINAL"}),
]
STAGE_LABELS = {key: label for key, label, _ in STAGE_OPTIONS}
STAGE_ALIASES = {
    alias: key
    for key, _, aliases in STAGE_OPTIONS
    for alias in aliases | {key}
}
STAGE_REACH_COLUMNS = {
    "GROUP_STAGE": "prob_reach_round_32",
    "LAST_32": "prob_reach_round_32",
    "LAST_16": "prob_reach_round_16",
    "QUARTER_FINALS": "prob_reach_quarter_final",
    "SEMI_FINALS": "prob_reach_semi_final",
    "FINAL": "prob_reach_final",
}
STAGE_EXIT_LABELS = {
    "GROUP_STAGE": "Group stage",
    "LAST_32": "Round of 32",
    "LAST_16": "Round of 16",
    "QUARTER_FINALS": "Quarter-final",
    "SEMI_FINALS": "Semi-final",
    "FINAL": "Final",
}


def _inject_styles() -> None:
    path = ROOT / "assets" / "pulse_v3.css"
    if path.exists():
        st.markdown(f"<style>{path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def _score(row: pd.Series) -> str:
    home = pd.to_numeric(
        row.get("home_score", row.get("home_score_full_time")),
        errors="coerce",
    )
    away = pd.to_numeric(
        row.get("away_score", row.get("away_score_full_time")),
        errors="coerce",
    )
    return "vs" if pd.isna(home) or pd.isna(away) else f"{int(home)}–{int(away)}"


def _kickoff(value) -> str:
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    return "Time pending" if pd.isna(timestamp) else timestamp.strftime("%d %b · %H:%M UTC")


def _go_to_matches(view: str, match_id: int | None = None) -> None:
    st.session_state["cupmarket_match_hub_view"] = view
    if match_id is not None:
        st.session_state["cupmarket_match_hub_match_id"] = int(match_id)
    st.switch_page("pages/4_Match_Hub.py")


def _go_to_market(team: str) -> None:
    st.session_state["cupmarket_path_requested_team"] = team
    st.session_state["cupmarket_country_requested_section"] = "Market"
    st.switch_page("pages/7_Tournament_Path.py")

def _go_to_path(team: str | None = None) -> None:
    if team:
        st.session_state["cupmarket_path_requested_team"] = team
    st.switch_page("pages/7_Tournament_Path.py")


def _go_to_bracket(team: str | None = None) -> None:
    if team:
        st.session_state["cupmarket_path_requested_team"] = team
    st.switch_page("pages/8_Bracket_View.py")


def _numeric(value, default: float = 0.0) -> float:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return default
    return float(number)


def _clean_team(value) -> str:
    try:
        if pd.isna(value):
            return "TBD"
    except (TypeError, ValueError):
        pass
    text = str(value or "").strip()
    return "TBD" if text.lower() in {"", "nan", "none", "null", "tbd"} else text


def _normal_stage(value) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value or "").strip().upper()
    if not text or text in {"NAN", "NONE", "NULL"}:
        return ""
    return STAGE_ALIASES.get(text, text)


def _stage_label_from_key(stage_key: str) -> str:
    return STAGE_LABELS.get(_normal_stage(stage_key), str(stage_key or "").replace("_", " ").title())


def _stage_sort_index(stage_key: str) -> int:
    key = _normal_stage(stage_key)
    for index, (candidate, _, _) in enumerate(STAGE_OPTIONS):
        if candidate == key:
            return index
    return len(STAGE_OPTIONS)


def _sort_by_time(frame: pd.DataFrame, ascending: bool = True) -> pd.DataFrame:
    if frame.empty:
        return frame
    if "utc_date" not in frame.columns:
        return frame
    sorted_frame = frame.copy()
    sorted_frame["utc_date"] = pd.to_datetime(sorted_frame["utc_date"], errors="coerce", utc=True)
    return sorted_frame.sort_values("utc_date", ascending=ascending, na_position="last")


def _score_any(row: pd.Series) -> str:
    home = pd.to_numeric(
        row.get("home_score", row.get("home_score_full_time")),
        errors="coerce",
    )
    away = pd.to_numeric(
        row.get("away_score", row.get("away_score_full_time")),
        errors="coerce",
    )
    return "vs" if pd.isna(home) or pd.isna(away) else f"{int(home)}-{int(away)}"


def _score_or_live(row: pd.Series) -> str:
    score = _score_any(row)
    if score != "vs":
        return score
    home = pd.to_numeric(row.get("home_score_full_time"), errors="coerce")
    away = pd.to_numeric(row.get("away_score_full_time"), errors="coerce")
    return "vs" if pd.isna(home) or pd.isna(away) else f"{int(home)}-{int(away)}"


def _stage_text(row: pd.Series) -> str:
    label = match_stage_label(row)
    return label if label else str(row.get("stage", "Tournament")).replace("_", " ").title()


def _exit_stage(row: pd.Series) -> str:
    for column, label in EXIT_STAGE_COLUMNS:
        if _numeric(row.get(column)) >= 0.999:
            return label
    return "Still alive"


def _eliminated_teams(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty or "team" not in prices.columns:
        return pd.DataFrame()
    rows = []
    for _, row in prices.iterrows():
        exit_stage = _exit_stage(row)
        champion = _numeric(row.get("prob_champion"))
        still_alive = exit_stage == "Still alive" or champion > 0.0
        if still_alive:
            continue
        rows.append(
            {
                "Country": row.get("team"),
                "Exit": exit_stage,
                "Price": f"{_numeric(row.get('cupmarket_price')):.2f} CM",
                "Champion": "0.0%",
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["Exit", "Country"]).reset_index(drop=True)


def _alive_teams(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty or "team" not in prices.columns:
        return pd.DataFrame()
    rows = prices.copy()
    rows["exit_stage"] = rows.apply(_exit_stage, axis=1)
    rows = rows.loc[rows["exit_stage"].eq("Still alive")].copy()
    if rows.empty:
        return rows
    rows["cupmarket_price"] = pd.to_numeric(rows["cupmarket_price"], errors="coerce")
    return rows.sort_values("cupmarket_price", ascending=False).reset_index(drop=True)


def _load_knockout_progress() -> pd.DataFrame:
    return load_latest_csv(KNOCKOUT_PROGRESS_PATH)


def _source_for_stage(matches: pd.DataFrame, progress: pd.DataFrame, stage_key: str) -> pd.DataFrame:
    key = _normal_stage(stage_key)
    if key == "GROUP_STAGE":
        source = matches.copy() if isinstance(matches, pd.DataFrame) else pd.DataFrame()
    elif isinstance(progress, pd.DataFrame) and not progress.empty:
        source = progress.copy()
    else:
        source = matches.copy() if isinstance(matches, pd.DataFrame) else pd.DataFrame()
    if source.empty or "stage" not in source.columns:
        return pd.DataFrame()
    source["stage_key"] = source["stage"].map(_normal_stage)
    filtered = source.loc[source["stage_key"].eq(key)].copy()
    if "utc_date" in filtered.columns:
        filtered["utc_date"] = pd.to_datetime(filtered["utc_date"], errors="coerce", utc=True)
        filtered = filtered.sort_values("utc_date", na_position="last")
    return filtered


def _default_stage(matches: pd.DataFrame, progress: pd.DataFrame) -> str:
    frames = []
    for frame in [progress, matches]:
        if isinstance(frame, pd.DataFrame) and not frame.empty and {"stage", "status"}.issubset(frame.columns):
            frames.append(frame.copy())
    if not frames:
        return "GROUP_STAGE"

    source = pd.concat(frames, ignore_index=True, sort=False)
    source["stage_key"] = source["stage"].map(_normal_stage)
    source = source.loc[source["stage_key"].isin(STAGE_LABELS)].copy()
    if source.empty:
        return "GROUP_STAGE"
    if "utc_date" in source.columns:
        source["utc_date"] = pd.to_datetime(source["utc_date"], errors="coerce", utc=True)

    for statuses, ascending in [
        (LIVE_STATUSES, True),
        (UPCOMING_STATUSES, True),
        (FINISHED_STATUSES, False),
    ]:
        rows = source.loc[source["status"].astype(str).isin(statuses)].copy()
        if rows.empty:
            continue
        rows = _sort_by_time(rows, ascending=ascending)
        return str(rows.iloc[0]["stage_key"])
    return "GROUP_STAGE"


def _stage_status_counts(fixtures: pd.DataFrame) -> dict[str, int]:
    if fixtures.empty or "status" not in fixtures.columns:
        return {"fixtures": 0, "finished": 0, "live": 0, "upcoming": 0}
    statuses = fixtures["status"].astype(str)
    return {
        "fixtures": len(fixtures),
        "finished": int(statuses.isin(FINISHED_STATUSES).sum()),
        "live": int(statuses.isin(LIVE_STATUSES).sum()),
        "upcoming": int(statuses.isin(UPCOMING_STATUSES).sum()),
    }


def _stage_participants(fixtures: pd.DataFrame) -> list[str]:
    if fixtures.empty:
        return []
    teams = []
    for column in ["home_team", "away_team"]:
        if column not in fixtures.columns:
            continue
        for value in fixtures[column].tolist():
            team = _clean_team(value)
            if team != "TBD":
                teams.append(team)
    return sorted(set(teams))


def _stage_fixture_table(fixtures: pd.DataFrame) -> pd.DataFrame:
    if fixtures.empty:
        return pd.DataFrame()
    rows = []
    for _, row in fixtures.iterrows():
        home = _clean_team(row.get("home_team"))
        away = _clean_team(row.get("away_team"))
        status = str(row.get("status", "") or "").replace("_", " ").title()
        score = _score_or_live(row)
        advanced = _clean_team(row.get("advancing_team"))
        if advanced != "TBD":
            outcome = f"{advanced} advanced"
        elif str(row.get("status", "")).upper() in FINISHED_STATUSES:
            outcome = "Result published"
        elif str(row.get("status", "")).upper() in LIVE_STATUSES:
            minute = pd.to_numeric(row.get("minute"), errors="coerce")
            outcome = f"Live at {int(minute)} min" if pd.notna(minute) else "Live now"
        else:
            outcome = _kickoff(row.get("utc_date"))
        rows.append(
            {
                "Stage": _stage_text(row),
                "Status": status,
                "Fixture": f"{home} vs {away}",
                "Score": score,
                "Outcome": outcome,
                "Kickoff": _kickoff(row.get("utc_date")),
            }
        )
    return pd.DataFrame(rows)


def _stage_decision_tables(fixtures: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if fixtures.empty:
        empty = pd.DataFrame()
        return {"advanced": empty, "eliminated": empty, "pending": empty}

    advanced_rows = []
    eliminated_rows = []
    pending_rows = []
    for _, row in fixtures.iterrows():
        home = _clean_team(row.get("home_team"))
        away = _clean_team(row.get("away_team"))
        status = str(row.get("status", "") or "").upper()
        advancing = _clean_team(row.get("advancing_team"))
        fixture = f"{home} vs {away}"
        score = _score_or_live(row)
        kickoff = _kickoff(row.get("utc_date"))

        if status in FINISHED_STATUSES and advancing != "TBD":
            advanced_rows.append(
                {
                    "Country": advancing,
                    "Result": f"{home} {score} {away}",
                    "Next": "Round of 16" if _normal_stage(row.get("stage")) == "LAST_32" else "Next round",
                }
            )
            eliminated = away if advancing == home else home if advancing == away else "TBD"
            if eliminated != "TBD":
                eliminated_rows.append(
                    {
                        "Country": eliminated,
                        "Result": f"{home} {score} {away}",
                    }
                )
        elif home != "TBD" and away != "TBD":
            pending_rows.append(
                {
                    "Fixture": fixture,
                    "Kickoff": kickoff,
                    "Status": str(row.get("status", "Pending")).replace("_", " ").title(),
                }
            )

    return {
        "advanced": pd.DataFrame(advanced_rows),
        "eliminated": pd.DataFrame(eliminated_rows),
        "pending": pd.DataFrame(pending_rows),
    }


def _stage_country_table(
    prices: pd.DataFrame,
    stage_key: str,
    participants: list[str] | None = None,
    limit: int = 12,
) -> pd.DataFrame:
    if prices.empty or "team" not in prices.columns:
        return pd.DataFrame()
    frame = prices.copy()
    if participants:
        frame = frame.loc[frame["team"].astype(str).isin(participants)].copy()
    if frame.empty:
        frame = prices.copy()

    chance_column = STAGE_REACH_COLUMNS.get(_normal_stage(stage_key))
    if chance_column in frame.columns:
        frame["stage_chance_sort"] = pd.to_numeric(frame[chance_column], errors="coerce").fillna(0.0)
    else:
        frame["stage_chance_sort"] = 0.0
    if "cupmarket_price" in frame.columns:
        frame["price_sort"] = pd.to_numeric(frame["cupmarket_price"], errors="coerce").fillna(0.0)
    else:
        frame["price_sort"] = 0.0
    frame["Exit"] = frame.apply(_exit_stage, axis=1)
    frame = frame.sort_values(["stage_chance_sort", "price_sort"], ascending=False).head(limit)

    rows = []
    for _, row in frame.iterrows():
        chance = row.get(chance_column) if chance_column in row.index else None
        champion = row.get("prob_champion")
        rows.append(
            {
                "Country": row.get("team"),
                "Price": f"{_numeric(row.get('cupmarket_price')):.2f} CM",
                "Stage chance": f"{100 * _numeric(chance):.1f}%" if chance_column else "-",
                "Champion": f"{100 * _numeric(champion):.1f}%",
                "Status": "Alive" if row["Exit"] == "Still alive" else f"Out: {row['Exit']}",
            }
        )
    return pd.DataFrame(rows)


def _stage_eliminated_for_key(prices: pd.DataFrame, stage_key: str) -> pd.DataFrame:
    eliminated = _eliminated_teams(prices)
    if eliminated.empty:
        return eliminated
    exit_label = STAGE_EXIT_LABELS.get(_normal_stage(stage_key), "")
    return eliminated.loc[eliminated["Exit"].eq(exit_label)].reset_index(drop=True)


def _stage_story(stage_key: str, fixtures: pd.DataFrame, prices: pd.DataFrame) -> str:
    label = _stage_label_from_key(stage_key)
    counts = _stage_status_counts(fixtures)
    alive_count = len(_alive_teams(prices))
    eliminated_count = len(_eliminated_teams(prices))

    if _normal_stage(stage_key) == "GROUP_STAGE":
        if counts["live"]:
            return "The group stage is live. Watch tables, pressure and match context move together before the bracket locks."
        if counts["upcoming"]:
            return "The group stage is still shaping the bracket. Use this round to understand who can reach the knockouts."
        return "The group stage has done its job: it built the knockout bracket and set the first market shock points."

    if fixtures.empty:
        return f"{label} is waiting for official fixture data. CupMarket can still show projected paths and market leaders."

    live = fixtures.loc[fixtures["status"].astype(str).isin(LIVE_STATUSES)] if "status" in fixtures.columns else pd.DataFrame()
    if not live.empty:
        row = _sort_by_time(live).iloc[0]
        return (
            f"{label} is live: {_clean_team(row.get('home_team'))} {_score_or_live(row)} "
            f"{_clean_team(row.get('away_team'))}. Follow chance to advance as the score changes."
        )

    finished = fixtures.loc[fixtures["status"].astype(str).isin(FINISHED_STATUSES)] if "status" in fixtures.columns else pd.DataFrame()
    if not finished.empty:
        latest = _sort_by_time(finished, ascending=False).iloc[0]
        advanced = _clean_team(latest.get("advancing_team"))
        result = f"{_clean_team(latest.get('home_team'))} {_score_or_live(latest)} {_clean_team(latest.get('away_team'))}"
        if advanced != "TBD":
            return f"{advanced} advanced from {label} after {result}. {alive_count} teams remain alive; {eliminated_count} are out."
        return f"{label} has published a result: {result}. Prices re-rank after the model settles the match."

    upcoming = fixtures.loc[fixtures["status"].astype(str).isin(UPCOMING_STATUSES)] if "status" in fixtures.columns else pd.DataFrame()
    if not upcoming.empty:
        row = _sort_by_time(upcoming).iloc[0]
        return (
            f"Next in {label}: {_clean_team(row.get('home_team'))} vs "
            f"{_clean_team(row.get('away_team'))} at {_kickoff(row.get('utc_date'))}. "
            "Open the match to see xG, likely scores and chance to advance."
        )

    return f"{label} has {counts['fixtures']} fixture rows ready. Open the bracket or a country path for the cleaner story."


def _knockout_results(matches: pd.DataFrame, progress: pd.DataFrame) -> pd.DataFrame:
    source = progress.copy() if isinstance(progress, pd.DataFrame) else pd.DataFrame()
    if source.empty and not matches.empty:
        source = matches.copy()
        if "stage" in source.columns:
            source = source.loc[source["stage"].astype(str).ne("GROUP_STAGE")].copy()
    if source.empty or "status" not in source.columns:
        return pd.DataFrame()
    source = source.loc[source["status"].astype(str).isin(FINISHED_STATUSES)].copy()
    if source.empty:
        return source
    if "utc_date" in source.columns:
        source["utc_date"] = pd.to_datetime(source["utc_date"], errors="coerce", utc=True)
        source = source.sort_values("utc_date", ascending=False, na_position="last")
    rows = []
    for _, row in source.iterrows():
        home = row.get("home_team")
        away = row.get("away_team")
        home_score = row.get("home_score", row.get("home_score_full_time"))
        away_score = row.get("away_score", row.get("away_score_full_time"))
        home_goals = pd.to_numeric(home_score, errors="coerce")
        away_goals = pd.to_numeric(away_score, errors="coerce")
        score = "vs" if pd.isna(home_goals) or pd.isna(away_goals) else f"{int(home_goals)}-{int(away_goals)}"
        advancing = row.get("advancing_team")
        if not advancing or str(advancing).lower() == "nan":
            winner = str(row.get("winner", "") or "").upper()
            if winner == "HOME_TEAM":
                advancing = home
            elif winner == "AWAY_TEAM":
                advancing = away
            elif pd.notna(home_goals) and pd.notna(away_goals):
                advancing = home if home_goals > away_goals else away if away_goals > home_goals else ""
        eliminated = ""
        if advancing == home:
            eliminated = away
        elif advancing == away:
            eliminated = home
        rows.append(
            {
                "Stage": _stage_text(row),
                "Result": f"{home} {score} {away}",
                "Advanced": advancing or "Pending",
                "Eliminated": eliminated or "Pending",
                "Kickoff": _kickoff(row.get("utc_date")),
                "match_id": row.get("api_match_id", row.get("match_id")),
            }
        )
    return pd.DataFrame(rows)


def _stage_focus_match(fixtures: pd.DataFrame) -> tuple[str, int | None]:
    if fixtures.empty or "status" not in fixtures.columns:
        return "Live", None
    for statuses, view, ascending in [
        (LIVE_STATUSES, "Live", True),
        (UPCOMING_STATUSES, "Upcoming", True),
        (FINISHED_STATUSES, "Results", False),
    ]:
        rows = fixtures.loc[fixtures["status"].astype(str).isin(statuses)].copy()
        if rows.empty:
            continue
        row = _sort_by_time(rows, ascending=ascending).iloc[0]
        match_id = pd.to_numeric(row.get("match_id", row.get("api_match_id")), errors="coerce")
        return view, int(match_id) if pd.notna(match_id) else None
    return "Live", None


def _render_stage_decisions(selected_stage: str, fixtures: pd.DataFrame) -> None:
    if _normal_stage(selected_stage) == "GROUP_STAGE":
        return

    decisions = _stage_decision_tables(fixtures)
    advanced = decisions["advanced"]
    eliminated = decisions["eliminated"]
    pending = decisions["pending"]

    st.markdown(f"#### {_stage_label_from_key(selected_stage)} decisions")
    metrics = st.columns(3)
    metrics[0].metric("Advanced", len(advanced))
    metrics[1].metric("Eliminated this round", len(eliminated))
    metrics[2].metric("Still to play", len(pending))

    columns = st.columns(3)
    with columns[0]:
        st.caption("Through")
        if advanced.empty:
            st.write("No team has advanced from this round yet.")
        else:
            st.dataframe(advanced, hide_index=True, width="stretch")
    with columns[1]:
        st.caption("Out this round")
        if eliminated.empty:
            st.write("No team has been eliminated in this round yet.")
        else:
            st.dataframe(eliminated, hide_index=True, width="stretch")
    with columns[2]:
        st.caption("Still to play")
        if pending.empty:
            st.write("No pending fixture with two known teams.")
        else:
            st.dataframe(pending.head(8), hide_index=True, width="stretch")


def _render_round_of_16_building(progress: pd.DataFrame) -> None:
    slots = round_of_16_build(progress)
    if slots.empty:
        return
    st.markdown("#### Round of 16 building")
    st.caption(
        "This is built from Round-of-32 winners. It updates before the official feed fills every future fixture row."
    )
    display = slots[["match_number", "fixture", "state", "kickoff_utc"]].copy()
    display = display.rename(
        columns={
            "match_number": "Match",
            "fixture": "Slot",
            "state": "State",
            "kickoff_utc": "Kickoff",
        }
    )
    display["Kickoff"] = display["Kickoff"].map(_kickoff)
    st.dataframe(display, hide_index=True, width="stretch")


def render_stage_explorer(matches: pd.DataFrame, prices: pd.DataFrame) -> None:
    progress = _load_knockout_progress()
    default_stage = _default_stage(matches, progress)
    labels = [_stage_label_from_key(stage_key) for stage_key, _, _ in STAGE_OPTIONS]
    default_index = min(_stage_sort_index(default_stage), len(labels) - 1)

    st.markdown("### Current round")
    st.caption(
        "Choose a round to see its fixtures, decisions and countries. Open Matches, "
        "Countries or Bracket when you need more detail."
    )
    selected_label = st.selectbox(
        "Round",
        labels,
        index=default_index,
        key="cupmarket_pulse_stage_explorer",
    )
    selected_stage = next(
        stage_key
        for stage_key, label, _ in STAGE_OPTIONS
        if label == selected_label
    )

    fixtures = _source_for_stage(matches, progress, selected_stage)
    participants = _stage_participants(fixtures)
    counts = _stage_status_counts(fixtures)
    country_table = _stage_country_table(prices, selected_stage, participants)
    story = _stage_story(selected_stage, fixtures, prices)
    decisions = _stage_decision_tables(fixtures)

    metrics = st.columns(4)
    metrics[0].metric("Fixtures", counts["fixtures"])
    if _normal_stage(selected_stage) == "GROUP_STAGE":
        metrics[1].metric("Live", counts["live"])
        metrics[2].metric("Finished", counts["finished"])
        metrics[3].metric("Countries", len(participants) if participants else len(country_table))
    else:
        metrics[1].metric("Advanced", len(decisions["advanced"]))
        metrics[2].metric("Eliminated", len(decisions["eliminated"]))
        metrics[3].metric("Still to play", len(decisions["pending"]))

    st.info(story)
    _render_stage_decisions(selected_stage, fixtures)
    if _normal_stage(selected_stage) == "LAST_32":
        _render_round_of_16_building(progress)

    focus_view, focus_match_id = _stage_focus_match(fixtures)
    default_team = None
    if participants:
        default_team = participants[0]
    elif not country_table.empty:
        default_team = str(country_table.iloc[0]["Country"])

    action_cols = st.columns(3)
    with action_cols[0]:
        if st.button("View matches", key=f"stage_explorer_matches_{selected_stage}", width="stretch"):
            _go_to_matches(focus_view, focus_match_id)
    with action_cols[1]:
        if st.button("View bracket", key=f"stage_explorer_bracket_{selected_stage}", width="stretch"):
            _go_to_bracket(default_team)
    with action_cols[2]:
        if st.button("View countries", key=f"stage_explorer_paths_{selected_stage}", width="stretch"):
            _go_to_path(default_team)

    fixture_tab, country_tab = st.tabs(["Fixtures", "Countries"])
    with fixture_tab:
        fixture_table = _stage_fixture_table(fixtures)
        if fixture_table.empty:
            st.caption("Official fixtures for this round are not available yet.")
        else:
            st.dataframe(
                fixture_table[["Status", "Fixture", "Score", "Outcome", "Kickoff"]],
                hide_index=True,
                width="stretch",
            )
    with country_tab:
        if country_table.empty:
            st.caption("Country data is not available for this round yet.")
        else:
            st.dataframe(country_table, hide_index=True, width="stretch")

def _next_match_summary(matches: pd.DataFrame) -> pd.Series:
    if matches.empty or "status" not in matches.columns:
        return pd.Series(dtype=object)
    active_or_next = matches.loc[
        matches["status"].astype(str).isin(LIVE_STATUSES | UPCOMING_STATUSES)
    ].copy()
    if active_or_next.empty:
        return pd.Series(dtype=object)
    active_or_next["utc_date"] = pd.to_datetime(
        active_or_next.get("utc_date"), errors="coerce", utc=True
    )
    live = active_or_next.loc[active_or_next["status"].astype(str).isin(LIVE_STATUSES)]
    if not live.empty:
        return live.sort_values("utc_date").iloc[0]
    return active_or_next.sort_values("utc_date").iloc[0]


def render_tournament_state(matches: pd.DataFrame, prices: pd.DataFrame) -> None:
    progress = _load_knockout_progress()
    results = _knockout_results(matches, progress)
    eliminated = _eliminated_teams(prices)
    alive = _alive_teams(prices)
    next_match = _next_match_summary(matches)

    st.markdown("### Tournament state")
    metrics = st.columns(4)
    metrics[0].metric("Still alive", len(alive) if not alive.empty else 0)
    metrics[1].metric("Eliminated", len(eliminated) if not eliminated.empty else 0)
    metrics[2].metric("Knockout results", len(results) if not results.empty else 0)
    if next_match.empty:
        metrics[3].metric("Next match", "None")
    else:
        metrics[3].metric("Next match", str(next_match.get("status", "Scheduled")).title())

    if not results.empty:
        latest = results.iloc[0]
        st.success(
            f"Latest knockout decision: {latest['Result']}. "
            f"{latest['Advanced']} advanced; {latest['Eliminated']} is out."
        )
        action_cols = st.columns(3)
        with action_cols[0]:
            if st.button("Open match details", key="pulse_latest_match_detail", width="stretch"):
                match_id = pd.to_numeric(latest.get("match_id"), errors="coerce")
                _go_to_matches("Results", int(match_id) if pd.notna(match_id) else None)
        with action_cols[1]:
            if st.button("Open advancing team", key="pulse_latest_advanced", width="stretch"):
                _go_to_path(str(latest["Advanced"]))
        with action_cols[2]:
            if st.button("Open eliminated team", key="pulse_latest_eliminated", width="stretch"):
                _go_to_path(str(latest["Eliminated"]))

    table_cols = st.columns(2)
    with table_cols[0]:
        st.markdown("#### Latest knockout decisions")
        if results.empty:
            st.caption("No knockout result has been published yet.")
        else:
            st.dataframe(
                results[["Stage", "Result", "Advanced", "Eliminated"]].head(6),
                hide_index=True,
                width="stretch",
            )
    with table_cols[1]:
        st.markdown("#### Eliminated teams")
        if eliminated.empty:
            st.caption("No team has a locked elimination row yet.")
        else:
            st.dataframe(
                eliminated.head(10),
                hide_index=True,
                width="stretch",
            )

    if not alive.empty:
        st.markdown("#### Still alive, ranked by CupMarket")
        display = alive.head(10).copy()
        columns = [
            column
            for column in [
                "market_rank",
                "team",
                "cupmarket_price",
                "prob_reach_round_16",
                "prob_reach_quarter_final",
                "prob_reach_final",
                "prob_champion",
            ]
            if column in display.columns
        ]
        display = display[columns].rename(
            columns={
                "market_rank": "Rank",
                "team": "Country",
                "cupmarket_price": "Price",
                "prob_reach_round_16": "Reach R16",
                "prob_reach_quarter_final": "Reach QF",
                "prob_reach_final": "Reach final",
                "prob_champion": "Champion",
            }
        )
        for column in ["Reach R16", "Reach QF", "Reach final", "Champion"]:
            if column in display.columns:
                display[column] = display[column].map(lambda value: f"{100 * _numeric(value):.1f}%")
        if "Price" in display.columns:
            display["Price"] = display["Price"].map(lambda value: f"{_numeric(value):.2f} CM")
        st.dataframe(display, hide_index=True, width="stretch")


def render_overview_v3(matches: pd.DataFrame, prices: pd.DataFrame, metadata: dict) -> None:
    _inject_styles()
    prices = add_rank_movement(prices)
    processed = load_static_data()["processed_ledger"]

    if matches.empty:
        finished = live = upcoming = pd.DataFrame()
    else:
        finished = matches[matches["status"].isin(["FINISHED", "AWARDED"])].sort_values(
            "utc_date", ascending=False
        )
        live = matches[matches["status"].isin(["IN_PLAY", "PAUSED"])].sort_values("utc_date")
        upcoming = matches[matches["status"].isin(["TIMED", "SCHEDULED"])].sort_values("utc_date")

    leader = prices.sort_values("cupmarket_price", ascending=False).iloc[0] if not prices.empty else pd.Series(dtype=object)
    default_team = str(leader.get("team")) if not leader.empty else "Ghana"
    predictions = metadata.get("predictions") if isinstance(metadata, dict) else pd.DataFrame()
    adaptive_ratings = metadata.get("adaptive_ratings") if isinstance(metadata, dict) else pd.DataFrame()

    round_tab, market_tab, today_tab = st.tabs(["Current round", "Market", "Today"])
    with round_tab:
        render_stage_explorer(matches, prices)
    with market_tab:
        render_market_board(
            prices,
            predictions=predictions,
            adaptive_ratings=adaptive_ratings,
        )
    with today_tab:
        render_todays_story(matches, prices)
        render_start_here_panel(default_team)

    render_official_data_caption(prices)
    st.caption(
        f"Tournament feed: {len(finished)} finished · {len(live)} live · "
        f"{len(upcoming)} upcoming. Model ledger: {len(processed)} processed results."
    )
