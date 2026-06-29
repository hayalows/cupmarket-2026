from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MatchMinute:
    minute: int
    source: str
    raw_status: str
    kickoff_utc: str | None


LIVE_CLOCK_STATUSES = {"IN_PLAY", "LIVE"}
EXTRA_TIME_STATUS_MARKERS = {"EXTRA", "ET"}


def _value(row: pd.Series | dict[str, Any], key: str):
    return row.get(key) if hasattr(row, "get") else None


def _status(row: pd.Series | dict[str, Any]) -> str:
    return str(_value(row, "status") or "").upper()


def _stage(row: pd.Series | dict[str, Any]) -> str:
    return str(_value(row, "stage") or "").upper()


def _valid_number(value) -> float | None:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return None
    return float(number)


def _kickoff_iso(kickoff) -> str | None:
    if pd.isna(kickoff):
        return None
    return kickoff.isoformat()


def _has_extra_time_signal(row: pd.Series | dict[str, Any], raw_status: str) -> bool:
    if any(marker in raw_status for marker in EXTRA_TIME_STATUS_MARKERS):
        return True
    duration = str(_value(row, "duration") or "").upper()
    if "EXTRA" in duration:
        return True
    for column in (
        "home_score_extra_time",
        "away_score_extra_time",
        "home_extra_time_score",
        "away_extra_time_score",
    ):
        if _valid_number(_value(row, column)) is not None:
            return True
    return False


def _inferred_match_clock_minutes(wall_elapsed: float) -> float:
    if wall_elapsed <= 50:
        return wall_elapsed
    return wall_elapsed - 15


def resolve_match_minute_detail(
    row: pd.Series | dict[str, Any],
    *,
    allow_extra_time: bool = False,
    now: pd.Timestamp | None = None,
) -> MatchMinute:
    raw_status = _status(row)
    minute = _valid_number(_value(row, "minute"))
    kickoff = pd.to_datetime(_value(row, "utc_date"), errors="coerce", utc=True)
    kickoff_utc = _kickoff_iso(kickoff)
    max_minute = 120 if allow_extra_time else 90

    if minute is not None:
        return MatchMinute(
            minute=int(np.clip(minute, 0, max_minute)),
            source="api",
            raw_status=raw_status,
            kickoff_utc=kickoff_utc,
        )

    if raw_status == "PAUSED":
        return MatchMinute(
            minute=45,
            source="paused_default",
            raw_status=raw_status,
            kickoff_utc=kickoff_utc,
        )

    if raw_status in LIVE_CLOCK_STATUSES and pd.notna(kickoff):
        current = now or pd.Timestamp.now(tz="UTC")
        wall_elapsed = max(
            0.0,
            (current - kickoff).total_seconds() / 60.0,
        )
        clock_elapsed = max(0.0, _inferred_match_clock_minutes(wall_elapsed))
        extra_time_allowed = (
            allow_extra_time
            and (
                _has_extra_time_signal(row, raw_status)
                or (_stage(row) != "GROUP_STAGE" and wall_elapsed > 105)
            )
        )
        if extra_time_allowed:
            minute_value = int(np.clip(clock_elapsed, 1, 120))
        else:
            minute_value = int(np.clip(clock_elapsed, 1, 90))
        return MatchMinute(
            minute=minute_value,
            source="kickoff_inferred",
            raw_status=raw_status,
            kickoff_utc=kickoff_utc,
        )

    return MatchMinute(
        minute=0,
        source="unavailable",
        raw_status=raw_status,
        kickoff_utc=kickoff_utc,
    )


def resolve_match_minute(
    row: pd.Series | dict[str, Any],
    *,
    allow_extra_time: bool = False,
    now: pd.Timestamp | None = None,
) -> int:
    return resolve_match_minute_detail(
        row,
        allow_extra_time=allow_extra_time,
        now=now,
    ).minute
