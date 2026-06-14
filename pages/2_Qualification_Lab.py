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
import features.product_ui as product_ui
from features.product_ui import (
    inject_styles,
    render_live_vs_official_note,
    render_page_guide,
    render_project_footer,
    render_specialist_sidebar,
)

st.set_page_config(
    page_title="CupMarket Qualification Lab",
    page_icon="◇",
    layout="wide",
)

root = Path(__file__).resolve().parents[1]
data_dir = root / "data"

inject_styles(root)
render_specialist_sidebar("qualification")


def render_data_diagnostics_compat(
    *,
    score_source: str,
    score_refreshed: str,
    model_generated: str,
    pending_updates: int | None = None,
    load_time_ms: float | None = None,
    refresh_key: str | None = None,
) -> None:
    helper = getattr(product_ui, "render_data_diagnostics", None)
    if callable(helper):
        helper(
            score_source=score_source,
            score_refreshed=score_refreshed,
            model_generated=model_generated,
            pending_updates=pending_updates,
            load_time_ms=load_time_ms,
            refresh_key=refresh_key,
        )
        return

    pending_text = (
        f" · {pending_updates} result{'s' if pending_updates != 1 else ''} awaiting model"
        if pending_updates is not None
        else ""
    )
    st.caption(
        f"Scores refreshed {score_refreshed} · Published model {model_generated}"
        f"{pending_text}"
    )
    with st.expander("Data freshness and system details", expanded=False):
        columns = st.columns(4 if pending_updates is not None else 3)
        columns[0].metric("Score source", score_source)
        columns[1].metric("Score feed refreshed", score_refreshed)
        columns[2].metric("Model generated", model_generated)
        if pending_updates is not None:
            columns[3].metric("Results awaiting model", pending_updates)
        if load_time_ms is not None:
            st.caption(f"Page data prepared in {load_time_ms:.0f} ms on this rerun.")
        if refresh_key and st.button(
            "Refresh live scores",
            key=refresh_key,
            help="Clears the score cache and requests the latest match states.",
        ):
            st.cache_data.clear()
            st.rerun()


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

if score_metadata.get("warning"):
    st.warning(
        score_metadata["warning"]
        + " The latest saved GitHub snapshot is being used instead."
    )

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
render_data_diagnostics_compat(
    score_source=score_metadata.get("source", "Unknown"),
    score_refreshed=format_source_time(score_metadata.get("fetched_at_utc")),
    model_generated=format_source_time(model_metadata.get("generated_at_utc")),
    pending_updates=freshness["pending_model_updates"],
    load_time_ms=load_time_ms,
    refresh_key="qualification_refresh_scores",
)
render_project_footer()
