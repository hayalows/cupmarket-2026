from pathlib import Path
import json
import time

import pandas as pd
import streamlit as st

from backend.live_qualification import LIVE_STATUSES
from features.live_match_data import (
    format_source_time,
    group_freshness,
    load_matches,
    should_auto_refresh,
)
from features.live_match_experience import render_match_experience
from features.match_ui import combine_prediction_sources
from features.product_ui import (
    inject_styles,
    render_data_diagnostics,
    render_live_feed_notice,
    render_live_vs_official_note,
    render_page_guide,
    render_project_footer,
    render_specialist_sidebar,
)

st.set_page_config(
    page_title="CupMarket Match Intelligence",
    page_icon="⚽",
    layout="wide",
)

root = Path(__file__).resolve().parents[1]
data_dir = root / "data"

inject_styles(root)
render_specialist_sidebar("match")


def file_version(path: Path) -> int:
    return path.stat().st_mtime_ns if path.exists() else 0


@st.cache_data(show_spinner=False)
def read_csv(path_text: str, version: int) -> pd.DataFrame:
    path = Path(path_text)
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    for column in ["utc_date", "generated_at_utc", "last_updated"]:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce", utc=True)
    return frame


@st.cache_data(show_spinner=False)
def read_json(path_text: str, version: int) -> dict:
    path = Path(path_text)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def cached_csv(path: Path) -> pd.DataFrame:
    return read_csv(str(path), file_version(path))


def cached_json(path: Path) -> dict:
    return read_json(str(path), file_version(path))


def load_match_room_data() -> dict:
    load_started = time.perf_counter()
    matches, score_metadata = load_matches(data_dir / "world_cup_2026_matches_latest.csv")
    latest_predictions = cached_csv(data_dir / "world_cup_live_predictions_latest.csv")
    prediction_ledger = cached_csv(root / "backend" / "state" / "world_cup_prediction_ledger.csv")
    prices = cached_csv(data_dir / "cupmarket_prices_latest.csv")
    model_metadata = cached_json(data_dir / "phase5_simulation_metadata.json")
    return {
        "matches": matches,
        "score_metadata": score_metadata,
        "prices": prices,
        "model_metadata": model_metadata,
        "predictions": combine_prediction_sources(latest_predictions, prediction_ledger),
        "load_time_ms": (time.perf_counter() - load_started) * 1000,
    }


def render_match_room(data: dict, refresh_label: str) -> None:
    matches = data["matches"]
    score_metadata = data["score_metadata"]
    model_metadata = data["model_metadata"]
    freshness = group_freshness(matches, model_metadata)
    live_count = (
        int(matches["status"].isin(LIVE_STATUSES).sum())
        if not matches.empty and "status" in matches.columns
        else 0
    )
    live_status_text = (
        f"{live_count} live match{'es' if live_count != 1 else ''}"
        if live_count
        else "Forecast mode"
    )
    live_status_class = "updating" if live_count else "attention"
    hero_description = (
        "Live matches are active. Open one to follow the changing match outlook, "
        "qualification picture, connected group effects and published-market context."
        if live_count
        else "No match is marked live right now. CupMarket will increase its check rate "
        "automatically when a kickoff window begins."
    )

    st.markdown(
        f'''
        <div class="cm-hero">
            <div class="cm-hero-top">
                <div class="cm-eyebrow">CupMarket 2026 · Match intelligence</div>
                <div class="cm-status {live_status_class}">
                    <span class="cm-dot"></span>{live_status_text}
                </div>
            </div>
            <h1>Open the match. Understand the consequences.</h1>
            <p>{hero_description}</p>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    render_live_feed_notice(score_metadata)

    if freshness["pending_model_updates"]:
        pending = freshness["pending_model_updates"]
        st.warning(
            f"{pending} completed group match"
            + ("es are" if pending != 1 else " is")
            + " visible in the score feed but not yet reflected in official probabilities "
            "and prices. Final scores are current; published market values update after the "
            "next successful model run."
        )

    render_match_experience(matches, data["predictions"], data["prices"])

    render_page_guide(
        "Useful before, during and after the match",
        "Match Intelligence adapts to the real match state.",
        [
            ("Before kickoff", "Read the forecast and test qualification outcomes."),
            ("During play", "Follow live outlook, group effects and market pressure."),
            ("After full time", "Review the result and wait for official repricing."),
        ],
    )
    render_live_vs_official_note()
    render_data_diagnostics(
        score_source=score_metadata.get("source", "Unknown"),
        score_refreshed=format_source_time(score_metadata.get("fetched_at_utc")),
        model_generated=format_source_time(model_metadata.get("generated_at_utc")),
        pending_updates=freshness["pending_model_updates"],
        technical_details=score_metadata.get("technical_warning"),
        load_time_ms=data["load_time_ms"],
        refresh_key="match_room_refresh_scores",
        token_configured=score_metadata.get("token_configured"),
        feed_state=score_metadata.get("feed_state"),
        requests_remaining=score_metadata.get("requests_remaining"),
    )
    st.caption(
        f"{refresh_label} The external score provider may still be several minutes behind the broadcast."
    )


@st.fragment(run_every="45s")
def render_active_match_room() -> None:
    data = load_match_room_data()
    if not should_auto_refresh(data["matches"]):
        st.rerun()
    render_match_room(data, "Live checks run every 45 seconds.")


@st.fragment(run_every="5m")
def render_idle_match_room() -> None:
    data = load_match_room_data()
    if should_auto_refresh(data["matches"]):
        st.rerun()
    render_match_room(data, "No match is active; CupMarket checks every five minutes.")


initial_data = load_match_room_data()
if should_auto_refresh(initial_data["matches"]):
    render_active_match_room()
else:
    render_idle_match_room()

render_project_footer()
