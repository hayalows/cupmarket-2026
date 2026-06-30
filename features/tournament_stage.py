from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

EMPTY_VALUE = "\u2014"
LOCKED_THRESHOLD = 0.999
LIVE_STATUSES = {"IN_PLAY", "LIVE", "PAUSED", "SUSPENDED"}
UPCOMING_STATUSES = {"TIMED", "SCHEDULED"}
FINISHED_STATUSES = {"FINISHED", "AWARDED"}


CONTINENT_MAP = {
    "Algeria": "Africa",
    "Argentina": "South America",
    "Australia": "Asia/Oceania",
    "Austria": "Europe",
    "Belgium": "Europe",
    "Bosnia-Herzegovina": "Europe",
    "Brazil": "South America",
    "Canada": "North America",
    "Cape Verde Islands": "Africa",
    "Colombia": "South America",
    "Congo DR": "Africa",
    "Croatia": "Europe",
    "Cura\u00e7ao": "North America",
    "Cura\ufffdao": "North America",
    "Czechia": "Europe",
    "Ecuador": "South America",
    "Egypt": "Africa",
    "England": "Europe",
    "France": "Europe",
    "Germany": "Europe",
    "Ghana": "Africa",
    "Haiti": "North America",
    "Iran": "Asia",
    "Iraq": "Asia",
    "Ivory Coast": "Africa",
    "Japan": "Asia",
    "Jordan": "Asia",
    "Mexico": "North America",
    "Morocco": "Africa",
    "Netherlands": "Europe",
    "New Zealand": "Oceania",
    "Norway": "Europe",
    "Panama": "North America",
    "Paraguay": "South America",
    "Portugal": "Europe",
    "Qatar": "Asia",
    "Saudi Arabia": "Asia",
    "Scotland": "Europe",
    "Senegal": "Africa",
    "South Africa": "Africa",
    "South Korea": "Asia",
    "Spain": "Europe",
    "Sweden": "Europe",
    "Switzerland": "Europe",
    "Tunisia": "Africa",
    "Turkey": "Europe",
    "United States": "North America",
    "Uruguay": "South America",
    "Uzbekistan": "Asia",
}


@dataclass(frozen=True)
class StageTarget:
    key: str
    label: str
    reach_column: str
    status_label: str
    target_label: str
    exit_column: str | None = None
    exit_label: str | None = None
    match_stage_keys: tuple[str, ...] = ()


STAGE_TARGETS = [
    StageTarget(
        key="ROUND_32",
        label="Round of 32",
        reach_column="prob_reach_round_32",
        status_label="Group stage",
        target_label="Reach Round of 32",
        exit_column="prob_group_exit",
        exit_label="Group stage",
        match_stage_keys=("GROUP_STAGE",),
    ),
    StageTarget(
        key="ROUND_16",
        label="Round of 16",
        reach_column="prob_reach_round_16",
        status_label="Round of 32",
        target_label="Reach Round of 16",
        exit_column="prob_round_32_exit",
        exit_label="Round of 32",
        match_stage_keys=("LAST_32", "ROUND_OF_32", "R32"),
    ),
    StageTarget(
        key="QUARTER_FINAL",
        label="Quarter-final",
        reach_column="prob_reach_quarter_final",
        status_label="Round of 16",
        target_label="Reach Quarter-final",
        exit_column="prob_round_16_exit",
        exit_label="Round of 16",
        match_stage_keys=("LAST_16", "ROUND_OF_16", "R16"),
    ),
    StageTarget(
        key="SEMI_FINAL",
        label="Semi-final",
        reach_column="prob_reach_semi_final",
        status_label="Quarter-final",
        target_label="Reach Semi-final",
        exit_column="prob_quarter_final_exit",
        exit_label="Quarter-final",
        match_stage_keys=("QUARTER_FINALS", "QUARTER_FINAL", "QF"),
    ),
    StageTarget(
        key="FINAL",
        label="Final",
        reach_column="prob_reach_final",
        status_label="Semi-final",
        target_label="Reach Final",
        exit_column="prob_semi_final_exit",
        exit_label="Semi-final",
        match_stage_keys=("SEMI_FINALS", "SEMI_FINAL", "SF"),
    ),
    StageTarget(
        key="CHAMPION",
        label="Champion",
        reach_column="prob_champion",
        status_label="Final",
        target_label="Win tournament",
        exit_column="prob_runner_up",
        exit_label="Final",
        match_stage_keys=("FINAL",),
    ),
]

STAGE_BY_KEY = {stage.key: stage for stage in STAGE_TARGETS}
MATCH_STAGE_TO_TARGET = {
    alias: stage
    for stage in STAGE_TARGETS
    for alias in stage.match_stage_keys
}
EXIT_STAGE_COLUMNS = [
    (stage.exit_column, stage.exit_label)
    for stage in STAGE_TARGETS
    if stage.exit_column and stage.exit_label
]
REACH_PROBABILITY_COLUMNS = [stage.reach_column for stage in STAGE_TARGETS]
PROBABILITY_COLUMNS = sorted(
    set(REACH_PROBABILITY_COLUMNS + [column for column, _ in EXIT_STAGE_COLUMNS])
)


def probability(value: Any, default: float = 0.0) -> float:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return default
    return float(number)


def percent(value: Any, digits: int = 1) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return EMPTY_VALUE
    return f"{100 * float(number):.{digits}f}%"


def percentage_points(value: Any, digits: int = 1) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return EMPTY_VALUE
    return f"{100 * float(number):+.{digits}f} pts"


def normal_stage(value: Any) -> str:
    raw = str(value or "").upper()
    if raw in {"ROUND_OF_32", "R32"}:
        return "LAST_32"
    if raw in {"ROUND_OF_16", "R16"}:
        return "LAST_16"
    if raw in {"QUARTER_FINAL", "QF"}:
        return "QUARTER_FINALS"
    if raw in {"SEMI_FINAL", "SF"}:
        return "SEMI_FINALS"
    return raw


def stage_for_match_stage(value: Any) -> StageTarget:
    key = normal_stage(value)
    return MATCH_STAGE_TO_TARGET.get(key, STAGE_BY_KEY["ROUND_32"])


def next_meaningful_target(row: pd.Series) -> tuple[str, str, str]:
    for column, stage in EXIT_STAGE_COLUMNS:
        if probability(row.get(column)) >= LOCKED_THRESHOLD:
            return "Eliminated", f"Out at {stage}", EMPTY_VALUE

    for stage in STAGE_TARGETS[1:]:
        chance = probability(row.get(stage.reach_column))
        if chance < LOCKED_THRESHOLD:
            return stage.status_label, stage.target_label, percent(chance)

    champion = probability(row.get("prob_champion"))
    if champion >= LOCKED_THRESHOLD:
        return "Champion", "Champion", "100.0%"
    return "Final", "Win tournament", percent(champion)


def add_continent_column(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    result = frame.copy()
    if "team" in result.columns:
        result["continent"] = result["team"].map(CONTINENT_MAP).fillna("Other")
    else:
        result["continent"] = "Other"
    return result


def add_next_target_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    result = frame.copy()
    targets = result.apply(next_meaningful_target, axis=1)
    result["stage_status"] = [status for status, _, _ in targets]
    result["next_target"] = [target for _, target, _ in targets]
    result["next_target_chance"] = [chance for _, _, chance in targets]
    return result


def current_stage_target(
    prices: pd.DataFrame,
    progress: pd.DataFrame | None = None,
) -> StageTarget:
    progress = progress if isinstance(progress, pd.DataFrame) else pd.DataFrame()
    if not progress.empty and {"stage", "status"}.issubset(progress.columns):
        frame = progress.copy()
        frame["stage_key"] = frame["stage"].map(normal_stage)
        if "utc_date" in frame.columns:
            frame["utc_date"] = pd.to_datetime(frame["utc_date"], errors="coerce", utc=True)

        for statuses, ascending in [
            (LIVE_STATUSES, True),
            (UPCOMING_STATUSES, True),
            (FINISHED_STATUSES, False),
        ]:
            rows = frame.loc[frame["status"].astype(str).str.upper().isin(statuses)].copy()
            if rows.empty:
                continue
            if "utc_date" in rows.columns:
                rows = rows.sort_values("utc_date", ascending=ascending, na_position="last")
            return stage_for_match_stage(rows.iloc[0]["stage_key"])

    if isinstance(prices, pd.DataFrame) and not prices.empty:
        for stage in STAGE_TARGETS[1:]:
            if stage.reach_column not in prices.columns:
                continue
            values = pd.to_numeric(prices[stage.reach_column], errors="coerce").fillna(0.0)
            if ((values > 0.0) & (values < LOCKED_THRESHOLD)).any():
                return stage
    return STAGE_BY_KEY["ROUND_32"]


def _short_list(values: list[str], limit: int = 4) -> str:
    cleaned = [str(value) for value in values if str(value).strip()]
    if not cleaned:
        return EMPTY_VALUE
    head = cleaned[:limit]
    suffix = f" +{len(cleaned) - limit}" if len(cleaned) > limit else ""
    return ", ".join(head) + suffix


def stage_ladder(prices: pd.DataFrame, *, leader_limit: int = 4) -> pd.DataFrame:
    if prices.empty or "team" not in prices.columns:
        return pd.DataFrame()
    frame = add_continent_column(prices)
    rows = []
    for stage_order, stage in enumerate(STAGE_TARGETS):
        if stage.reach_column not in frame.columns:
            continue
        values = pd.to_numeric(frame[stage.reach_column], errors="coerce").fillna(0.0)
        locked = frame.loc[values >= LOCKED_THRESHOLD].copy()
        possible = frame.loc[(values > 0.0) & (values < LOCKED_THRESHOLD)].copy()
        leaders = frame.assign(_chance=values).sort_values(
            ["_chance", "cupmarket_price"] if "cupmarket_price" in frame.columns else ["_chance"],
            ascending=False,
        )
        leaders = leaders.loc[leaders["_chance"] > 0.0].head(leader_limit)

        if locked.empty:
            continent_source = leaders
            continent_label = "Projected"
        else:
            continent_source = locked
            continent_label = "Confirmed"
        if continent_source.empty:
            continent_picture = EMPTY_VALUE
        else:
            counts = (
                continent_source.groupby("continent")["team"]
                .count()
                .sort_values(ascending=False)
            )
            continent_picture = ", ".join(
                f"{continent} {int(count)}" for continent, count in counts.items()
            )

        rows.append(
            {
                "Stage": stage.label,
                "Confirmed": int(len(locked)),
                "Still possible": int(len(possible)),
                "Leading countries": _short_list(leaders["team"].astype(str).tolist()),
                "Continent picture": f"{continent_label}: {continent_picture}",
            }
        )
    return pd.DataFrame(rows)


def continent_ladder(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty or "team" not in prices.columns:
        return pd.DataFrame()
    frame = add_continent_column(prices)
    rows = []
    for stage_order, stage in enumerate(STAGE_TARGETS):
        if stage.reach_column not in frame.columns:
            continue
        working = frame.copy()
        working["_chance"] = pd.to_numeric(
            working[stage.reach_column], errors="coerce"
        ).fillna(0.0)
        working["_locked"] = working["_chance"] >= LOCKED_THRESHOLD
        working = working.loc[working["_chance"] > 0.0].copy()
        if working.empty:
            continue
        for continent, group in working.groupby("continent"):
            locked = group.loc[group["_locked"]]
            contenders = group.loc[~group["_locked"]]
            leaders = group.sort_values("_chance", ascending=False).head(4)
            best_chance = leaders["_chance"].max()
            rows.append(
                {
                    "_stage_order": stage_order,
                    "_best_chance_sort": float(best_chance),
                    "Stage": stage.label,
                    "Continent": continent,
                    "Confirmed": int(len(locked)),
                    "Still possible": int(len(contenders)),
                    "Best chance": percent(best_chance),
                    "Countries": _short_list(leaders["team"].astype(str).tolist()),
                }
            )
    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows).sort_values(
        ["_stage_order", "Confirmed", "Still possible", "_best_chance_sort"],
        ascending=[True, False, False, False],
    )
    return result.drop(columns=["_stage_order", "_best_chance_sort"], errors="ignore")


def stage_probability_facts(
    prices: pd.DataFrame,
    progress: pd.DataFrame | None = None,
    *,
    limit: int = 5,
) -> list[str]:
    if prices.empty or "team" not in prices.columns:
        return []
    facts: list[str] = []
    focus = current_stage_target(prices, progress)
    values = pd.to_numeric(prices.get(focus.reach_column), errors="coerce").fillna(0.0)
    locked = prices.loc[values >= LOCKED_THRESHOLD, "team"].astype(str).tolist()
    possible = prices.loc[(values > 0.0) & (values < LOCKED_THRESHOLD), "team"].astype(str).tolist()
    if locked:
        facts.append(
            f"{_short_list(locked, limit)} are officially in {focus.label}."
        )
    if possible:
        facts.append(
            f"{len(possible)} countries still have a live path to {focus.label}."
        )

    champion = pd.to_numeric(prices.get("prob_champion"), errors="coerce").fillna(0.0)
    if not champion.empty:
        leader = prices.assign(_chance=champion).sort_values("_chance", ascending=False).iloc[0]
        facts.append(
            f"{leader['team']} has the highest title chance at {percent(leader['_chance'])}."
        )
    return facts
