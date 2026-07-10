from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content.rstrip() + "\n", encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label}; found {count}.")
    return text.replace(old, new, 1)


def replace_function(text: str, name: str, replacement: str) -> str:
    pattern = re.compile(
        rf"^def {re.escape(name)}\(.*?(?=^def |\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    updated, count = pattern.subn(replacement.rstrip() + "\n\n", text, count=1)
    if count != 1:
        raise RuntimeError(f"Could not replace function {name}; found {count}.")
    return updated


def patch_app() -> None:
    write(
        "app.py",
        '''from __future__ import annotations

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
''',
    )


def patch_product_ui() -> None:
    path = "features/product_ui.py"
    text = read(path)
    replacement = '''def render_specialist_sidebar(active_page: str) -> None:
    """Render the single product navigation used on every Streamlit page."""
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
'''
    text = replace_function(text, "render_specialist_sidebar", replacement)
    write(path, text)


def patch_overview() -> None:
    path = "features/overview_v3.py"
    text = read(path)
    text = text.replace(
        "from features.tournament_simulator import render_tournament_simulator\n",
        "",
    )

    market_route = '''def _go_to_market(team: str) -> None:
    st.session_state["cupmarket_path_requested_team"] = team
    st.session_state["cupmarket_country_requested_section"] = "Market"
    st.switch_page("pages/7_Tournament_Path.py")
'''
    text = replace_function(text, "_go_to_market", market_route)

    stage_explorer = '''def render_stage_explorer(matches: pd.DataFrame, prices: pd.DataFrame) -> None:
    progress = _load_knockout_progress()
    default_stage = _default_stage(matches, progress)
    labels = [_stage_label_from_key(stage_key) for stage_key, _, _ in STAGE_OPTIONS]
    default_index = min(_stage_sort_index(default_stage), len(labels) - 1)

    st.markdown("### Current round")
    st.caption(
        "Choose a round to see its fixtures, decisions and countries. Open Matches, "
        "Countries or Bracket when you need more detail."
    )
    selected_label = st.selectbox(
        "Round",
        labels,
        index=default_index,
        key="cupmarket_pulse_stage_explorer",
    )
    selected_stage = next(
        stage_key
        for stage_key, label, _ in STAGE_OPTIONS
        if label == selected_label
    )

    fixtures = _source_for_stage(matches, progress, selected_stage)
    participants = _stage_participants(fixtures)
    counts = _stage_status_counts(fixtures)
    country_table = _stage_country_table(prices, selected_stage, participants)
    story = _stage_story(selected_stage, fixtures, prices)
    decisions = _stage_decision_tables(fixtures)

    metrics = st.columns(4)
    metrics[0].metric("Fixtures", counts["fixtures"])
    if _normal_stage(selected_stage) == "GROUP_STAGE":
        metrics[1].metric("Live", counts["live"])
        metrics[2].metric("Finished", counts["finished"])
        metrics[3].metric("Countries", len(participants) if participants else len(country_table))
    else:
        metrics[1].metric("Advanced", len(decisions["advanced"]))
        metrics[2].metric("Eliminated", len(decisions["eliminated"]))
        metrics[3].metric("Still to play", len(decisions["pending"]))

    st.info(story)
    _render_stage_decisions(selected_stage, fixtures)
    if _normal_stage(selected_stage) == "LAST_32":
        _render_round_of_16_building(progress)

    focus_view, focus_match_id = _stage_focus_match(fixtures)
    default_team = None
    if participants:
        default_team = participants[0]
    elif not country_table.empty:
        default_team = str(country_table.iloc[0]["Country"])

    action_cols = st.columns(3)
    with action_cols[0]:
        if st.button("View matches", key=f"stage_explorer_matches_{selected_stage}", use_container_width=True):
            _go_to_matches(focus_view, focus_match_id)
    with action_cols[1]:
        if st.button("View bracket", key=f"stage_explorer_bracket_{selected_stage}", use_container_width=True):
            _go_to_bracket(default_team)
    with action_cols[2]:
        if st.button("View countries", key=f"stage_explorer_paths_{selected_stage}", use_container_width=True):
            _go_to_path(default_team)

    fixture_tab, country_tab = st.tabs(["Fixtures", "Countries"])
    with fixture_tab:
        fixture_table = _stage_fixture_table(fixtures)
        if fixture_table.empty:
            st.caption("Official fixtures for this round are not available yet.")
        else:
            st.dataframe(
                fixture_table[["Status", "Fixture", "Score", "Outcome", "Kickoff"]],
                hide_index=True,
                use_container_width=True,
            )
    with country_tab:
        if country_table.empty:
            st.caption("Country data is not available for this round yet.")
        else:
            st.dataframe(country_table, hide_index=True, use_container_width=True)
'''
    text = replace_function(text, "render_stage_explorer", stage_explorer)

    overview = '''def render_overview_v3(matches: pd.DataFrame, prices: pd.DataFrame, metadata: dict) -> None:
    _inject_styles()
    prices = add_rank_movement(prices)
    processed = load_static_data()["processed_ledger"]

    if matches.empty:
        finished = live = upcoming = pd.DataFrame()
    else:
        finished = matches[matches["status"].isin(["FINISHED", "AWARDED"])].sort_values(
            "utc_date", ascending=False
        )
        live = matches[matches["status"].isin(["IN_PLAY", "PAUSED"])].sort_values("utc_date")
        upcoming = matches[matches["status"].isin(["TIMED", "SCHEDULED"])].sort_values("utc_date")

    leader = prices.sort_values("cupmarket_price", ascending=False).iloc[0] if not prices.empty else pd.Series(dtype=object)
    default_team = str(leader.get("team")) if not leader.empty else "Ghana"
    predictions = metadata.get("predictions") if isinstance(metadata, dict) else pd.DataFrame()
    adaptive_ratings = metadata.get("adaptive_ratings") if isinstance(metadata, dict) else pd.DataFrame()

    round_tab, market_tab, today_tab = st.tabs(["Current round", "Market", "Today"])
    with round_tab:
        render_stage_explorer(matches, prices)
    with market_tab:
        render_market_board(
            prices,
            predictions=predictions,
            adaptive_ratings=adaptive_ratings,
        )
    with today_tab:
        render_todays_story(matches, prices)
        render_start_here_panel(default_team)

    render_official_data_caption(prices)
    st.caption(
        f"Tournament feed: {len(finished)} finished · {len(live)} live · "
        f"{len(upcoming)} upcoming. Model ledger: {len(processed)} processed results."
    )
'''
    text = replace_function(text, "render_overview_v3", overview)
    write(path, text)


def patch_main_page_copy() -> None:
    path = "features/tournament_pulse_page.py"
    text = read(path)
    old = '''        <div class="cm-hero">
            <div class="cm-eyebrow">CupMarket 2026 · Tournament pulse</div>
            <h1>See what happened. Open what matters.</h1>
            <p>Results, live matches, upcoming fixtures and country-market movement now connect directly to the detail that explains them.</p>
        </div>
'''
    new = '''        <div class="cm-hero">
            <div class="cm-eyebrow">CupMarket 2026</div>
            <h1>Tournament overview</h1>
            <p>See the current round, latest results, upcoming fixtures and market position. Open a specialist page for the full detail.</p>
        </div>
'''
    text = replace_once(text, old, new, "overview hero")
    write(path, text)

    path = "features/match_hub_v2.py"
    text = read(path)
    old = '''        <div class="cm-hero">
            <div class="cm-eyebrow">CupMarket 2026 · Fixtures & results</div>
            <h1>Every match, one clear path.</h1>
            <p>Move from live action to completed-result review or the next fixture without learning a different navigation system.</p>
        </div>
'''
    new = '''        <div class="cm-hero">
            <div class="cm-eyebrow">CupMarket 2026</div>
            <h1>Matches and results</h1>
            <p>Follow live scores, review completed forecasts, or open the next scheduled fixture.</p>
        </div>
'''
    text = replace_once(text, old, new, "matches hero")
    write(path, text)

    path = "pages/1_Match_Intelligence.py"
    text = read(path).replace(
        "<h1>Open the match. Understand the consequences.</h1>",
        "<h1>Match intelligence</h1>",
    )
    write(path, text)

    path = "pages/2_Qualification_Lab.py"
    text = read(path).replace(
        "<h1>What does the next result change?</h1>",
        "<h1>Qualification scenarios</h1>",
    )
    write(path, text)


def patch_country_page() -> None:
    path = "features/tournament_path_page.py"
    text = read(path)
    replacement = '''def _render_country_page_v2() -> None:
    st.markdown(
        '''
        <div class="cm-hero">
            <div class="cm-eyebrow">CupMarket 2026</div>
            <h1>Country profile</h1>
            <p>Select one country to see its status, next match, tournament path, price movement and fixture history.</p>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    data = load_tournament_path_data()
    summary = tournament_summary(data)
    st.caption(
        f"Tournament stage: {summary['current_stage']} · "
        f"Bracket: {summary['bracket_status']}"
    )

    teams = available_teams(data)
    if not teams:
        st.warning(
            "Country data is not available yet. Matches, Bracket and System Health remain available."
        )
        return

    with st.expander("How to use Countries", expanded=False):
        st.write(
            "Overview gives the fast answer. Path shows this country's stage chances. "
            "Market explains its CM value. Fixtures contains only this country's matches."
        )

    requested = st.session_state.pop("cupmarket_path_requested_team", None)
    default_team = preferred_team(teams, requested, data["prices"])
    if st.session_state.get("cupmarket_path_team") not in teams:
        st.session_state["cupmarket_path_team"] = default_team
    team = st.selectbox("Country", teams, key="cupmarket_path_team")

    selected = team_summary(data, team)
    price = selected["price"]
    path = selected["path"]
    latest_fixture_result = _latest_finished_fixture(selected["fixtures"])
    result_state = _team_result_state(latest_fixture_result, team)
    reach_label, reach_value = _reach_metric_for_state(
        price,
        path,
        latest_fixture_result,
    )

    st.markdown(f"## {team}")
    cards = st.columns(4)
    cards[0].metric(
        "Current price",
        _number(price.get("cupmarket_price"), suffix=" CM") if not price.empty else "—",
    )
    cards[1].metric(
        "Status",
        result_state.get("status")
        or (status_label(path.get("fixture_status")) if not path.empty else "Awaiting path data"),
    )
    cards[2].metric(reach_label, _percent(reach_value))
    cards[3].metric(
        "Champion chance",
        _percent(price.get("prob_champion")) if not price.empty else "—",
    )

    sections = ["Overview", "Path", "Market", "Fixtures"]
    requested_section = st.session_state.pop("cupmarket_country_requested_section", None)
    if requested_section in sections:
        st.session_state["cupmarket_country_section"] = requested_section
    elif st.session_state.get("cupmarket_country_section") not in sections:
        st.session_state["cupmarket_country_section"] = "Overview"

    section = st.segmented_control(
        "Country view",
        sections,
        key="cupmarket_country_section",
        selection_mode="single",
        label_visibility="collapsed",
    ) or "Overview"

    if section == "Overview":
        _render_path_message(path, selected["opponents"], latest_fixture_result, team)
        _render_next_knockout_slot(data["progress"], team)
        st.caption("This view contains the current status, next match and headline probabilities.")
    elif section == "Path":
        st.markdown("### Tournament path")
        _render_stage_probability_ladder(price, team)
        st.caption(
            "These probabilities belong to the selected country. Open Bracket to see the full tournament structure."
        )
        st.page_link("pages/8_Bracket_View.py", label="View the full bracket")
    elif section == "Market":
        render_market_explanation(
            team=team,
            price=price,
            movement=selected["movement"],
            progress=data["progress"],
            adaptive_ratings=data.get("adaptive_ratings", pd.DataFrame()),
            manifest=data.get("publication_manifest", {}),
        )
        _render_market_reaction(
            selected["movement"],
            data["history"],
            team,
            price,
            selected.get("latest_movement", pd.Series(dtype=object)),
        )
    else:
        st.markdown("### Fixture history")
        fixture_display = _team_fixture_table(selected["fixtures"], team)
        if fixture_display.empty:
            st.info("No confirmed fixture is available for this country yet.")
        else:
            st.dataframe(fixture_display, hide_index=True, use_container_width=True)
        st.caption("This table contains only the selected country's fixtures.")

    render_official_data_caption(data["prices"], label="Country market")
    with st.expander("Definitions", expanded=False):
        st.markdown(
            "**Projected path** means future results can still change the opponent.\n\n"
            "**Slot confirmed** means the country's bracket position is fixed, but the opponent is not final.\n\n"
            "**Fixture confirmed** means both countries are known.\n\n"
            "**Published market** changes after completed results are processed by the model."
        )
'''
    text = replace_function(text, "_render_country_page_v2", replacement)
    write(path, text)


def patch_pages() -> None:
    write(
        "pages/8_Bracket_View.py",
        '''import streamlit as st

from features.bracket_stage_view import render_stage_bracket_view
from features.bracket_view import render_dynamic_bracket_view
from features.product_ui import inject_styles, render_project_footer, render_specialist_sidebar
from features.tournament_data import DATA_DIR
from features.tournament_path_data import load_tournament_path_data, tournament_summary

st.set_page_config(
    page_title="CupMarket Bracket",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="auto",
)

inject_styles(DATA_DIR.parent)
render_specialist_sidebar("bracket")

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026</div>
        <h1>Tournament bracket</h1>
        <p>See confirmed knockout fixtures and the projected slots that are still waiting for official teams.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)

data = load_tournament_path_data()
summary = tournament_summary(data)

metrics = st.columns(4)
metrics[0].metric("Tournament stage", summary["current_stage"])
metrics[1].metric("Bracket status", summary["bracket_status"])
metrics[2].metric("Finished", summary["completed_knockout_matches"])
metrics[3].metric("Live", summary["live_knockout_matches"])

st.info(
    "Stage view is easier on mobile. Full bracket is better on a wide screen. "
    "Confirmed fixtures come from the official feed; projected slots come from the latest model run."
)

stage_tab, full_tab = st.tabs(["Stage view", "Full bracket"])
with stage_tab:
    render_stage_bracket_view(data)
with full_tab:
    render_dynamic_bracket_view(data)

render_project_footer()
''',
    )

    write(
        "pages/12_Tournament_Simulator.py",
        '''import pandas as pd
import streamlit as st

from features.live_match_data import load_matches
from features.product_ui import (
    inject_styles,
    render_project_footer,
    render_specialist_sidebar,
)
from features.tournament_data_v2 import DATA_DIR, load_static_data
from features.tournament_simulator import render_tournament_simulator

st.set_page_config(
    page_title="CupMarket Simulator",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="auto",
)

inject_styles(DATA_DIR.parent)
render_specialist_sidebar("simulator")

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026</div>
        <h1>Scenario simulator</h1>
        <p>Test possible knockout results and compare how they could change advancement chances and CM values. Official data is never changed.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)

matches, _ = load_matches(DATA_DIR / "world_cup_2026_matches_latest.csv")
static = load_static_data()
prices = static.get("prices", pd.DataFrame())
predictions = static.get("latest_predictions", pd.DataFrame())

render_tournament_simulator(matches, prices, predictions)
render_project_footer()
''',
    )

    write(
        "pages/11_Tournament_Insights.py",
        '''import pandas as pd
import streamlit as st

from features.adaptive_ratings import build_adaptive_ratings, render_adaptive_ratings_insights
from features.knockout_readiness import render_knockout_readiness
from features.match_story import render_match_story
from features.model_performance import render_model_performance
from features.product_ui import inject_styles, render_project_footer, render_specialist_sidebar
from features.tournament_data_v2 import DATA_DIR, STATE_DIR, load_static_data
from features.tournament_insights import render_tournament_insights
from features.tournament_path_data import load_tournament_path_data
from features.tournament_timeline import render_tournament_timeline


def _alive_count(prices: pd.DataFrame) -> int:
    if prices.empty:
        return 0
    exit_columns = [
        "prob_group_exit",
        "prob_round_32_exit",
        "prob_round_16_exit",
        "prob_quarter_final_exit",
        "prob_semi_final_exit",
        "prob_runner_up",
    ]
    locked_out = pd.Series(False, index=prices.index)
    for column in exit_columns:
        if column in prices.columns:
            locked_out = locked_out | (
                pd.to_numeric(prices[column], errors="coerce").fillna(0.0) >= 0.999
            )
    champion = pd.to_numeric(prices.get("prob_champion"), errors="coerce").fillna(0.0)
    return int((~locked_out | (champion > 0.0)).sum())


def _knockout_counts(progress: pd.DataFrame) -> tuple[int, int, int]:
    if not isinstance(progress, pd.DataFrame) or progress.empty or "status" not in progress.columns:
        return 0, 0, 0
    statuses = progress["status"].astype(str)
    finished = int(statuses.isin(["FINISHED", "AWARDED"]).sum())
    live = int(statuses.isin(["IN_PLAY", "LIVE", "PAUSED", "SUSPENDED"]).sum())
    upcoming = int(statuses.isin(["TIMED", "SCHEDULED"]).sum())
    return finished, live, upcoming


st.set_page_config(page_title="CupMarket Analysis", page_icon="💡", layout="wide")
inject_styles(DATA_DIR.parent)
render_specialist_sidebar("insights")

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026</div>
        <h1>Model analysis</h1>
        <p>Review forecast performance, match evidence, adaptive research and knockout-model checks. Open Archive for the permanent tournament story and market replay.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)
st.info(
    "Official results are fixed. Forecasts and projected paths can change. "
    "Adaptive ratings remain a research layer until their guardrail is satisfied."
)

static = load_static_data()
path_data = load_tournament_path_data()
prices = static.get("prices", pd.DataFrame())
predictions = static.get("latest_predictions", pd.DataFrame())
tables = path_data.get("group_tables", pd.DataFrame())
movements = path_data.get("movements", pd.DataFrame())
movement_history = path_data.get("movement_history", pd.DataFrame())
if movement_history.empty:
    movement_history = movements
path_status = path_data.get("path_status", pd.DataFrame())
snapshots = path_data.get("snapshots", pd.DataFrame())
progress = path_data.get("progress", pd.DataFrame())
history = static.get("history", pd.DataFrame())
processed_ledger = static.get("processed_ledger", pd.DataFrame())
prediction_ledger = static.get("prediction_ledger", pd.DataFrame())
adaptive_ratings = build_adaptive_ratings(prices, history, processed_ledger)
if prediction_ledger.empty:
    ledger_path = STATE_DIR / "world_cup_prediction_ledger.csv"
    prediction_ledger = pd.read_csv(ledger_path) if ledger_path.exists() else pd.DataFrame()

finished_knockouts, live_knockouts, upcoming_knockouts = _knockout_counts(progress)
stage_cols = st.columns(4)
stage_cols[0].metric("Still alive", _alive_count(prices))
stage_cols[1].metric("Knockout results", finished_knockouts)
stage_cols[2].metric("Live knockouts", live_knockouts)
stage_cols[3].metric("Fixtures ahead", upcoming_knockouts)

st.caption(
    "Choose the analysis question below. Tournament history and market replay are kept in Archive."
)

tabs = st.tabs(
    [
        "Research summary",
        "Match review",
        "Evidence timeline",
        "Model evaluation",
        "Adaptive research",
        "Knockout checks",
    ]
)
with tabs[0]:
    render_tournament_insights(
        prices,
        tables,
        movements,
        path_status,
        snapshots=snapshots,
        prediction_ledger=prediction_ledger,
        progress=progress,
    )
with tabs[1]:
    render_match_story(prediction_ledger, movement_history, processed_ledger)
with tabs[2]:
    render_tournament_timeline(processed_ledger, movement_history)
with tabs[3]:
    render_model_performance()
with tabs[4]:
    render_adaptive_ratings_insights(adaptive_ratings)
with tabs[5]:
    render_knockout_readiness(prices, predictions, path_status)

render_project_footer()
''',
    )

    write(
        "pages/13_Tournament_Archive.py",
        '''import streamlit as st

from features.product_ui import inject_styles, render_project_footer, render_specialist_sidebar
from features.tournament_archive import render_tournament_archive
from features.tournament_data_v2 import DATA_DIR

st.set_page_config(page_title="CupMarket Archive", page_icon="🗂️", layout="wide")
inject_styles(DATA_DIR.parent)
render_specialist_sidebar("archive")

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026</div>
        <h1>Tournament archive</h1>
        <p>Review the permanent tournament record, market replay, saved forecasts and final model verdict.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)

render_tournament_archive()
render_project_footer()
''',
    )

    write(
        "pages/9_Model_Health.py",
        '''import streamlit as st

from features.model_health import render_model_health
from features.product_ui import inject_styles, render_project_footer, render_specialist_sidebar
from features.tournament_data_v2 import DATA_DIR

st.set_page_config(page_title="CupMarket System Health", page_icon="📡", layout="wide")
inject_styles(DATA_DIR.parent)
render_specialist_sidebar("model_health")

st.markdown(
    '''
    <div class="cm-hero">
        <div class="cm-eyebrow">CupMarket 2026</div>
        <h1>System health</h1>
        <p>Check data freshness, publication status, workflow state and model safety controls.</p>
    </div>
    ''',
    unsafe_allow_html=True,
)

render_model_health()
render_project_footer()
''',
    )


def patch_feature_headings() -> None:
    path = "features/model_health.py"
    text = read(path)
    text = replace_once(
        text,
        '    st.markdown("## Model health")\n    st.caption("One view for score freshness, the published market, workflow state and adaptive-model safety.")\n',
        '    st.markdown("### Current status")\n',
        "system health heading",
    )
    write(path, text)

    path = "features/tournament_archive.py"
    text = read(path)
    old = '''    st.markdown(
        "## World Cup 2026 archive" if complete else "## Tournament archive, building live"
    )
    st.caption(
        "The archive turns the live project into a permanent record: outcomes, market paths and forecast evidence stay available after the final."
    )
'''
    new = '''    st.markdown("### Archive status")
    st.caption(
        "This page preserves official outcomes, market paths and forecast evidence as a permanent record."
    )
'''
    text = replace_once(text, old, new, "archive heading")
    write(path, text)


def patch_tests() -> None:
    write(
        "tests/test_navigation_contract.py",
        '''from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class NavigationContractTest(unittest.TestCase):
    def test_navigation_uses_supported_icons_and_single_menu(self):
        app_text = (ROOT / "app.py").read_text(encoding="utf-8")
        product_ui_text = (ROOT / "features" / "product_ui.py").read_text(encoding="utf-8")
        patch_text = (ROOT / "scripts" / "apply_product_experience_refresh.py").read_text(encoding="utf-8")
        config_text = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")

        combined = app_text + product_ui_text + patch_text
        self.assertNotIn('icon="◇"', combined)
        self.assertNotIn('icon="◉"', combined)
        self.assertNotIn("disabled=active_page", product_ui_text)
        self.assertIn("showSidebarNavigation = false", config_text)

        for sidebar_text in (app_text, product_ui_text):
            self.assertIn('with st.expander("Tools", expanded=False):', sidebar_text)
            for label in [
                "Overview",
                "Countries",
                "Matches",
                "Bracket",
                "Simulator",
                "Analysis",
                "System Health",
                "Archive",
            ]:
                self.assertIn(f'label="{label}"', sidebar_text)
            for hidden_label in [
                "Live Match Room",
                "Market Story",
                "Group Archive",
                "Group Centre",
                "Guide",
            ]:
                self.assertNotIn(f'label="{hidden_label}"', sidebar_text)
        self.assertIn('initial_sidebar_state="auto"', app_text)


if __name__ == "__main__":
    unittest.main()
''',
    )

    write(
        "tests/test_product_information_architecture.py",
        '''from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ProductInformationArchitectureTests(unittest.TestCase):
    def test_overview_does_not_embed_the_full_simulator(self):
        text = (ROOT / "features" / "overview_v3.py").read_text(encoding="utf-8")
        self.assertNotIn("render_tournament_simulator", text)
        self.assertIn('["Current round", "Market", "Today"]', text)
        self.assertIn('st.tabs(["Fixtures", "Countries"])', text)
        self.assertNotIn('"Market signals"', text)

    def test_market_deep_links_open_the_country_market_section(self):
        text = (ROOT / "features" / "overview_v3.py").read_text(encoding="utf-8")
        self.assertIn('cupmarket_country_requested_section', text)
        self.assertIn('st.switch_page("pages/7_Tournament_Path.py")', text)
        self.assertNotIn('st.switch_page("pages/5_Market_Story.py")', text)

    def test_country_page_is_country_specific(self):
        text = (ROOT / "features" / "tournament_path_page.py").read_text(encoding="utf-8")
        active = text[text.index("def _render_country_page_v2") :]
        self.assertIn('st.segmented_control(', active)
        self.assertIn('["Overview", "Path", "Market", "Fixtures"]', active)
        self.assertNotIn("_render_tournament_forecast(data)", active)
        self.assertNotIn("_render_tournament_fixtures(data)", active)
        self.assertIn("This table contains only the selected country's fixtures.", active)

    def test_analysis_and_archive_have_distinct_jobs(self):
        analysis = (ROOT / "pages" / "11_Tournament_Insights.py").read_text(encoding="utf-8")
        archive = (ROOT / "pages" / "13_Tournament_Archive.py").read_text(encoding="utf-8")
        self.assertIn("<h1>Model analysis</h1>", analysis)
        self.assertNotIn("Specialist tools", analysis)
        self.assertIn("Open Archive for the permanent tournament story", analysis)
        self.assertIn("<h1>Tournament archive</h1>", archive)

    def test_primary_page_headings_are_direct(self):
        expected = {
            ROOT / "features" / "tournament_pulse_page.py": "<h1>Tournament overview</h1>",
            ROOT / "features" / "match_hub_v2.py": "<h1>Matches and results</h1>",
            ROOT / "features" / "tournament_path_page.py": "<h1>Country profile</h1>",
            ROOT / "pages" / "8_Bracket_View.py": "<h1>Tournament bracket</h1>",
            ROOT / "pages" / "12_Tournament_Simulator.py": "<h1>Scenario simulator</h1>",
            ROOT / "pages" / "9_Model_Health.py": "<h1>System health</h1>",
        }
        for path, heading in expected.items():
            self.assertIn(heading, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
''',
    )


def patch_readme() -> None:
    write(
        "README.md",
        '''# CupMarket 2026

A Streamlit app for World Cup match tracking, knockout paths, tournament probabilities, model evaluation, and virtual country prices.

## Live app

The Streamlit app uses `app.py` as its launcher and opens the Tournament Overview by default.

## Product structure

Each visible page has one main responsibility:

- **Overview** — current round, latest results, upcoming fixtures, and market leaders.
- **Countries** — one selected country's status, path, price movement, and fixtures.
- **Matches** — live scores, upcoming fixtures, completed results, and forecast review.
- **Bracket** — confirmed fixtures and projected knockout slots.
- **Simulator** — sandbox result scenarios that never change official data.
- **Analysis** — forecast performance, adaptive research, and model evidence.
- **System Health** — data freshness, workflow state, publication status, and guardrails.
- **Archive** — permanent tournament history, market replay, and final model verdict.

The built-in Streamlit page list is hidden so users see one consistent navigation system.

## Data flow

- Live scores and match status come from football-data.org.
- The trained Phase 3 goal models are stored in `backend/state/models/`.
- `backend/update_pipeline.py` updates live Elo, rolling form, future match probabilities, knockout settlement, tournament simulations, adaptive signals, and CupMarket prices.
- `.github/workflows/update-cupmarket.yml` checks for newly completed official matches and missing official prediction rows.
- A manual workflow run forces a full 20,000-simulation refresh.
- Updated files are committed into `data/`, and Streamlit reads the new commit automatically.

## System health

The System Health page reports the latest published market time, score-check time, update-workflow state, data source, simulation model, adaptive guardrail, and archive state.

When automation fails, the update workflow opens or updates a GitHub issue. A later successful run closes the alert.

## Required secrets

Create `FOOTBALL_DATA_TOKEN` in both places:

1. Streamlit Community Cloud secrets, for near-live scores in the app.
2. GitHub repository Actions secrets, for the automated backend.

Never commit the token to this repository.

## Required GitHub Actions permission

In the repository, open:

`Settings → Actions → General → Workflow permissions`

Select **Read and write permissions** so the workflow can commit refreshed files.

## Current automation scope

CupMarket supports the completed group-stage record and the active knockout flow. Knockout fixtures use saved pre-match forecasts, settlement ledgers, advancement probabilities, live knockout projections, extra time, penalties, and stage-aware UI labels.
''',
    )


def main() -> None:
    patch_app()
    patch_product_ui()
    patch_overview()
    patch_main_page_copy()
    patch_country_page()
    patch_pages()
    patch_feature_headings()
    patch_tests()
    patch_readme()
    print("CupMarket UX writing and information architecture refresh applied.")


if __name__ == "__main__":
    main()
