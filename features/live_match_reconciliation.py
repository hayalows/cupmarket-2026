from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

FINISHED_STATUSES = frozenset({"FINISHED", "AWARDED"})
ACTIVE_PLAY_STATUSES = frozenset({"IN_PLAY", "PAUSED"})
STALE_PROVIDER_STATUS = "AWAITING_CONFIRMATION"

_TERMINAL_COPY_COLUMNS = (
    "status",
    "winner",
    "duration",
    "home_score_full_time",
    "away_score_full_time",
    "minute",
    "injury_time",
    "last_updated",
)
_TERMINAL_SIGNATURE_COLUMNS = (
    "status",
    "winner",
    "duration",
    "home_score_full_time",
    "away_score_full_time",
)


@dataclass(frozen=True)
class TerminalReconciliationReport:
    """Summary of terminal states restored or officially corrected."""

    restored_match_ids: tuple[int, ...] = ()
    corrected_match_ids: tuple[int, ...] = ()
    appended_match_ids: tuple[int, ...] = ()

    @property
    def changed_match_ids(self) -> tuple[int, ...]:
        return tuple(
            sorted(
                set(self.restored_match_ids)
                | set(self.corrected_match_ids)
                | set(self.appended_match_ids)
            )
        )


def _normalise_match_ids(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "match_id" not in frame.columns:
        return frame.copy()
    result = frame.copy()
    result["match_id"] = pd.to_numeric(result["match_id"], errors="coerce")
    result = result.dropna(subset=["match_id"])
    result["match_id"] = result["match_id"].astype(int)
    return result


def _as_utc_timestamp(value) -> pd.Timestamp | None:
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    return None if pd.isna(timestamp) else timestamp


def _candidate_is_newer(candidate: pd.Series, current: pd.Series) -> bool:
    candidate_updated = _as_utc_timestamp(candidate.get("last_updated"))
    current_updated = _as_utc_timestamp(current.get("last_updated"))
    if candidate_updated is None:
        return False
    if current_updated is None:
        return True
    return candidate_updated > current_updated


def _terminal_signature(row: pd.Series) -> tuple:
    return tuple(row.get(column) for column in _TERMINAL_SIGNATURE_COLUMNS)


def _copy_terminal_fields(
    frame: pd.DataFrame,
    index,
    terminal_row: pd.Series,
) -> None:
    for column in _TERMINAL_COPY_COLUMNS:
        if column not in terminal_row.index:
            continue
        if column not in frame.columns:
            frame[column] = pd.NA
        frame.at[index, column] = terminal_row[column]


def merge_terminal_states(
    current: pd.DataFrame,
    trusted: pd.DataFrame,
) -> tuple[pd.DataFrame, TerminalReconciliationReport]:
    """Merge terminal match states without allowing status regression.

    Rules:
    - A confirmed finished result overrides a live, scheduled, or uncertain state.
    - A newer confirmed terminal record may correct an older terminal result.
    - An older terminal record never overwrites a newer terminal record.

    The function is pure and does not read files, network data, or Streamlit state.
    """
    frame = _normalise_match_ids(current)
    trusted_frame = _normalise_match_ids(trusted)
    if trusted_frame.empty or "status" not in trusted_frame.columns:
        return frame, TerminalReconciliationReport()

    terminal = trusted_frame[
        trusted_frame["status"].isin(FINISHED_STATUSES)
    ].drop_duplicates("match_id", keep="last")
    if terminal.empty:
        return frame, TerminalReconciliationReport()

    restored: set[int] = set()
    corrected: set[int] = set()
    appended: set[int] = set()

    for terminal_row in terminal.itertuples(index=False):
        candidate = pd.Series(terminal_row._asdict())
        match_id = int(candidate["match_id"])
        matching_indexes = (
            frame.index[frame["match_id"] == match_id]
            if not frame.empty and "match_id" in frame.columns
            else []
        )

        if len(matching_indexes) == 0:
            frame = pd.concat(
                [frame, pd.DataFrame([candidate.to_dict()])],
                ignore_index=True,
                sort=False,
            )
            appended.add(match_id)
            continue

        index = matching_indexes[0]
        current_row = frame.loc[index]
        current_status = str(current_row.get("status", ""))

        if current_status not in FINISHED_STATUSES:
            _copy_terminal_fields(frame, index, candidate)
            restored.add(match_id)
            continue

        if not _candidate_is_newer(candidate, current_row):
            continue

        signature_changed = _terminal_signature(candidate) != _terminal_signature(
            current_row
        )
        _copy_terminal_fields(frame, index, candidate)
        if signature_changed:
            corrected.add(match_id)

    sort_columns = [
        column for column in ("utc_date", "match_id") if column in frame.columns
    ]
    if sort_columns:
        frame = frame.sort_values(sort_columns).reset_index(drop=True)

    return frame, TerminalReconciliationReport(
        restored_match_ids=tuple(sorted(restored)),
        corrected_match_ids=tuple(sorted(corrected)),
        appended_match_ids=tuple(sorted(appended)),
    )


def mark_impossible_live_states(
    matches: pd.DataFrame,
    now: pd.Timestamp | None = None,
    *,
    maximum_match_hours: int = 4,
) -> tuple[pd.DataFrame, list[dict]]:
    """Quarantine active statuses that conflict with the match timeline.

    The function does not invent a final result. It only removes a misleading live
    label until a trusted terminal state becomes available.
    """
    required = {"status", "utc_date"}
    if matches.empty or not required.issubset(matches.columns):
        return matches.copy(), []

    frame = matches.copy()
    current_time = now or pd.Timestamp.now(tz="UTC")
    kickoff = pd.to_datetime(frame["utc_date"], errors="coerce", utc=True)
    active_mask = frame["status"].isin(ACTIVE_PLAY_STATUSES)
    too_old_mask = kickoff <= current_time - pd.Timedelta(hours=maximum_match_hours)

    finished_kickoffs = kickoff[frame["status"].isin(FINISHED_STATUSES)].dropna()
    latest_finished_kickoff = (
        finished_kickoffs.max() if not finished_kickoffs.empty else pd.NaT
    )
    later_match_finished_mask = (
        pd.Series(False, index=frame.index)
        if pd.isna(latest_finished_kickoff)
        else kickoff < latest_finished_kickoff
    )

    stale_mask = active_mask & (too_old_mask | later_match_finished_mask)
    stale_records: list[dict] = []
    for index in frame.index[stale_mask]:
        match_id = pd.to_numeric(frame.at[index, "match_id"], errors="coerce")
        stale_records.append(
            {
                "match_id": int(match_id) if pd.notna(match_id) else None,
                "home_team": frame.at[index, "home_team"]
                if "home_team" in frame.columns
                else None,
                "away_team": frame.at[index, "away_team"]
                if "away_team" in frame.columns
                else None,
                "reported_status": frame.at[index, "status"],
                "kickoff_utc": kickoff.at[index].isoformat()
                if pd.notna(kickoff.at[index])
                else None,
            }
        )
        frame.at[index, "status"] = STALE_PROVIDER_STATUS

    return frame, stale_records
