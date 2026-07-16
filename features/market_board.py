from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

EXIT_STAGE_COLUMNS = [
    ("prob_group_exit", "Group stage"),
    ("prob_round_32_exit", "Round of 32"),
    ("prob_round_16_exit", "Round of 16"),
    ("prob_quarter_final_exit", "Quarter-final"),
    ("prob_semi_final_exit", "Semi-final"),
    ("prob_runner_up", "Final"),
]
REACH_COLUMNS = [
    ("prob_reach_round_32", "R32"),
    ("prob_reach_round_16", "R16"),
    ("prob_reach_quarter_final", "QF"),
    ("prob_reach_semi_final", "SF"),
    ("prob_reach_final", "Final"),
    ("prob_champion", "Champion"),
]
ROUND_LABELS = {
    "prob_reach_round_32": "Round of 32",
    "prob_reach_round_16": "Round of 16",
    "prob_reach_quarter_final": "Quarter-final",
    "prob_reach_semi_final": "Semi-final",
    "prob_reach_final": "Final",
    "prob_champion": "Champion",
}
SORT_OPTIONS = {
    "Market rank": ("market_rank_sort", True),
    "Price": ("cupmarket_price_sort", False),
    "Champion chance": ("prob_champion_sort", False),
    "Next-stage chance": ("next_stage_probability", False),
    "Biggest risers": ("price_change_percent_sort", False),
    "Biggest fallers": ("price_change_percent_sort", True),
    "Adaptive boost": ("rating_change_sort", False),
}


def _numeric(value: Any, default: float = 0.0) -> float:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return default
    return float(number)


def _pct(value: Any) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "-"
    return f"{100 * float(number):.1f}%"


def _price(value: Any) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return "-"
    return f"{float(number):.2f} CM"


def _move(row: pd.Series) -> str:
    change = pd.to_numeric(row.get("price_change"), errors="coerce")
    percent = pd.to_numeric(row.get("price_change_percent"), errors="coerce")
    if pd.isna(change):
        return "-"
    if pd.isna(percent):
        return f"{float(change):+.2f} CM"
    return f"{float(change):+.2f} CM ({float(percent):+.1f}%)"


def _exit_stage(row: pd.Series) -> str:
    for column, label in EXIT_STAGE_COLUMNS:
        if _numeric(row.get(column)) >= 0.999:
            return label
    return "Still alive"


def _round_status(row: pd.Series) -> str:
    exit_stage = str(row.get("exit_stage") or "")
    if exit_stage and exit_stage != "Still alive":
        return f"Out: {exit_stage}"
    reached = "Alive"
    for column, label in REACH_COLUMNS:
        if _numeric(row.get(column)) >= 0.999:
            reached = (
                "Champion"
                if column == "prob_champion"
                else f"In {ROUND_LABELS[column]}"
            )
    return reached


def _next_target(row: pd.Series) -> tuple[str, float]:
    exit_stage = str(row.get("exit_stage") or "")
    if exit_stage and exit_stage != "Still alive":
        return ("Eliminated", 0.0)
    for column, _ in REACH_COLUMNS:
        probability = _numeric(row.get(column))
        if probability < 0.999:
            return (ROUND_LABELS[column], probability)
    return ("Champion", _numeric(row.get("prob_champion"), 1.0))


def _safe_text(value: Any) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value or "").strip()
    return "" if text.lower() in {"", "nan", "none", "null"} else text


def adaptive_health(predictions: pd.DataFrame, ratings: pd.DataFrame) -> dict[str, Any]:
    adaptive_columns = {
        "home_adaptive_adjustment",
        "away_adaptive_adjustment",
        "adaptive_prediction_enabled",
        "adaptive_model_version",
    }
    has_columns = not predictions.empty and adaptive_columns.issubset(predictions.columns)
    enabled_rows = 0
    nonzero_rows = 0
    version = "Unavailable"
    if has_columns:
        enabled_rows = int(
            predictions["adaptive_prediction_enabled"]
            .astype(str)
            .str.lower()
            .isin(["true", "1", "yes"])
            .sum()
        )
        home = pd.to_numeric(predictions["home_adaptive_adjustment"], errors="coerce")
        away = pd.to_numeric(predictions["away_adaptive_adjustment"], errors="coerce")
        nonzero_rows = int(((home.fillna(0).abs() + away.fillna(0).abs()) > 1e-9).sum())
        versions = predictions["adaptive_model_version"].dropna().astype(str)
        if not versions.empty:
            version = versions.iloc[-1]
    return {
        "has_prediction_columns": has_columns,
        "enabled_rows": enabled_rows,
        "nonzero_prediction_rows": nonzero_rows,
        "rating_rows": int(len(ratings)) if isinstance(ratings, pd.DataFrame) else 0,
        "version": version,
        "working": bool(has_columns and enabled_rows > 0 and nonzero_rows > 0),
    }


def build_market_board(
    prices: pd.DataFrame,
    adaptive_ratings: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if prices.empty or "team" not in prices.columns:
        return pd.DataFrame()

    board = prices.copy()
    board["team"] = board["team"].astype(str)
    for column, _ in REACH_COLUMNS + EXIT_STAGE_COLUMNS:
        if column in board.columns:
            board[column] = pd.to_numeric(board[column], errors="coerce").fillna(0.0)

    for column in [
        "market_rank",
        "cupmarket_price",
        "previous_price",
        "price_change",
        "price_change_percent",
    ]:
        if column in board.columns:
            board[column] = pd.to_numeric(board[column], errors="coerce")

    board["exit_stage"] = board.apply(_exit_stage, axis=1)
    board["market_status"] = board.apply(_round_status, axis=1)
    next_targets = board.apply(_next_target, axis=1)
    board["next_target"] = [target for target, _ in next_targets]
    board["next_stage_probability"] = [probability for _, probability in next_targets]

    if adaptive_ratings is not None and not adaptive_ratings.empty and "team" in adaptive_ratings.columns:
        rating_columns = [
            column
            for column in [
                "team",
                "rating_change",
                "confidence_level",
                "overreaction_risk",
                "adaptive_model_version",
            ]
            if column in adaptive_ratings.columns
        ]
        ratings = adaptive_ratings[rating_columns].copy()
        ratings["team"] = ratings["team"].astype(str)
        board = board.merge(ratings, on="team", how="left", suffixes=("", "_adaptive"))
    else:
        board["rating_change"] = pd.NA
        board["confidence_level"] = pd.NA
        board["overreaction_risk"] = pd.NA

    board["market_rank_sort"] = pd.to_numeric(
        board.get("market_rank"),
        errors="coerce",
    ).fillna(9999)
    board["cupmarket_price_sort"] = pd.to_numeric(
        board.get("cupmarket_price"),
        errors="coerce",
    ).fillna(0.0)
    board["prob_champion_sort"] = pd.to_numeric(
        board.get("prob_champion"),
        errors="coerce",
    ).fillna(0.0)
    board["price_change_percent_sort"] = pd.to_numeric(
        board.get("price_change_percent"),
        errors="coerce",
    ).fillna(0.0)
    board["rating_change_sort"] = pd.to_numeric(
        board.get("rating_change"),
        errors="coerce",
    ).fillna(0.0)
    return board.sort_values("market_rank_sort").reset_index(drop=True)


def filter_market_board(
    board: pd.DataFrame,
    *,
    search: str = "",
    status_filter: str = "All",
    sort_by: str = "Market rank",
) -> pd.DataFrame:
    if board.empty:
        return board
    result = board.copy()
    query = search.strip().lower()
    if query:
        result = result.loc[result["team"].str.lower().str.contains(query, na=False)].copy()
    if status_filter == "Alive":
        result = result.loc[result["exit_stage"].eq("Still alive")].copy()
    elif status_filter == "Eliminated":
        result = result.loc[~result["exit_stage"].eq("Still alive")].copy()
    elif status_filter != "All":
        result = result.loc[result["market_status"].eq(status_filter)].copy()

    sort_column, ascending = SORT_OPTIONS.get(sort_by, SORT_OPTIONS["Market rank"])
    if sort_column in result.columns:
        result = result.sort_values(sort_column, ascending=ascending, na_position="last")
    return result.reset_index(drop=True)


def display_market_board(board: pd.DataFrame) -> pd.DataFrame:
    if board.empty:
        return pd.DataFrame()
    display = pd.DataFrame(
        {
            "Rank": board["market_rank"].map(
                lambda value: f"#{int(value)}" if pd.notna(value) else "-"
            ),
            "Country": board["team"],
            "Status": board["market_status"],
            "Price": board["cupmarket_price"].map(_price),
            "Move": board.apply(_move, axis=1),
            "Next": board["next_target"],
            "Next chance": board["next_stage_probability"].map(_pct),
            "R16": board.get("prob_reach_round_16", pd.Series(index=board.index)).map(_pct),
            "QF": board.get("prob_reach_quarter_final", pd.Series(index=board.index)).map(_pct),
            "SF": board.get("prob_reach_semi_final", pd.Series(index=board.index)).map(_pct),
            "Final": board.get("prob_reach_final", pd.Series(index=board.index)).map(_pct),
            "Champion": board.get("prob_champion", pd.Series(index=board.index)).map(_pct),
            "Adaptive": board.get("rating_change", pd.Series(index=board.index)).map(
                lambda value: "-" if pd.isna(value) else f"{float(value):+.1f}"
            ),
            "Signal": board.get("overreaction_risk", pd.Series(index=board.index)).map(
                lambda value: _safe_text(value) or "-"
            ),
        }
    )
    return display


def render_market_board(
    prices: pd.DataFrame,
    *,
    predictions: pd.DataFrame | None = None,
    adaptive_ratings: pd.DataFrame | None = None,
) -> None:
    predictions = predictions if isinstance(predictions, pd.DataFrame) else pd.DataFrame()
    adaptive_ratings = (
        adaptive_ratings if isinstance(adaptive_ratings, pd.DataFrame) else pd.DataFrame()
    )
    board = build_market_board(prices, adaptive_ratings)
    health = adaptive_health(predictions, adaptive_ratings)

    st.markdown("### Market board")
    st.caption(
        "Every country, current CM price, tournament probabilities and adaptive signal in one scan."
    )
    if board.empty:
        st.info("Country market data is not available yet.")
        return

    alive = int(board["exit_stage"].eq("Still alive").sum())
    metrics = st.columns(4)
    metrics[0].metric("Countries", len(board))
    metrics[1].metric("Still alive", alive)
    metrics[2].metric("Eliminated", len(board) - alive)
    metrics[3].metric(
        "Adaptive rows",
        health["enabled_rows"],
        delta="on" if health["working"] else "check",
        delta_color="off",
    )

    controls = st.columns([1.4, 1.0, 1.0])
    search = controls[0].text_input(
        "Search country",
        value="",
        key="market_board_search",
        placeholder="Canada, Brazil, Ghana...",
    )
    statuses = ["All", "Alive", "Eliminated"] + sorted(
        value for value in board["market_status"].dropna().unique() if value not in {"Alive"}
    )
    status_filter = controls[1].selectbox(
        "Filter",
        statuses,
        key="market_board_status",
    )
    sort_by = controls[2].selectbox(
        "Sort",
        list(SORT_OPTIONS),
        key="market_board_sort",
    )

    visible = filter_market_board(
        board,
        search=search,
        status_filter=status_filter,
        sort_by=sort_by,
    )

    st.markdown("#### Quick scan")
    card_rows = visible.head(6)
    if card_rows.empty:
        st.caption("No countries match the current filters.")
    else:
        columns = st.columns(min(3, len(card_rows)))
        for index, row in enumerate(card_rows.itertuples(index=False)):
            series = pd.Series(row._asdict())
            with columns[index % len(columns)]:
                with st.container(border=True):
                    st.caption(series.get("market_status", ""))
                    st.metric(
                        str(series.get("team")),
                        _price(series.get("cupmarket_price")),
                        delta=_move(series),
                    )
                    st.write(
                        f"Next: **{series.get('next_target')}** at "
                        f"**{_pct(series.get('next_stage_probability'))}**"
                    )
                    st.caption(
                        "Champion "
                        f"{_pct(series.get('prob_champion'))} | Adaptive "
                        f"{series.get('rating_change_sort'):+.1f}"
                    )

    st.markdown("#### Full country list")
    st.dataframe(
        display_market_board(visible),
        hide_index=True,
        width="stretch",
    )

    with st.expander("Adaptive model check", expanded=False):
        status = "Working" if health["working"] else "Needs data"
        st.write(
            f"Status: **{status}** | Version: **{health['version']}** | "
            f"enabled prediction rows: **{health['enabled_rows']}** | "
            f"nonzero adjustment rows: **{health['nonzero_prediction_rows']}** | "
            f"rating rows: **{health['rating_rows']}**"
        )
        st.caption(
            "Adaptive ratings are an audit and prediction adjustment layer. "
            "Official prices still publish only after the backend model run completes."
        )
