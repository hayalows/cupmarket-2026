from __future__ import annotations

from pathlib import Path

import streamlit as st

PROJECT_OWNER = "Papa Kojo Mensah"
PROJECT_ALIAS = "Iconka"
PROJECT_REPOSITORY = "https://github.com/hayalows/cupmarket-2026"


def _inject_navigation_consistency() -> None:
    """Keep the legacy main-app link aligned with the current product language."""
    st.markdown(
        '''
        <style>
        section[data-testid="stSidebar"] a[href*="1_Match_Intelligence"] {
            font-size: 0 !important;
        }
        section[data-testid="stSidebar"] a[href*="1_Match_Intelligence"]::after {
            content: "Live Match Room";
            font-size: 1rem;
            line-height: 1.35;
            color: inherit;
        }
        section[data-testid="stSidebar"] a[href*="1_Match_Intelligence"] [data-testid*="Icon"],
        section[data-testid="stSidebar"] a[href*="1_Match_Intelligence"] span:first-child {
            font-size: 1rem !important;
        }
        </style>
        ''',
        unsafe_allow_html=True,
    )


def inject_styles(root: Path) -> None:
    """Load the shared visual system in a predictable order."""
    for stylesheet in [
        root / "assets" / "product.css",
        root / "assets" / "group_tools.css",
    ]:
        if stylesheet.exists():
            st.markdown(
                f"<style>{stylesheet.read_text(encoding='utf-8')}</style>",
                unsafe_allow_html=True,
            )


def render_project_credit(compact: bool = False) -> None:
    _inject_navigation_consistency()
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
        st.markdown(
            '<div class="cm-side-label">Explore</div>',
            unsafe_allow_html=True,
        )
        st.page_link("app.py", label="Overview", icon="🏠")
        st.page_link(
            "pages/1_Match_Intelligence.py",
            label="Live Match Room",
            icon="⚽",
        )
        st.page_link(
            "pages/2_Qualification_Lab.py",
            label="Qualification Lab",
            icon="🧭",
        )
        st.page_link(
            "pages/3_Live_Group_Centre.py",
            label="Live Group Centre",
            icon="📊",
        )
        st.markdown(
            '<div class="cm-side-label">About this build</div>',
            unsafe_allow_html=True,
        )
        render_project_credit(compact=True)
        st.link_button("View the project on GitHub", PROJECT_REPOSITORY)


def render_page_guide(
    title: str,
    description: str,
    steps: list[tuple[str, str]],
) -> None:
    """Keep onboarding available without placing it before the primary task."""
    with st.expander(f"How to use this page · {title}", expanded=False):
        st.caption(description)
        columns = st.columns(len(steps))
        for index, (column, step) in enumerate(zip(columns, steps), start=1):
            step_title, step_body = step
            with column:
                st.markdown(f"**{index}. {step_title}**")
                st.caption(step_body)


def render_live_vs_official_note() -> None:
    """Explain the two update clocks without consuming the main screen."""
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
) -> None:
    """Place operational telemetry behind a compact disclosure."""
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
        if load_time_ms is not None:
            st.caption(f"Page data prepared in {load_time_ms:.0f} ms on this rerun.")
        if refresh_key and st.button(
            "Refresh live scores",
            key=refresh_key,
            help="Clears the 60-second score cache and requests the latest match states.",
        ):
            st.cache_data.clear()
            st.rerun()
        if warning:
            st.warning(warning)


def render_start_here() -> None:
    st.markdown(
        '''
        <div class="cm-start-here">
            <div class="cm-project-label">Start here</div>
            <h2>Choose the football question you want CupMarket to answer.</h2>
            <p>The main dashboard gives the broad picture. Open a match when you care about what is happening now, use the qualification lab to test outcomes before kickoff, or follow a whole group when simultaneous matches interact.</p>
        </div>
        ''',
        unsafe_allow_html=True,
    )
    columns = st.columns(3)
    with columns[0]:
        st.markdown("**Open a match**")
        st.caption(
            "Live fixtures appear first. Move from the score into outlook, qualification, group effects and market context."
        )
        st.page_link(
            "pages/1_Match_Intelligence.py",
            label="Open Live Match Room",
            icon="⚽",
            use_container_width=True,
        )
    with columns[1]:
        st.markdown("**Test qualification paths**")
        st.caption("See what a win, draw or loss means before kickoff.")
        st.page_link(
            "pages/2_Qualification_Lab.py",
            label="Open Qualification Lab",
            icon="🧭",
            use_container_width=True,
        )
    with columns[2]:
        st.markdown("**Follow a live group**")
        st.caption(
            "Track simultaneous matches, provisional tables and next-goal impact."
        )
        st.page_link(
            "pages/3_Live_Group_Centre.py",
            label="Open Live Group Centre",
            icon="📊",
            use_container_width=True,
        )


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
