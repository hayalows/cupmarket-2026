from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

EXPECTED_TEAM_COUNT = 48
EXPECTED_GROUPS = tuple("ABCDEFGHIJKL")
MAX_CUPMARKET_PRICE = 120.0
SETTLEMENT_EXPLANATION_COLUMNS = {
    "exit_stage_floor",
    "performance_premium",
    "adjusted_settlement_value",
    "settlement_reason",
    "is_eliminated",
}

PRICE_REQUIRED_COLUMNS = {
    "team",
    "group",
    "live_elo",
    "cupmarket_price",
    "market_rank",
    "previous_price",
    "price_change",
    "price_change_percent",
    "generated_at_utc",
    "model_version",
    "bracket_mode",
    *SETTLEMENT_EXPLANATION_COLUMNS,
}

PROBABILITY_COLUMNS = {
    "prob_finish_1st_group",
    "prob_finish_2nd_group",
    "prob_finish_3rd_group",
    "prob_best_third_qualifier",
    "prob_reach_round_32",
    "prob_reach_round_16",
    "prob_reach_quarter_final",
    "prob_reach_semi_final",
    "prob_reach_final",
    "prob_champion",
    "prob_group_exit",
    "prob_round_32_exit",
    "prob_round_16_exit",
    "prob_quarter_final_exit",
    "prob_semi_final_exit",
    "prob_runner_up",
}

PROBABILITY_REQUIRED_COLUMNS = {
    "team",
    "group",
    "live_elo",
    "champion_rank",
    "generated_at_utc",
    "model_version",
    "bracket_mode",
    *PROBABILITY_COLUMNS,
    *SETTLEMENT_EXPLANATION_COLUMNS,
}

GROUP_TABLE_REQUIRED_COLUMNS = {
    "group",
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
}

MATCH_REQUIRED_COLUMNS = {
    "match_id",
    "utc_date",
    "status",
    "stage",
    "home_team",
    "away_team",
}

STAGE_TOTALS = {
    "prob_reach_round_32": 32.0,
    "prob_reach_round_16": 16.0,
    "prob_reach_quarter_final": 8.0,
    "prob_reach_semi_final": 4.0,
    "prob_reach_final": 2.0,
    "prob_champion": 1.0,
}

SETTLEMENT_PROBABILITY_COLUMNS = [
    "prob_group_exit",
    "prob_round_32_exit",
    "prob_round_16_exit",
    "prob_quarter_final_exit",
    "prob_semi_final_exit",
    "prob_runner_up",
    "prob_champion",
]


class ContractViolation(AssertionError):
    """Raised when a published CupMarket output breaks its data contract."""


@dataclass(frozen=True)
class OutputFrames:
    prices: pd.DataFrame
    probabilities: pd.DataFrame
    group_tables: pd.DataFrame
    matches: pd.DataFrame


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ContractViolation(f"{label} is missing columns: {', '.join(missing)}")


def _require_non_empty(frame: pd.DataFrame, label: str) -> None:
    if frame.empty:
        raise ContractViolation(f"{label} must not be empty")


def _require_unique(frame: pd.DataFrame, columns: Iterable[str], label: str) -> None:
    columns = list(columns)
    duplicates = frame.loc[frame.duplicated(columns, keep=False), columns]
    if not duplicates.empty:
        sample = duplicates.head(5).to_dict("records")
        raise ContractViolation(
            f"{label} contains duplicate keys for {columns}: {sample}"
        )


def _require_probability_bounds(frame: pd.DataFrame, label: str) -> None:
    values = frame[list(PROBABILITY_COLUMNS)].apply(pd.to_numeric, errors="coerce")
    if values.isna().any().any():
        bad_columns = values.columns[values.isna().any()].tolist()
        raise ContractViolation(
            f"{label} contains missing or non-numeric probabilities in: {bad_columns}"
        )

    bad = (values < -1e-9) | (values > 1.0 + 1e-9)
    if bad.any().any():
        locations = np.argwhere(bad.to_numpy())[:5]
        examples = [
            {
                "team": frame.iloc[row].get("team"),
                "column": values.columns[column],
                "value": float(values.iloc[row, column]),
            }
            for row, column in locations
        ]
        raise ContractViolation(f"{label} has probabilities outside [0, 1]: {examples}")


def _require_stage_totals(probabilities: pd.DataFrame) -> None:
    for column, expected in STAGE_TOTALS.items():
        actual = float(pd.to_numeric(probabilities[column], errors="raise").sum())
        if not np.isclose(actual, expected, atol=0.02):
            raise ContractViolation(
                f"{column} total is {actual:.6f}; expected approximately {expected:.2f}"
            )


def _require_settlement_distribution(probabilities: pd.DataFrame) -> None:
    totals = probabilities[SETTLEMENT_PROBABILITY_COLUMNS].sum(axis=1)
    bad = ~np.isclose(totals.to_numpy(dtype=float), 1.0, atol=1e-6)
    if bad.any():
        rows = probabilities.loc[bad, ["team"]].copy()
        rows["total"] = totals.loc[bad]
        raise ContractViolation(
            "Settlement outcome probabilities must sum to 1 per team: "
            f"{rows.head(5).to_dict('records')}"
        )


def _require_team_universe(frames: OutputFrames) -> None:
    prices_teams = set(frames.prices["team"].dropna())
    probability_teams = set(frames.probabilities["team"].dropna())
    table_teams = set(frames.group_tables["team"].dropna())

    if len(prices_teams) != EXPECTED_TEAM_COUNT:
        raise ContractViolation(
            f"prices must contain {EXPECTED_TEAM_COUNT} teams; found {len(prices_teams)}"
        )
    if prices_teams != probability_teams:
        raise ContractViolation("prices and probabilities contain different team sets")
    if prices_teams != table_teams:
        raise ContractViolation("prices and group tables contain different team sets")


def _require_group_shape(group_tables: pd.DataFrame) -> None:
    groups = set(group_tables["group"].dropna().astype(str))
    if groups != set(EXPECTED_GROUPS):
        raise ContractViolation(
            f"group tables must contain groups A-L; found {sorted(groups)}"
        )

    counts = group_tables.groupby("group")["team"].nunique()
    invalid = counts[counts != 4]
    if not invalid.empty:
        raise ContractViolation(
            f"every group must contain four teams: {invalid.to_dict()}"
        )

    expected_positions = {1, 2, 3, 4}
    for group, rows in group_tables.groupby("group"):
        positions = set(pd.to_numeric(rows["position"], errors="raise").astype(int))
        if positions != expected_positions:
            raise ContractViolation(
                f"group {group} positions must be 1-4; found {sorted(positions)}"
            )


def _require_group_table_arithmetic(group_tables: pd.DataFrame) -> None:
    numeric = group_tables[
        [
            "played",
            "wins",
            "draws",
            "losses",
            "goals_for",
            "goals_against",
            "goal_difference",
            "points",
        ]
    ].apply(pd.to_numeric, errors="raise")

    if not (numeric["played"] == numeric[["wins", "draws", "losses"]].sum(axis=1)).all():
        raise ContractViolation("played must equal wins + draws + losses")
    if not (numeric["goal_difference"] == numeric["goals_for"] - numeric["goals_against"]).all():
        raise ContractViolation("goal_difference must equal goals_for - goals_against")
    if not (numeric["points"] == 3 * numeric["wins"] + numeric["draws"]).all():
        raise ContractViolation("points must equal 3*wins + draws")


def _require_market_values(prices: pd.DataFrame) -> None:
    values = pd.to_numeric(prices["cupmarket_price"], errors="coerce")
    if values.isna().any():
        raise ContractViolation("cupmarket_price must be numeric and non-null")
    if ((values < 5.0 - 1e-9) | (values > MAX_CUPMARKET_PRICE + 1e-9)).any():
        raise ContractViolation(
            f"cupmarket_price must stay inside settlement bounds 5-{MAX_CUPMARKET_PRICE:g}"
        )

    ranks = pd.to_numeric(prices["market_rank"], errors="coerce")
    if ranks.isna().any() or set(ranks.astype(int)) != set(range(1, EXPECTED_TEAM_COUNT + 1)):
        raise ContractViolation("market_rank must contain every rank from 1 to 48 once")


def _require_timestamp(frame: pd.DataFrame, label: str) -> None:
    parsed = pd.to_datetime(frame["generated_at_utc"], errors="coerce", utc=True)
    if parsed.isna().any():
        raise ContractViolation(f"{label}.generated_at_utc contains invalid timestamps")
    if parsed.nunique() != 1:
        raise ContractViolation(f"{label} must contain one publication timestamp")


def load_output_frames(repo_root: Path) -> OutputFrames:
    data_dir = repo_root / "data"
    paths = {
        "prices": data_dir / "cupmarket_prices_latest.csv",
        "probabilities": data_dir / "tournament_probabilities_latest.csv",
        "group_tables": data_dir / "current_group_tables.csv",
        "matches": data_dir / "world_cup_2026_matches_latest.csv",
    }
    missing = [str(path.relative_to(repo_root)) for path in paths.values() if not path.exists()]
    if missing:
        raise ContractViolation(f"required output files are missing: {', '.join(missing)}")

    return OutputFrames(**{name: pd.read_csv(path) for name, path in paths.items()})


def validate_output_frames(frames: OutputFrames) -> None:
    for label, frame in {
        "prices": frames.prices,
        "probabilities": frames.probabilities,
        "group_tables": frames.group_tables,
        "matches": frames.matches,
    }.items():
        _require_non_empty(frame, label)

    _require_columns(frames.prices, PRICE_REQUIRED_COLUMNS, "prices")
    _require_columns(
        frames.probabilities,
        PROBABILITY_REQUIRED_COLUMNS,
        "probabilities",
    )
    _require_columns(frames.group_tables, GROUP_TABLE_REQUIRED_COLUMNS, "group_tables")
    _require_columns(frames.matches, MATCH_REQUIRED_COLUMNS, "matches")

    _require_unique(frames.prices, ["team"], "prices")
    _require_unique(frames.probabilities, ["team"], "probabilities")
    _require_unique(frames.group_tables, ["group", "team"], "group_tables")
    _require_unique(frames.matches, ["match_id"], "matches")

    _require_team_universe(frames)
    _require_group_shape(frames.group_tables)
    _require_group_table_arithmetic(frames.group_tables)
    _require_probability_bounds(frames.probabilities, "probabilities")
    _require_stage_totals(frames.probabilities)
    _require_settlement_distribution(frames.probabilities)
    _require_market_values(frames.prices)
    _require_timestamp(frames.prices, "prices")
    _require_timestamp(frames.probabilities, "probabilities")


def validate_repository_outputs(repo_root: Path | str) -> None:
    root = Path(repo_root).resolve()
    validate_output_frames(load_output_frames(root))
