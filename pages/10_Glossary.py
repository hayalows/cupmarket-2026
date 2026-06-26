import streamlit as st

from features.product_ui import inject_styles, render_project_footer, render_specialist_sidebar
from features.tournament_data_v2 import DATA_DIR

st.set_page_config(page_title="CupMarket Guide", page_icon="ℹ️", layout="wide")

inject_styles(DATA_DIR.parent)
render_specialist_sidebar("guide")

st.title("CupMarket Guide")
st.write("A simple guide to the words and labels used inside the app.")

st.info(
    "CupMarket is a virtual tournament intelligence project. It is not betting. "
    "Prices, probabilities and projections are model outputs for analysis and learning."
)

terms = [
    ("Confirmed", "The fixture or result exists in the official feed."),
    ("Projected", "The model's best current estimate. It can change after new results."),
    ("Part-confirmed", "One side or slot is known, but the full fixture is not locked."),
    ("Price", "A virtual value based on the country's possible tournament outcomes."),
    ("Model run", "A fresh calculation after new match data is processed."),
    ("Reach R32", "The chance that a country reaches the Round of 32."),
    ("Market move", "How much a country's virtual price changed after a model update."),
    ("Live interpretation", "A temporary view based on the current score state."),
    ("Published market", "The official saved CupMarket output after the model finishes."),
]

for title, body in terms:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.write(body)

st.markdown("### Best way to use the app")
st.write("Start from Pulse, open Country for one-team context, then use Bracket when you want the full tournament path.")

render_project_footer()
