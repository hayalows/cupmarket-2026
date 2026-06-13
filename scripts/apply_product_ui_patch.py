from __future__ import annotations

from pathlib import Path


APP_PATH = Path("app.py")
MARKER = 'PRODUCT_UI_VERSION = "1.0"'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label} anchor, found {count}.")
    return text.replace(old, new, 1)


def replace_between(
    text: str,
    start_marker: str,
    end_marker: str,
    replacement: str,
    label: str,
) -> str:
    start = text.find(start_marker)
    if start == -1:
        raise RuntimeError(f"Could not find start of {label}.")
    end = text.find(end_marker, start)
    if end == -1:
        raise RuntimeError(f"Could not find end of {label}.")
    return text[:start] + replacement + text[end:]


def main() -> None:
    text = APP_PATH.read_text(encoding="utf-8")

    if MARKER in text:
        print("Product UI refresh already applied.")
        return

    text = replace_once(
        text,
        '''st.set_page_config(
    page_title="CupMarket 2026",
    page_icon="⚽",
    layout="wide",
)
''',
        '''st.set_page_config(
    page_title="CupMarket 2026",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)
''',
        "page configuration",
    )

    product_layer = r'''
PRODUCT_UI_VERSION = "1.0"

px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = [
    "#5B5FF0",
    "#12B981",
    "#F59E0B",
    "#0EA5E9",
    "#EC4899",
    "#8B5CF6",
]

PRODUCT_CSS = """
<style>
:root {
    --cm-bg: #f5f7fb;
    --cm-surface: rgba(255,255,255,.92);
    --cm-surface-solid: #ffffff;
    --cm-border: #e6e9f0;
    --cm-text: #10131a;
    --cm-muted: #687083;
    --cm-primary: #5b5ff0;
    --cm-primary-soft: #eef0ff;
    --cm-green: #0f9f6e;
    --cm-amber: #d97706;
    --cm-red: #dc4c64;
    --cm-shadow: 0 18px 55px rgba(23, 29, 52, .08);
}

html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Inter, Arial, sans-serif;
}

.stApp {
    background:
        radial-gradient(circle at 72% -10%, rgba(91,95,240,.12), transparent 34%),
        radial-gradient(circle at 2% 15%, rgba(14,165,233,.08), transparent 28%),
        var(--cm-bg);
    color: var(--cm-text);
}

.block-container {
    max-width: 1320px;
    padding-top: 2.2rem;
    padding-bottom: 4rem;
}

header[data-testid="stHeader"] {
    background: rgba(245,247,251,.78);
    backdrop-filter: blur(18px);
}

#MainMenu, footer {
    visibility: hidden;
}

h1, h2, h3 {
    color: var(--cm-text);
    letter-spacing: -.035em;
}

p, label, .stCaption {
    color: var(--cm-muted);
}

.cm-hero {
    position: relative;
    overflow: hidden;
    margin: .2rem 0 1.8rem;
    padding: 2rem 2.1rem;
    border: 1px solid rgba(255,255,255,.75);
    border-radius: 28px;
    background:
        linear-gradient(120deg, rgba(255,255,255,.98), rgba(248,249,255,.94)),
        var(--cm-surface-solid);
    box-shadow: var(--cm-shadow);
}

.cm-hero::after {
    content: "";
    position: absolute;
    width: 250px;
    height: 250px;
    right: -80px;
    top: -110px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(91,95,240,.22), rgba(91,95,240,0));
}

.cm-hero-top {
    display: flex;
    gap: .75rem;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    position: relative;
    z-index: 1;
}

.cm-eyebrow {
    display: inline-flex;
    align-items: center;
    gap: .45rem;
    font-size: .76rem;
    font-weight: 750;
    letter-spacing: .09em;
    text-transform: uppercase;
    color: var(--cm-primary);
}

.cm-hero h1 {
    margin: .55rem 0 .35rem;
    font-size: clamp(2.25rem, 5vw, 4rem);
    line-height: 1.02;
    font-weight: 780;
    max-width: 900px;
}

.cm-hero p {
    margin: 0;
    max-width: 780px;
    font-size: 1.02rem;
    line-height: 1.65;
}

.cm-status {
    display: inline-flex;
    align-items: center;
    gap: .45rem;
    border-radius: 999px;
    padding: .48rem .72rem;
    font-size: .78rem;
    font-weight: 720;
    border: 1px solid var(--cm-border);
    background: rgba(255,255,255,.82);
    color: var(--cm-text);
}

.cm-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--cm-green);
    box-shadow: 0 0 0 5px rgba(15,159,110,.12);
}

.cm-status.failed .cm-dot { background: var(--cm-red); box-shadow: 0 0 0 5px rgba(220,76,100,.12); }
.cm-status.attention .cm-dot { background: var(--cm-amber); box-shadow: 0 0 0 5px rgba(217,119,6,.12); }
.cm-status.updating .cm-dot { background: #0ea5e9; box-shadow: 0 0 0 5px rgba(14,165,233,.12); }

.cm-hero-meta {
    display: flex;
    gap: .65rem;
    flex-wrap: wrap;
    margin-top: 1.3rem;
    position: relative;
    z-index: 1;
}

.cm-chip {
    display: inline-flex;
    gap: .38rem;
    align-items: center;
    padding: .5rem .7rem;
    border-radius: 12px;
    background: #f2f4f9;
    color: #4b5568;
    font-size: .8rem;
    font-weight: 650;
}

.cm-section-heading {
    margin: 2rem 0 .85rem;
}

.cm-section-heading .kicker {
    color: var(--cm-primary);
    font-size: .73rem;
    font-weight: 800;
    letter-spacing: .09em;
    text-transform: uppercase;
}

.cm-section-heading h2 {
    font-size: 1.55rem;
    margin: .2rem 0 .2rem;
}

.cm-section-heading p {
    margin: 0;
    font-size: .93rem;
}

[data-testid="stMetric"] {
    background: var(--cm-surface);
    border: 1px solid var(--cm-border);
    border-radius: 20px;
    padding: 1.1rem 1.15rem;
    box-shadow: 0 10px 30px rgba(23,29,52,.055);
    min-height: 118px;
}

[data-testid="stMetricLabel"] {
    font-size: .78rem;
    color: var(--cm-muted);
    font-weight: 680;
}

[data-testid="stMetricValue"] {
    color: var(--cm-text);
    font-size: 2rem;
    font-weight: 760;
    letter-spacing: -.04em;
}

[data-testid="stMetricDelta"] {
    font-weight: 700;
}

[data-testid="stDataFrame"] {
    border: 1px solid var(--cm-border);
    border-radius: 18px;
    overflow: hidden;
    background: var(--cm-surface-solid);
    box-shadow: 0 10px 28px rgba(23,29,52,.045);
}

[data-testid="stPlotlyChart"] {
    background: var(--cm-surface-solid);
    border: 1px solid var(--cm-border);
    border-radius: 20px;
    padding: .55rem;
    box-shadow: 0 10px 28px rgba(23,29,52,.045);
}

.stButton > button, .stLinkButton > a {
    border-radius: 13px !important;
    border: 1px solid #dfe3ec !important;
    background: #ffffff !important;
    color: var(--cm-text) !important;
    font-weight: 680 !important;
    min-height: 2.8rem;
    box-shadow: 0 7px 20px rgba(23,29,52,.055);
    transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
}

.stButton > button:hover, .stLinkButton > a:hover {
    border-color: #bfc5f7 !important;
    box-shadow: 0 10px 26px rgba(91,95,240,.12);
    transform: translateY(-1px);
}

[data-baseweb="select"] > div, [data-testid="stTextInput"] input {
    border-radius: 13px !important;
    border-color: var(--cm-border) !important;
    background: #ffffff !important;
}

[data-testid="stAlert"] {
    border-radius: 16px;
    border: 1px solid var(--cm-border);
}

section[data-testid="stSidebar"] {
    background:
        radial-gradient(circle at 0 0, rgba(91,95,240,.26), transparent 35%),
        linear-gradient(180deg, #12172a 0%, #0d1120 100%);
    border-right: 1px solid rgba(255,255,255,.06);
}

section[data-testid="stSidebar"] * {
    color: #eef1fa;
}

section[data-testid="stSidebar"] .stCaption,
section[data-testid="stSidebar"] p {
    color: #aeb6ca;
}

section[data-testid="stSidebar"] [data-testid="stAlert"] {
    background: rgba(255,255,255,.07);
    border-color: rgba(255,255,255,.1);
}

section[data-testid="stSidebar"] [role="radiogroup"] label {
    padding: .72rem .78rem;
    border-radius: 12px;
    margin-bottom: .2rem;
    transition: background .15s ease;
}

section[data-testid="stSidebar"] [role="radiogroup"] label:hover {
    background: rgba(255,255,255,.07);
}

.cm-side-brand {
    display: flex;
    align-items: center;
    gap: .78rem;
    padding: .3rem 0 1.15rem;
}

.cm-mark {
    width: 42px;
    height: 42px;
    border-radius: 14px;
    display: grid;
    place-items: center;
    background: linear-gradient(145deg, #7377ff, #4548c9);
    box-shadow: 0 10px 30px rgba(91,95,240,.35);
    font-weight: 850;
    color: white;
    letter-spacing: -.04em;
}

.cm-side-brand strong {
    display: block;
    font-size: 1rem;
    color: white;
}

.cm-side-brand span {
    color: #98a3ba;
    font-size: .74rem;
}

.cm-side-label {
    margin-top: .55rem;
    color: #7f8aa3 !important;
    font-size: .67rem;
    font-weight: 800;
    letter-spacing: .1em;
    text-transform: uppercase;
}

.cm-side-row {
    margin-top: .5rem;
    padding: .72rem .78rem;
    border-radius: 13px;
    background: rgba(255,255,255,.055);
    border: 1px solid rgba(255,255,255,.07);
    font-size: .79rem;
    line-height: 1.45;
}

.cm-side-row b { color: #ffffff; }

@media (max-width: 800px) {
    .block-container { padding: 1rem .85rem 3rem; }
    .cm-hero { padding: 1.45rem 1.3rem; border-radius: 22px; }
    .cm-hero h1 { font-size: 2.25rem; }
    [data-testid="stMetric"] { min-height: 102px; }
}
</style>
"""


def inject_product_styles() -> None:
    st.markdown(PRODUCT_CSS, unsafe_allow_html=True)


def render_page_header(page: str, health: dict, metadata: dict) -> None:
    page_copy = {
        "Overview": (
            "Tournament intelligence",
            "A live view of matches, probabilities and the country market.",
        ),
        "Match Centre": (
            "Match Centre",
            "Fixtures, scores and model probabilities in one place.",
        ),
        "Country Market": (
            "Country Market",
            "Probability-weighted prices that move as the tournament changes.",
        ),
        "Team Explorer": (
            "Team Explorer",
            "Inspect a country's path, price and tournament outlook.",
        ),
        "Group Tables": (
            "Group Tables",
            "Current standings built from completed tournament results.",
        ),
        "Model Health": (
            "Model Health",
            "Operational status, evaluation metrics and data freshness.",
        ),
        "How It Works": (
            "How CupMarket works",
            "A transparent view of the data, models and pricing logic.",
        ),
    }
    title, description = page_copy.get(
        page,
        (page, "World Cup intelligence powered by live data and simulation."),
    )
    status = str(health.get("status", "Unknown"))
    status_class = status.lower().replace(" ", "-")
    simulations = int(metadata.get("number_of_simulations", 0) or 0)
    generated = format_utc_timestamp(metadata.get("generated_at_utc"))
    st.markdown(
        f'''
        <div class="cm-hero">
            <div class="cm-hero-top">
                <div class="cm-eyebrow">CupMarket 2026 · Live intelligence</div>
                <div class="cm-status {status_class}">
                    <span class="cm-dot"></span>{status}
                </div>
            </div>
            <h1>{title}</h1>
            <p>{description}</p>
            <div class="cm-hero-meta">
                <span class="cm-chip">◉ {simulations:,} simulations</span>
                <span class="cm-chip">↻ Updated {generated}</span>
                <span class="cm-chip">◎ Virtual market · No real money</span>
            </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def render_section_heading(
    title: str,
    description: str,
    kicker: str = "Live data",
) -> None:
    st.markdown(
        f'''
        <div class="cm-section-heading">
            <div class="kicker">{kicker}</div>
            <h2>{title}</h2>
            <p>{description}</p>
        </div>
        ''',
        unsafe_allow_html=True,
    )


def polish_figure(figure, height: int | None = None):
    figure.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#ffffff",
        font=dict(
            family='-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
            color="#4b5568",
            size=13,
        ),
        title_font=dict(color="#10131a", size=18),
        margin=dict(l=24, r=24, t=64, b=24),
        hoverlabel=dict(
            bgcolor="#111827",
            font_color="#ffffff",
            bordercolor="#111827",
        ),
    )
    if height:
        figure.update_layout(height=height)
    figure.update_xaxes(gridcolor="#edf0f5", zeroline=False)
    figure.update_yaxes(gridcolor="#edf0f5", zeroline=False)
    return figure
'''

    text = replace_once(
        text,
        "WORKFLOW_STALE_MINUTES = 45\n",
        "WORKFLOW_STALE_MINUTES = 45\n" + product_layer,
        "product UI insertion",
    )

    new_shell = r'''inject_product_styles()

NAV_LABELS = {
    "Overview": "◫  Overview",
    "Match Centre": "◉  Match Centre",
    "Country Market": "↗  Country Market",
    "Team Explorer": "◎  Team Explorer",
    "Group Tables": "▤  Group Tables",
    "Model Health": "◌  Model Health",
    "How It Works": "ⓘ  How It Works",
}

with st.sidebar:
    st.markdown(
        '''
        <div class="cm-side-brand">
            <div class="cm-mark">CM</div>
            <div>
                <strong>CupMarket</strong>
                <span>World Cup intelligence</span>
            </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    page = st.radio(
        "Choose a page",
        list(NAV_LABELS),
        format_func=lambda item: NAV_LABELS[item],
        label_visibility="collapsed",
    )

    st.markdown(
        '<div class="cm-side-label">System status</div>',
        unsafe_allow_html=True,
    )

    source = match_metadata.get("source", "Unknown")
    score_time = "Waiting for data"
    if match_metadata.get("fetched_at_utc"):
        score_time = pd.to_datetime(
            match_metadata["fetched_at_utc"],
            utc=True,
        ).strftime("%H:%M UTC")

    simulation_time = "Waiting for model"
    if phase5_meta.get("generated_at_utc"):
        simulation_time = pd.to_datetime(
            phase5_meta["generated_at_utc"],
            utc=True,
        ).strftime("%H:%M UTC")

    st.markdown(
        f'''
        <div class="cm-side-row">
            <b>{production_health.get("status", "Unknown")}</b><br>
            Scores · {source} · {score_time}<br>
            Model · {simulation_time}
        </div>
        ''',
        unsafe_allow_html=True,
    )

    if match_metadata.get("warning"):
        st.caption(match_metadata["warning"])

    st.caption("Data provided by football-data.org")

render_page_header(page, production_health, phase5_meta)
'''

    text = replace_between(
        text,
        'st.title("CupMarket 2026")',
        '\n\nif page == "Overview":',
        new_shell,
        "application shell",
    )

    heading_replacements = {
        '    st.subheader("Market leaders")': '    render_section_heading(\n        "Market leaders",\n        "The highest probability-weighted country values right now.",\n        "Market pulse",\n    )',
        '    st.subheader("Next matches")': '    render_section_heading(\n        "Next matches",\n        "Upcoming fixtures and live tournament status.",\n        "Match calendar",\n    )',
        '    st.subheader("What the leader\'s probability means")': '    render_section_heading(\n        "How to read the leader",\n        "Price combines the value of every possible tournament finish.",\n        "Interpretation",\n    )',
        '    st.header("Match Centre")': '    render_section_heading(\n        "Fixtures and forecasts",\n        "Filter the tournament and compare scores with saved model probabilities.",\n        "Match centre",\n    )',
        '    st.header("Country Market")': '    render_section_heading(\n        "Country prices",\n        "Prices update after completed matches and a fresh tournament simulation.",\n        "Market",\n    )',
        '    st.header("Team Explorer")': '    render_section_heading(\n        "Explore a country",\n        "See price, stage probabilities and the shape of a country\'s path.",\n        "Country profile",\n    )',
        '    st.header("Current Group Tables")': '    render_section_heading(\n        "Current standings",\n        "Official completed results translated into live group tables.",\n        "Groups",\n    )',
        '    st.header("Model Health")\n\n    st.subheader("Production pipeline")': '    render_section_heading(\n        "Production pipeline",\n        "Workflow health, freshness and historical evaluation in one place.",\n        "Operations",\n    )',
        '    st.header("How the system works")': '    render_section_heading(\n        "From data to price",\n        "The complete path from a final whistle to a new CupMarket value.",\n        "Method",\n    )',
    }

    for old, new in heading_replacements.items():
        text = replace_once(text, old, new, old)

    leader_anchor = '''        st.dataframe(
            leader_table,
            use_container_width=True,
            hide_index=True,
        )
'''
    leader_replacement = '''        leader_table = leader_table.rename(
            columns={
                "market_rank": "Rank",
                "team": "Country",
                "group": "Group",
                "cupmarket_price": "Price",
                "prob_reach_round_32": "Reach R32",
                "prob_reach_quarter_final": "Reach QF",
                "prob_reach_final": "Reach final",
                "prob_champion": "Champion",
            }
        )

        st.dataframe(
            leader_table,
            use_container_width=True,
            hide_index=True,
        )
'''
    text = replace_once(
        text,
        leader_anchor,
        leader_replacement,
        "leader table",
    )

    next_matches_anchor = '''            st.dataframe(
                next_matches[
                    [
                        "kickoff_utc",
                        "status",
                        "home_team",
                        "away_team",
                        "group",
                        "stage",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )
'''
    next_matches_replacement = '''            next_display = next_matches[
                [
                    "kickoff_utc",
                    "status",
                    "home_team",
                    "away_team",
                    "group",
                    "stage",
                ]
            ].rename(
                columns={
                    "kickoff_utc": "Kickoff · UTC",
                    "status": "Status",
                    "home_team": "Home",
                    "away_team": "Away",
                    "group": "Group",
                    "stage": "Stage",
                }
            )

            st.dataframe(
                next_display,
                use_container_width=True,
                hide_index=True,
            )
'''
    text = replace_once(
        text,
        next_matches_anchor,
        next_matches_replacement,
        "next matches table",
    )

    match_table_anchor = '''        st.dataframe(
            filtered[display_columns],
            use_container_width=True,
            hide_index=True,
        )
'''
    match_table_replacement = '''        match_display = filtered[display_columns].copy()

        for probability_column in [
            "prob_home_win",
            "prob_draw",
            "prob_away_win",
        ]:
            if probability_column in match_display.columns:
                match_display[probability_column] = match_display[
                    probability_column
                ].map(format_percent)

        for goals_column in [
            "expected_home_goals",
            "expected_away_goals",
        ]:
            if goals_column in match_display.columns:
                match_display[goals_column] = match_display[
                    goals_column
                ].round(2)

        match_display = match_display.rename(
            columns={
                "kickoff_utc": "Kickoff · UTC",
                "status": "Status",
                "home_team": "Home",
                "score": "Score",
                "away_team": "Away",
                "group": "Group",
                "stage": "Stage",
                "expected_home_goals": "Home xG",
                "expected_away_goals": "Away xG",
                "prob_home_win": "Home win",
                "prob_draw": "Draw",
                "prob_away_win": "Away win",
                "display_label": "Model view",
                "most_likely_score": "Likely score",
            }
        )

        st.dataframe(
            match_display,
            use_container_width=True,
            hide_index=True,
        )
'''
    text = replace_once(
        text,
        match_table_anchor,
        match_table_replacement,
        "match centre table",
    )

    market_table_start = '''        st.dataframe(
            market_table[
                [
                    column
                    for column in [
                        "market_rank",
                        "team",
                        "group",
                        "cupmarket_price",
                        "previous_price",
                        "price_change",
                        "price_change_percent",
                        "prob_reach_round_32",
                        "prob_reach_quarter_final",
                        "prob_reach_final",
                        "prob_champion",
                    ]
                    if column
                    in market_table.columns
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )
'''
    market_table_replacement = '''        market_columns = [
            column
            for column in [
                "market_rank",
                "team",
                "group",
                "cupmarket_price",
                "previous_price",
                "price_change",
                "price_change_percent",
                "prob_reach_round_32",
                "prob_reach_quarter_final",
                "prob_reach_final",
                "prob_champion",
            ]
            if column in market_table.columns
        ]
        market_display = market_table[market_columns].copy()

        for probability_column in [
            "prob_reach_round_32",
            "prob_reach_quarter_final",
            "prob_reach_final",
            "prob_champion",
        ]:
            if probability_column in market_display.columns:
                market_display[probability_column] = market_display[
                    probability_column
                ].map(format_percent)

        market_display = market_display.rename(
            columns={
                "market_rank": "Rank",
                "team": "Country",
                "group": "Group",
                "cupmarket_price": "Price",
                "previous_price": "Previous",
                "price_change": "Change",
                "price_change_percent": "Change %",
                "prob_reach_round_32": "Reach R32",
                "prob_reach_quarter_final": "Reach QF",
                "prob_reach_final": "Reach final",
                "prob_champion": "Champion",
            }
        )

        st.dataframe(
            market_display,
            use_container_width=True,
            hide_index=True,
        )
'''
    text = replace_once(
        text,
        market_table_start,
        market_table_replacement,
        "country market table",
    )

    group_table_anchor = '''            st.dataframe(
                table[
                    [
                        "position",
                        "team",
                        "played",
                        "wins",
                        "draws",
                        "losses",
                        "goals_for",
                        "goals_against",
                        "goal_difference",
                        "points",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )
'''
    group_table_replacement = '''            group_display = table[
                [
                    "position",
                    "team",
                    "played",
                    "wins",
                    "draws",
                    "losses",
                    "goals_for",
                    "goals_against",
                    "goal_difference",
                    "points",
                ]
            ].rename(
                columns={
                    "position": "Pos",
                    "team": "Country",
                    "played": "P",
                    "wins": "W",
                    "draws": "D",
                    "losses": "L",
                    "goals_for": "GF",
                    "goals_against": "GA",
                    "goal_difference": "GD",
                    "points": "Pts",
                }
            )

            st.dataframe(
                group_display,
                use_container_width=True,
                hide_index=True,
            )
'''
    text = replace_once(
        text,
        group_table_anchor,
        group_table_replacement,
        "group table",
    )

    for figure_name in ["figure", "history_chart", "stage_chart"]:
        anchor = f'''        st.plotly_chart(
            {figure_name},
            use_container_width=True,
        )
'''
        replacement = f'''        polish_figure({figure_name})
        st.plotly_chart(
            {figure_name},
            use_container_width=True,
        )
'''
        if anchor in text:
            text = text.replace(anchor, replacement, 1)

    APP_PATH.write_text(text, encoding="utf-8")
    print("CupMarket product UI refresh applied.")


if __name__ == "__main__":
    main()
