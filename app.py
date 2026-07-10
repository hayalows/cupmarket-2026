from __future__ import annotations

from pathlib import Path

import streamlit as st

from features.product_ui import (
    PROJECT_REPOSITORY,
    inject_styles,
    render_project_credit,
)

ROOT = Path(__file__).resolve().parent

st.set_page_config(
    page_title="CupMarket 2026",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="auto",
)

inject_styles(ROOT)

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
    st.markdown('<div class="cm-side-label">Main</div>', unsafe_allow_html=True)
    st.page_link("pages/Tournament_Pulse.py", label="Overview")
    st.page_link("pages/7_Tournament_Path.py", label="Countries")
    st.page_link("pages/4_Match_Hub.py", label="Matches")
    st.page_link("pages/8_Bracket_View.py", label="Bracket")

    with st.expander("Tools", expanded=False):
        st.page_link("pages/12_Tournament_Simulator.py", label="Simulator")
        st.page_link("pages/11_Tournament_Insights.py", label="Analysis")
        st.page_link("pages/9_Model_Health.py", label="System Health")
        st.page_link("pages/13_Tournament_Archive.py", label="Archive")

    with st.expander("About", expanded=False):
        render_project_credit(compact=True)
        st.link_button("View the project on GitHub", PROJECT_REPOSITORY)

st.switch_page("pages/Tournament_Pulse.py")
