import streamlit as st

from features.live_match_data import format_source_time, load_matches
from features.overview_v3 import render_overview_v3
from features.product_ui import inject_styles, render_project_footer, render_specialist_sidebar
from features.tournament_data import DATA_DIR, load_static_data

st.set_page_config(
    page_title="CupMarket Tournament Pulse",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="auto",
)

root = DATA_DIR.parent
inject_styles(root)
render_specialist_sidebar("overview")

matches, score_metadata = load_matches(DATA_DIR / "world_cup_2026_matches_latest.csv")
prices = load_static_data()["prices"]

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026 · Tournament pulse</div>
        <h1>See what happened. Open what matters.</h1>
        <p>Results, live matches, upcoming fixtures and country-market movement now connect directly to the detail that explains them.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)

if score_metadata.get("warning"):
    st.warning(score_metadata["warning"] + " Showing the latest saved match snapshot.")

render_overview_v3(matches=matches, prices=prices, metadata={})
st.caption(
    f"Score source: {score_metadata.get('source', 'Unknown')} · refreshed "
    f"{format_source_time(score_metadata.get('fetched_at_utc'))}"
)
render_project_footer()
