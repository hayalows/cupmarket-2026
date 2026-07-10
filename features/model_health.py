"""The compact trust layer for published CupMarket data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from features.official_data import (
    fetch_update_workflow_health,
    load_latest_csv,
    load_latest_json,
    official_frame_status,
)
from features.tournament_data_v2 import DATA_DIR


MANIFEST_PATH = DATA_DIR / "publication_manifest.json"
ADAPTIVE_HEALTH_PATH = DATA_DIR / "adaptive_model_health.json"
PRICES_PATH = DATA_DIR / "cupmarket_prices_latest.csv"


def _timestamp(value) -> str:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return "Unavailable" if pd.isna(parsed) else parsed.strftime("%d %b %Y · %H:%M UTC")


def _status_text(workflow: dict[str, str | None]) -> str:
    conclusion = str(workflow.get("conclusion") or "").lower()
    state = str(workflow.get("state") or "").lower()
    if conclusion == "success":
        return "Workflow healthy"
    if conclusion in {"failure", "cancelled", "timed_out"}:
        return "Workflow needs attention"
    if state in {"queued", "in_progress"}:
        return "Workflow running"
    return "Workflow status unavailable"


def render_model_health() -> None:
    prices = load_latest_csv(PRICES_PATH)
    manifest = load_latest_json(MANIFEST_PATH)
    adaptive = load_latest_json(ADAPTIVE_HEALTH_PATH)
    workflow = fetch_update_workflow_health()
    provenance = official_frame_status(prices)
    publication = manifest.get("publication", {}) if isinstance(manifest, dict) else {}
    tournament = manifest.get("tournament", {}) if isinstance(manifest, dict) else {}
    archive = manifest.get("archive", {}) if isinstance(manifest, dict) else {}

    st.markdown("### Current status")
    first = st.columns(4)
    first[0].metric("Published market", _timestamp(publication.get("model_generated_at_utc")))
    first[1].metric("Last score check", _timestamp(publication.get("last_checked_at_utc")))
    first[2].metric("Workflow", _status_text(workflow))
    first[3].metric("Data source", str(provenance.get("source") or "Unavailable"))

    adaptive_decision = str(adaptive.get("decision") or "collecting_evidence").replace("_", " ").title()
    second = st.columns(4)
    second[0].metric(
        "Tournament market model",
        str(publication.get("model_version") or "Unavailable"),
    )
    second[1].metric("Simulations", int(tournament.get("number_of_simulations", 0) or 0))
    second[2].metric("Adaptive match layer", adaptive_decision)
    second[3].metric("Archive", str(archive.get("status") or "collecting").title())
    st.caption(
        "Tournament prices use the market simulation model. Adaptive match nudges "
        "remain paused until the comparison guardrail reaches Monitor or Trusted."
    )

    if provenance.get("source") != "GitHub main":
        st.warning("CupMarket is showing its deployed fallback. The saved market remains complete, but the newest GitHub publication could not be read.")
    if str(adaptive.get("decision") or "") == "rollback":
        st.warning(str(adaptive.get("message") or "Adaptive adjustments are disabled by the rollback guardrail."))
    elif adaptive:
        if str(adaptive.get("decision") or "") == "collecting_evidence":
            st.info(
                "Adaptive match adjustments are paused while the comparison "
                "sample is still being collected. Baseline forecasts remain active."
            )
        else:
            st.info(
                str(
                    adaptive.get("message")
                    or "Adaptive comparison remains inside its published guardrail."
                )
            )

    with st.expander("Publication details", expanded=False):
        details = {
            "GitHub snapshot": provenance.get("commit"),
            "Publication status": publication.get("status"),
            "Bracket mode": publication.get("bracket_mode"),
            "Completed matches": tournament.get("matches_finished"),
            "Tracked countries": tournament.get("teams_tracked"),
            "Adaptive comparison sample": adaptive.get("comparison_sample_size"),
            "Latest workflow update": _timestamp(workflow.get("updated_at")),
        }
        st.dataframe(
            pd.DataFrame([{"Field": key, "Value": value if value not in {None, ""} else "Unavailable"} for key, value in details.items()]),
            hide_index=True,
            use_container_width=True,
        )
        if workflow.get("url"):
            st.link_button("Open update workflow", str(workflow["url"]))
