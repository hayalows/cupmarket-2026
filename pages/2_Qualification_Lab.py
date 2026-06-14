from pathlib import Path
import json
import time

import pandas as pd
import streamlit as st

from features.live_match_data import (
    format_source_time,
    group_freshness,
    load_matches,
)
from features.match_ui import combine_prediction_sources
from features.qualification_ui import render_qualification_lab
from features.product_ui import (
    inject_styles,
    render_data_diagnostics,
    render_live_vs_official_note,
    render_page_guide,
    render_project_footer,
    render_specialist_sidebar,
)

st.set_page_config(
    page_title="CupMarket Qualification Lab",
    page_icon="🧭",
    layout="wide",
)

root = Path(__file__).resolve().parents[1]
data_dir = root / "data"

inject_styles(root)
render_specialist_sidebar("qualification")


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
            frame[column] = pd.to_datetime(
                frame[column], errors="coerce", utc=True
            )
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


def render_feed_notice(metadata: dict) -> None:
    kind = metadata.get("failure_kind")
    if kind == "missing_token":
        st.error(
            "Live scores are not connected in this Streamlit deployment. Add "
            "FOOTBALL_DATA_TOKEN in Streamlit App settings → Secrets, save it, "
            "then reboot the app. The saved snapshot is being shown for now."
        )
    elif kind == "invalid_token":
        st.error(
            "The Streamlit live-score token was rejected. Replace it in App settings → "
            "Secrets, save it, then reboot the app."
        )
    elif metadata.get("is_fallback"):
        st.warning(
            (metadata.get("warning") or "The live score source is unavailable.")
            + " The latest saved GitHub snapshot is being used."
        )
    elif metadata.get("feed_state") == "provider_delayed":
        st.warning(
            "Kickoff has passed, but the provider still marks the fixture as scheduled. "
            "This page is checking automatically every 45 seconds."
        )
    elif metadata.get("warning"):
        st.warning(metadata["warning"])


@st.fragment(run_every="45s")
def render_live_qualification_lab() -> None:
    load_started = time.perf_counter()
    matches, score_metadata = load_matches(
        data_dir / "world_cup_2026_matches_latest.csv"
    )
    latest_predictions = cached_csv(
        data_dir / "world_cup_live_predictions_latest.csv"
    )
    prediction_ledger = cached_csv(
        root / "backend" / "state" / "world_cup_prediction_ledger.csv"
    )
    prices = cached_csv(data_dir / "cupmarket_prices_latest.csv")
    group_tables = cached_csv(data_dir / "current_group_tables.csv")
    model_metadata = cached_json(data_dir / "phase5_simulation_metadata.json")
    predictions = combine_prediction_sources(
        latest_predictions,
        prediction_ledger,
    )
    freshness = group_freshness(matches, model_metadata)
    load_time_ms = (time.perf_counter() - load_started) * 1000

    st.markdown(
        '''
        <div class="cm-hero">
            <div class="cm-eyebrow">CupMarket 2026 · Qualification scenarios</div>
            <h1>What does the next result change?</h1>
            <p>Select a country first. CupMarket then shows the routes created by a win, draw or loss, and switches to a provisional live view when its group is playing.</p>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    render_feed_notice(score_metadata)

    if freshness["pending_model_updates"]:
        st.warning(
            "A completed result is visible in the score feed but is still awaiting the "
            "published model update. Live tables are current; scenario probabilities still "
            "use the latest published forecast."
        )

    render_qualification_lab(
        matches,
        predictions,
        prices,
        group_tables,
        {"pending_finished_matches": freshness["pending_model_updates"]},
    )

    render_page_guide(
        "See what the next result changes",
        "Use the lab when you want to understand one country's qualification routes.",
        [
            ("Select", "Choose the country you care about."),
            ("Run", "Calculate its win, draw and loss paths."),
            ("Read", "Compare top-two and best-third routes."),
        ],
    )
    render_live_vs_official_note()
    render_data_diagnostics(
        score_source=score_metadata.get("source", "Unknown"),
        score_refreshed=format_source_time(score_metadata.get("fetched_at_utc")),
        model_generated=format_source_time(model_metadata.get("generated_at_utc")),
        pending_updates=freshness["pending_model_updates"],
        load_time_ms=load_time_ms,
        refresh_key="qualification_refresh_scores",
        token_configured=score_metadata.get("token_configured"),
        feed_state=score_metadata.get("feed_state"),
        requests_remaining=score_metadata.get("requests_remaining"),
    )
    st.caption(
        "Automatic score refresh runs every 45 seconds while this page is open."
    )


render_live_qualification_lab()
render_project_footer()
