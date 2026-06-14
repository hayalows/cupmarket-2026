from __future__ import annotations

from pathlib import Path

import streamlit as st

PROJECT_OWNER = "Papa Kojo Mensah"
PROJECT_ALIAS = "Iconka"
PROJECT_REPOSITORY = "https://github.com/hayalows/cupmarket-2026"


def inject_styles(root: Path) -> None:
    for stylesheet in [
        root / "assets" / "product.css",
        root / "assets" / "group_tools.css",
        root / "assets" / "pulse_v3.css",
    ]:
        if stylesheet.exists():
            st.markdown(
                f"<style>{stylesheet.read_text(encoding='utf-8')}</style>",
                unsafe_allow_html=True,
            )


def render_project_credit(compact: bool = False) -> None:
    class_name = "cm-project-card compact" if compact else "cm-project-card"
    st.markdown(
        f'''
        <div class="{class_name}">
            <div class="cm-project-label">Independent project</div>
            <strong>CupMarket 2026</strong>
            <p>Designed and built by {PROJECT_OWNER} ({PROJECT_ALIAS}).</p>
            <span>Working prototype · Testing and feedback are welcome</span>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def render_specialist_sidebar(active_page: str) -> None:
    with st.sidebar:
        st.markdown(
            '''
            <div class="cm-side-brand">
                <div class="cm-mark">CM</div>
                <div>
                    <strong>CupMarket</strong>
                    <span>World Cup intelligence project</span>
                </div>
            </div>
            ''',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="cm-side-label">Explore</div>', unsafe_allow_html=True)
        st.page_link("pages/Tournament_Pulse.py", label="Tournament Pulse", icon="🏠")
        st.page_link("pages/4_Match_Hub.py", label="Match Hub", icon="⚽")
        st.page_link("pages/1_Match_Intelligence.py", label="Live Match Room", icon="🎯")
        st.page_link("pages/2_Qualification_Lab.py", label="Qualification Lab", icon="🧭")
        st.page_link("pages/3_Live_Group_Centre.py", label="Live Group Centre", icon="📋")
        st.page_link("pages/5_Market_Story.py", label="Market Story", icon="📈")
        st.page_link("pages/6_Analytics_Dashboard.py", label="Full Analytics", icon="📊")
        st.markdown('<div class="cm-side-label">About this build</div>', unsafe_allow_html=True)
        render_project_credit(compact=True)
        st.link_button("View the project on GitHub", PROJECT_REPOSITORY)


def render_page_guide(title: str, description: str, steps: list[tuple[str, str]]) -> None:
    with st.expander(f"How to use this page · {title}", expanded=False):
        st.caption(description)
        columns = st.columns(len(steps))
        for index, (column, step) in enumerate(zip(columns, steps), start=1):
            with column:
                st.markdown(f"**{index}. {step[0]}**")
                st.caption(step[1])


def render_live_vs_official_note() -> None:
    with st.expander("Live interpretation vs published market", expanded=False):
        st.markdown(
            "**Live interpretation:** scores, provisional tables and in-play projections "
            "can change whenever the score feed refreshes.\n\n"
            "**Published market:** ratings, tournament probabilities and country prices "
            "change only after full time and the next successful model run."
        )


def render_data_diagnostics(
    *,
    score_source: str,
    score_refreshed: str,
    model_generated: str,
    pending_updates: int | None = None,
    warning: str | None = None,
    load_time_ms: float | None = None,
    refresh_key: str | None = None,
    token_configured: bool | None = None,
    feed_state: str | None = None,
    requests_remaining: str | None = None,
) -> None:
    pending_text = (
        f" · {pending_updates} result{'s' if pending_updates != 1 else ''} awaiting model"
        if pending_updates is not None
        else ""
    )
    st.caption(
        f"Scores refreshed {score_refreshed} · Published model {model_generated}{pending_text}"
    )
    with st.expander("Data freshness and system details", expanded=False):
        columns = st.columns(4 if pending_updates is not None else 3)
        columns[0].metric("Score source", score_source)
        columns[1].metric("Score feed refreshed", score_refreshed)
        columns[2].metric("Model generated", model_generated)
        if pending_updates is not None:
            columns[3].metric("Results awaiting model", pending_updates)

        detail_parts = []
        if token_configured is not None:
            detail_parts.append(
                "Streamlit token configured" if token_configured else "Streamlit token missing"
            )
        if feed_state:
            detail_parts.append(f"Feed state: {feed_state.replace('_', ' ')}")
        if requests_remaining is not None:
            detail_parts.append(f"Provider requests remaining: {requests_remaining}")
        if detail_parts:
            st.caption(" · ".join(detail_parts))
        if load_time_ms is not None:
            st.caption(f"Page data prepared in {load_time_ms:.0f} ms on this rerun.")
        if refresh_key and st.button(
            "Refresh live scores",
            key=refresh_key,
            help="Clears only the football-feed cache and requests the latest match states.",
        ):
            from features.live_match_data import clear_live_match_cache

            clear_live_match_cache()
            st.rerun()
        if warning:
            st.warning(warning)


def render_start_here() -> None:
    st.switch_page("pages/Tournament_Pulse.py")


def render_project_footer() -> None:
    st.markdown(
        f'''
        <div class="cm-project-footer">
            <div>
                <strong>CupMarket 2026</strong>
                <span>An independent World Cup analytics project by {PROJECT_OWNER} ({PROJECT_ALIAS}).</span>
            </div>
            <div class="cm-footer-meta">Working prototype · Virtual market · No real-money wagering</div>
        </div>
        ''',
        unsafe_allow_html=True,
    )
