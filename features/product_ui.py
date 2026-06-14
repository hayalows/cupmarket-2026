from __future__ import annotations

from pathlib import Path

import streamlit as st

PROJECT_OWNER = "Papa Kojo Mensah"
PROJECT_ALIAS = "Iconka"
PROJECT_REPOSITORY = "https://github.com/hayalows/cupmarket-2026"


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
    cards = "".join(
        f'''
        <div class="cm-guide-step">
            <span>{index}</span>
            <div><strong>{step_title}</strong><p>{step_body}</p></div>
        </div>
        '''
        for index, (step_title, step_body) in enumerate(steps, start=1)
    )
    st.markdown(
        f'''
        <div class="cm-guide">
            <div class="cm-guide-copy">
                <div class="cm-project-label">How to use this page</div>
                <h2>{title}</h2>
                <p>{description}</p>
            </div>
            <div class="cm-guide-grid">{cards}</div>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def render_live_vs_official_note() -> None:
    st.markdown(
        '''
        <div class="cm-state-note">
            <div><strong>Live interpretation</strong><span>Scores, provisional tables and in-play projections can change whenever the feed refreshes.</span></div>
            <div><strong>Published market</strong><span>Ratings, tournament probabilities and country prices change only after the final whistle and the next successful model run.</span></div>
        </div>
        ''',
        unsafe_allow_html=True,
    )


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
