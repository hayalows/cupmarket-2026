from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label} anchor, found {count}.")
    return text.replace(old, new, 1)


def patch_qualification_ui() -> None:
    path = Path("features/qualification_ui.py")
    text = path.read_text(encoding="utf-8")
    marker = "from features.live_qualification_ui import render_live_group"
    if marker in text:
        return

    text = replace_once(
        text,
        "from features.live_group_table import build_live_group_table\n",
        "from features.live_group_table import build_live_group_table\n"
        "from features.live_qualification_ui import render_live_group\n",
        "qualification import",
    )
    text = replace_once(
        text,
        '        "Condition the next group match and simulate what each result means "\n'
        '        "for qualification."\n',
        '        "Before kickoff, compare a win, draw or loss. During a live group "\n'
        '        "match, the page switches to provisional standings and live projections."\n',
        "qualification introduction",
    )
    strength_anchor = '''    strength = (
        dict(zip(prices["team"], prices["cupmarket_price"]))
        if not prices.empty
        else {}
    )

    try:
'''
    strength_replacement = '''    strength = (
        dict(zip(prices["team"], prices["cupmarket_price"]))
        if not prices.empty
        else {}
    )

    if render_live_group(matches, predictions, prices, selected_team):
        return

    try:
'''
    text = replace_once(
        text,
        strength_anchor,
        strength_replacement,
        "live qualification switch",
    )
    path.write_text(text, encoding="utf-8")


def patch_match_ui() -> None:
    path = Path("features/match_ui.py")
    text = path.read_text(encoding="utf-8")
    marker = "from features.live_qualification_ui import render_live_match"
    if marker in text:
        return

    text = replace_once(
        text,
        "import streamlit as st\n\n",
        "import streamlit as st\n\n"
        "from features.live_qualification_ui import render_live_match\n",
        "match import",
    )
    anchor = '''    if prediction_row.empty or pd.isna(prediction_row.get("prob_home_win")):
        st.info("A saved probability forecast is not available for this match yet.")
        return

    confidence_label, top_probability, separation = prediction_confidence(
'''
    replacement = '''    live_projection_shown = render_live_match(
        matches,
        prediction_outputs,
        prices,
        int(selected_match_id),
    )
    if live_projection_shown:
        st.markdown("#### Original pre-match forecast")

    if prediction_row.empty or pd.isna(prediction_row.get("prob_home_win")):
        st.info("A saved probability forecast is not available for this match yet.")
        return

    confidence_label, top_probability, separation = prediction_confidence(
'''
    text = replace_once(text, anchor, replacement, "live match projection")
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_qualification_ui()
    patch_match_ui()
    print("Live qualification interface patch applied.")
