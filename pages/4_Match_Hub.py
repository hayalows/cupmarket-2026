import streamlit as st

from features.live_match_data import should_auto_refresh
from features.match_hub_v2 import inject_styles, load_match_hub_data, render_match_hub
from features.product_ui import render_project_footer, render_specialist_sidebar

st.set_page_config(
    page_title="CupMarket Fixtures & Results",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="auto",
)

inject_styles()
render_specialist_sidebar("match_hub")


def _apply_match_deep_link() -> None:
    requested_view = st.query_params.get("view")
    requested_match = st.query_params.get("match_id")
    applied = False

    if requested_view in {"Live", "Results", "Upcoming"}:
        st.session_state["cupmarket_match_hub_view"] = requested_view
        applied = True

    if requested_match is not None:
        try:
            st.session_state["cupmarket_match_hub_match_id"] = int(requested_match)
            applied = True
        except (TypeError, ValueError):
            pass

    if applied:
        st.query_params.clear()


_apply_match_deep_link()


def _render(data: dict, refresh_label: str) -> None:
    render_match_hub(data)
    st.caption(refresh_label)


@st.fragment(run_every="45s")
def render_active_match_hub() -> None:
    data = load_match_hub_data()
    if not should_auto_refresh(data["matches"]):
        st.rerun()
    _render(data, "Live checks run every 45 seconds while match activity is possible.")


@st.fragment(run_every="5m")
def render_idle_match_hub() -> None:
    data = load_match_hub_data()
    if should_auto_refresh(data["matches"]):
        st.rerun()
    _render(data, "No match is active. CupMarket checks again every five minutes.")


initial_data = load_match_hub_data()
if should_auto_refresh(initial_data["matches"]):
    render_active_match_hub()
else:
    render_idle_match_hub()

render_project_footer()
