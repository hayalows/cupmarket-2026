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

    product_helpers = r"""
PRODUCT_UI_VERSION = "1.0"
PRODUCT_CSS_PATH = APP_ROOT / "assets" / "product.css"

px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = [
    "#5B5FF0",
    "#12B981",
    "#F59E0B",
    "#0EA5E9",
    "#EC4899",
    "#8B5CF6",
]


def inject_product_styles() -> None:
    if PRODUCT_CSS_PATH.exists():
        css = PRODUCT_CSS_PATH.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


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
"""

    text = replace_once(
        text,
        "WORKFLOW_STALE_MINUTES = 45\n",
        "WORKFLOW_STALE_MINUTES = 45\n" + product_helpers,
        "product helper insertion",
    )

    app_shell = r"""inject_product_styles()

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
"""

    text = replace_between(
        text,
        'st.title("CupMarket 2026")',
        '\n\nif page == "Overview":',
        app_shell,
        "application shell",
    )

    heading_replacements = {
        '    st.subheader("Market leaders")': '''    render_section_heading(
        "Market leaders",
        "The highest probability-weighted country values right now.",
        "Market pulse",
    )''',
        '    st.subheader("Next matches")': '''    render_section_heading(
        "Next matches",
        "Upcoming fixtures and live tournament status.",
        "Match calendar",
    )''',
        '    st.subheader("What the leader\'s probability means")': '''    render_section_heading(
        "How to read the leader",
        "Price combines the value of every possible tournament finish.",
        "Interpretation",
    )''',
        '    st.header("Match Centre")': '''    render_section_heading(
        "Fixtures and forecasts",
        "Filter the tournament and compare scores with saved model probabilities.",
        "Match centre",
    )''',
        '    st.header("Country Market")': '''    render_section_heading(
        "Country prices",
        "Prices update after completed matches and a fresh tournament simulation.",
        "Market",
    )''',
        '    st.header("Team Explorer")': '''    render_section_heading(
        "Explore a country",
        "See price, stage probabilities and the shape of a country's path.",
        "Country profile",
    )''',
        '    st.header("Current Group Tables")': '''    render_section_heading(
        "Current standings",
        "Official completed results translated into live group tables.",
        "Groups",
    )''',
        '    st.header("Model Health")\n\n    st.subheader("Production pipeline")': '''    render_section_heading(
        "Production pipeline",
        "Workflow health, freshness and historical evaluation in one place.",
        "Operations",
    )''',
        '    st.header("How the system works")': '''    render_section_heading(
        "From data to price",
        "The complete path from a final whistle to a new CupMarket value.",
        "Method",
    )''',
    }

    for old, new in heading_replacements.items():
        text = replace_once(text, old, new, old)

    text = replace_once(
        text,
        '''        st.dataframe(
            leader_table,
            use_container_width=True,
            hide_index=True,
        )
''',
        '''        leader_table = leader_table.rename(
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
''',
        "leader table",
    )

    text = replace_once(
        text,
        '''            st.dataframe(
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
''',
        '''            next_display = next_matches[
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
''',
        "next matches table",
    )

    text = replace_once(
        text,
        '''        st.dataframe(
            filtered[display_columns],
            use_container_width=True,
            hide_index=True,
        )
''',
        '''        match_display = filtered[display_columns].copy()

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
''',
        "match centre table",
    )

    old_market = '''        st.dataframe(
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
    new_market = '''        market_columns = [
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
    text = replace_once(text, old_market, new_market, "country market table")

    old_group = '''            st.dataframe(
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
    new_group = '''            group_display = table[
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
    text = replace_once(text, old_group, new_group, "group table")

    for figure_name in ["figure", "history_chart", "stage_chart"]:
        anchor = f'''        st.plotly_chart(
            {figure_name},
            use_container_width=True,
        )
'''
        if anchor in text:
            text = text.replace(
                anchor,
                f'''        polish_figure({figure_name})
        st.plotly_chart(
            {figure_name},
            use_container_width=True,
        )
''',
                1,
            )

    APP_PATH.write_text(text, encoding="utf-8")
    print("CupMarket product UI refresh applied.")


if __name__ == "__main__":
    main()
