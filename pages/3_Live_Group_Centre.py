from pathlib import Path

import streamlit as st

from features.group_centre_page import render_page

st.set_page_config(
    page_title="CupMarket Live Group Centre",
    page_icon="◉",
    layout="wide",
)

ROOT = Path(__file__).resolve().parents[1]
for stylesheet in [
    ROOT / "assets" / "product.css",
    ROOT / "assets" / "group_tools.css",
]:
    if stylesheet.exists():
        st.markdown(
            f"<style>{stylesheet.read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True,
        )

render_page(ROOT)
