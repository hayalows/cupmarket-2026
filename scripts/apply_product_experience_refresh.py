from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Expected text was not found in {path}: {old[:80]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_once(path: Path, marker: str, addition: str) -> None:
    text = path.read_text(encoding="utf-8")
    if addition.strip() in text:
        return
    if marker not in text:
        raise RuntimeError(f"Expected marker was not found in {path}: {marker[:80]!r}")
    path.write_text(text.replace(marker, marker + addition, 1), encoding="utf-8")


def patch_app() -> None:
    path = ROOT / "app.py"

    replace_once(
        path,
        "import streamlit as st\n\nst.set_page_config(",
        "import streamlit as st\n\nfrom features.product_ui import (\n"
        "    render_live_vs_official_note,\n"
        "    render_project_credit,\n"
        "    render_project_footer,\n"
        "    render_start_here,\n"
        ")\n\nst.set_page_config(",
    )

    replace_once(
        path,
        'PRODUCT_UI_VERSION = "1.0"\nPRODUCT_CSS_PATH = APP_ROOT / "assets" / "product.css"',
        'PRODUCT_UI_VERSION = "2.0"\nPRODUCT_CSS_PATHS = [\n'
        '    APP_ROOT / "assets" / "product.css",\n'
        '    APP_ROOT / "assets" / "group_tools.css",\n'
        ']',
    )

    replace_once(
        path,
        "def inject_product_styles() -> None:\n"
        "    if PRODUCT_CSS_PATH.exists():\n"
        "        css = PRODUCT_CSS_PATH.read_text(encoding=\"utf-8\")\n"
        "        st.markdown(f\"<style>{css}</style>\", unsafe_allow_html=True)",
        "def inject_product_styles() -> None:\n"
        "    for stylesheet in PRODUCT_CSS_PATHS:\n"
        "        if stylesheet.exists():\n"
        "            css = stylesheet.read_text(encoding=\"utf-8\")\n"
        "            st.markdown(f\"<style>{css}</style>\", unsafe_allow_html=True)",
    )

    replace_once(
        path,
        '                <span>World Cup intelligence</span>',
        '                <span>World Cup intelligence project</span>',
    )

    replace_once(
        path,
        "    page = st.radio(\n"
        "        \"Choose a page\",\n"
        "        list(NAV_LABELS),\n"
        "        format_func=lambda item: NAV_LABELS[item],\n"
        "        label_visibility=\"collapsed\",\n"
        "    )\n\n"
        "    st.markdown(\n"
        "        '<div class=\"cm-side-label\">System status</div>',",
        "    page = st.radio(\n"
        "        \"Choose a page\",\n"
        "        list(NAV_LABELS),\n"
        "        format_func=lambda item: NAV_LABELS[item],\n"
        "        label_visibility=\"collapsed\",\n"
        "    )\n\n"
        "    st.markdown(\n"
        "        '<div class=\"cm-side-label\">Live tools</div>',\n"
        "        unsafe_allow_html=True,\n"
        "    )\n"
        "    st.page_link(\"pages/1_Match_Intelligence.py\", label=\"Match Intelligence\", icon=\"⚽\")\n"
        "    st.page_link(\"pages/2_Qualification_Lab.py\", label=\"Qualification Lab\", icon=\"◇\")\n"
        "    st.page_link(\"pages/3_Live_Group_Centre.py\", label=\"Live Group Centre\", icon=\"◉\")\n\n"
        "    st.markdown(\n"
        "        '<div class=\"cm-side-label\">System status</div>',",
    )

    replace_once(
        path,
        '    st.caption("Data provided by football-data.org")',
        '    st.caption("Match data provided by football-data.org")\n'
        '    render_project_credit(compact=True)',
    )

    replace_once(
        path,
        '    render_section_heading(\n        "Market leaders",',
        '    render_start_here()\n\n'
        '    render_section_heading(\n        "Market leaders",',
    )

    replace_once(
        path,
        '    if st.button(\n        "Refresh score cache",',
        '    render_live_vs_official_note()\n\n'
        '    if st.button(\n        "Refresh live scores",',
    )

    replace_once(
        path,
        '        "Last successful automatic update",',
        '        "Last successful run",',
    )
    replace_once(
        path,
        '        "Last failed update",',
        '        "Last failed run",',
    )

    replace_once(
        path,
        "### Current meaning of “live”\n\n"
        "- Scores can refresh from the API every 60 seconds.\n"
        "- Saved model probabilities update after the post-match pipeline runs.\n"
        "- Tournament prices update after the simulator runs.\n"
        "- In-play probabilities based on score and minute are not part of this version yet.",
        "### During a live match\n\n"
        "- Refreshing a live page requests the latest score state from the API.\n"
        "- Match Intelligence compares the current-score projection with the original pre-match forecast.\n"
        "- Qualification Lab switches to provisional standings and in-play qualification estimates.\n"
        "- Live Group Centre follows simultaneous matches and shows what the next goal could change.\n\n"
        "### After the final whistle\n\n"
        "The official Elo ratings, tournament probabilities and country prices update after the automated model pipeline processes the completed match. Live estimates are clearly separated from the official market.",
    )

    text = path.read_text(encoding="utf-8")
    if not text.rstrip().endswith("render_project_footer()"):
        path.write_text(text.rstrip() + "\n\nrender_project_footer()\n", encoding="utf-8")


def patch_match_page() -> None:
    path = ROOT / "pages" / "1_Match_Intelligence.py"
    replace_once(
        path,
        "from features.match_ui import combine_prediction_sources, render_match_centre",
        "from features.match_ui import combine_prediction_sources, render_match_centre\n"
        "from features.product_ui import (\n"
        "    inject_styles,\n"
        "    render_live_vs_official_note,\n"
        "    render_page_guide,\n"
        "    render_project_footer,\n"
        "    render_specialist_sidebar,\n"
        ")",
    )
    replace_once(
        path,
        "for stylesheet in [\n"
        "    root / \"assets\" / \"product.css\",\n"
        "    root / \"assets\" / \"group_tools.css\",\n"
        "]:\n"
        "    if stylesheet.exists():\n"
        "        st.markdown(\n"
        "            f\"<style>{stylesheet.read_text(encoding='utf-8')}</style>\",\n"
        "            unsafe_allow_html=True,\n"
        "        )",
        "inject_styles(root)\nrender_specialist_sidebar(\"match\")",
    )
    replace_once(
        path,
        "source_columns = st.columns(4)",
        "render_page_guide(\n"
        "    \"Open one match and read it in layers\",\n"
        "    \"Start with the score and timing, then compare the current live state with the saved pre-match forecast.\",\n"
        "    [\n"
        "        (\"Refresh\", \"Request the latest score state.\"),\n"
        "        (\"Choose\", \"Select the fixture you want to inspect.\"),\n"
        "        (\"Compare\", \"Read live probabilities against the original forecast.\"),\n"
        "    ],\n"
        ")\n"
        "render_live_vs_official_note()\n\n"
        "source_columns = st.columns(4)",
    )
    append_once(path, "render_match_centre(matches, predictions, prices)", "\nrender_project_footer()")


def patch_qualification_page() -> None:
    path = ROOT / "pages" / "2_Qualification_Lab.py"
    replace_once(
        path,
        "from features.qualification_ui import render_qualification_lab",
        "from features.qualification_ui import render_qualification_lab\n"
        "from features.product_ui import (\n"
        "    inject_styles,\n"
        "    render_live_vs_official_note,\n"
        "    render_page_guide,\n"
        "    render_project_footer,\n"
        "    render_specialist_sidebar,\n"
        ")",
    )
    replace_once(
        path,
        "for stylesheet in [\n"
        "    root / \"assets\" / \"product.css\",\n"
        "    root / \"assets\" / \"group_tools.css\",\n"
        "]:\n"
        "    if stylesheet.exists():\n"
        "        st.markdown(\n"
        "            f\"<style>{stylesheet.read_text(encoding='utf-8')}</style>\",\n"
        "            unsafe_allow_html=True,\n"
        "        )",
        "inject_styles(root)\nrender_specialist_sidebar(\"qualification\")",
    )
    replace_once(
        path,
        "source_columns = st.columns(4)",
        "render_page_guide(\n"
        "    \"See what the next result changes\",\n"
        "    \"Before kickoff, compare a win, draw or loss. During play, the page automatically changes to the provisional live view.\",\n"
        "    [\n"
        "        (\"Select\", \"Choose the country you care about.\"),\n"
        "        (\"Run\", \"Calculate its qualification paths.\"),\n"
        "        (\"Read\", \"Compare top-two and best-third routes.\"),\n"
        "    ],\n"
        ")\n"
        "render_live_vs_official_note()\n\n"
        "source_columns = st.columns(4)",
    )
    append_once(
        path,
        '    {"pending_finished_matches": freshness["pending_model_updates"]},\n)',
        "\nrender_project_footer()",
    )


def patch_group_page() -> None:
    path = ROOT / "pages" / "3_Live_Group_Centre.py"
    replace_once(
        path,
        "from features.group_centre_page import render_page",
        "from features.group_centre_page import render_page\n"
        "from features.product_ui import (\n"
        "    inject_styles,\n"
        "    render_project_footer,\n"
        "    render_specialist_sidebar,\n"
        ")",
    )
    replace_once(
        path,
        "for stylesheet in [\n"
        "    ROOT / \"assets\" / \"product.css\",\n"
        "    ROOT / \"assets\" / \"group_tools.css\",\n"
        "]:\n"
        "    if stylesheet.exists():\n"
        "        st.markdown(\n"
        "            f\"<style>{stylesheet.read_text(encoding='utf-8')}</style>\",\n"
        "            unsafe_allow_html=True,\n"
        "        )",
        "inject_styles(ROOT)\nrender_specialist_sidebar(\"group\")",
    )
    replace_once(
        path,
        "render_page(ROOT)",
        "render_page(ROOT)\nrender_project_footer()",
    )


def patch_group_centre_page() -> None:
    path = ROOT / "features" / "group_centre_page.py"
    replace_once(
        path,
        "from features.live_group_view import render_projection, render_provisional",
        "from features.live_group_view import render_projection, render_provisional\n"
        "from features.product_ui import render_live_vs_official_note, render_page_guide",
    )
    replace_once(
        path,
        "    render_header(data[\"source\"], data[\"metadata\"])\n\n"
        "    if matches.empty:",
        "    render_header(data[\"source\"], data[\"metadata\"])\n"
        "    render_page_guide(\n"
        "        \"Follow the group as one connected system\",\n"
        "        \"Use this page when two matches can change the same table at the same time.\",\n"
        "        [\n"
        "            (\"Pick a country\", \"The page finds its group and related match.\"),\n"
        "            (\"Refresh\", \"Bring in the latest scores before reading the table.\"),\n"
        "            (\"Project\", \"Estimate the final group outcome from the current score.\"),\n"
        "        ],\n"
        "    )\n"
        "    render_live_vs_official_note()\n\n"
        "    if matches.empty:",
    )


def patch_feature_copy() -> None:
    path = ROOT / "features" / "match_ui.py"
    replace_once(path, '        "Refresh score cache",', '        "Refresh live scores",')
    replace_once(path, '        "Match status",', '        "Show matches",')
    replace_once(
        path,
        "    st.dataframe(match_display, use_container_width=True, hide_index=True)",
        "    with st.expander(\"Browse all fixtures\", expanded=False):\n"
        "        st.dataframe(match_display, use_container_width=True, hide_index=True)",
    )
    replace_once(path, '    st.markdown("### Open a matchup")', '    st.markdown("### Choose a match")')
    replace_once(
        path,
        '    st.caption("Choose a match to view its own intelligence page.")',
        '    st.caption("The detailed view below keeps the most useful information in one place.")',
    )

    path = ROOT / "features" / "qualification_ui.py"
    replace_once(path, '    st.markdown("### Win, draw or lose")', '    st.markdown("### Your country’s route")')
    replace_once(
        path,
        '        "Run qualification scenarios",',
        '        "Compare win, draw and loss",',
    )

    path = ROOT / "features" / "live_qualification_ui.py"
    replace_once(
        path,
        '    st.warning("Live qualification mode is active. Current scores are treated as provisional results; the trained model itself is not being retrained.")',
        '    st.info("Live mode is active. Current scores shape this provisional view; the official model and country prices remain unchanged until the match is final.")',
    )
    replace_once(path, '    st.markdown("#### If all live matches ended now")', '    st.markdown("#### Table if the live scores held")')
    replace_once(path, '        st.markdown("#### Live qualification projection")', '        st.markdown("#### Projection from the current score")')

    path = ROOT / "features" / "group_centre.py"
    replace_once(path, '    if st.button("Refresh live scores"):', '    if st.button("Refresh live scores", use_container_width=True):')

    path = ROOT / "features" / "live_group_view.py"
    replace_once(path, '        "Run live qualification projection",', '        "Update live projection",')


def main() -> None:
    patch_app()
    patch_match_page()
    patch_qualification_page()
    patch_group_page()
    patch_group_centre_page()
    patch_feature_copy()
    print("CupMarket product experience refresh applied.")


if __name__ == "__main__":
    main()
