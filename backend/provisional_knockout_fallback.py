from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd


THIRD_PLACE_CERTAINTY = 0.999


def install(update_pipeline) -> None:
    """Patch official upcoming fixtures with a deterministic Round-of-32 fallback.

    The provider can publish LAST_32 match rows before it fills the two qualified teams.
    The normal predictor correctly skips those blank rows. This fallback fills safe
    provisional LAST_32 fixtures from CupMarket's path-status file.

    After every group is complete, third-place assignments are locked once instead of
    sampled, so the prediction engine can publish every Round-of-32 forecast before the
    provider catches up.
    """
    original = update_pipeline.official_upcoming_fixtures

    def _slot_order_key(match_id: int, slot: str) -> int:
        fixed_pair = update_pipeline.FIXED_R32.get(int(match_id))
        if fixed_pair and slot in fixed_pair:
            return fixed_pair.index(slot)
        if str(slot).startswith("1"):
            return 0
        if str(slot).startswith("2"):
            return 1
        if str(slot).startswith("3"):
            return 1
        return 2

    def _path_row(path_status: pd.DataFrame, team: str) -> pd.Series | None:
        rows = path_status[path_status["team"].astype(str).eq(str(team))]
        if rows.empty:
            return None
        return rows.iloc[0]

    def _build_team_by_slot(path_status: pd.DataFrame) -> dict[str, str]:
        confirmed = path_status.copy()
        confirmed["prob_reach_round_32"] = pd.to_numeric(
            confirmed["prob_reach_round_32"], errors="coerce"
        ).fillna(0.0)
        confirmed = confirmed[
            confirmed["confirmed_slot"].notna()
            & (confirmed["confirmed_slot"].astype(str).str.strip() != "")
            & (confirmed["prob_reach_round_32"] >= THIRD_PLACE_CERTAINTY)
            & ~confirmed["fixture_status"].astype(str).str.contains(
                "eliminated", case=False, na=False
            )
        ]
        return {
            str(row.confirmed_slot): str(row.team)
            for row in confirmed.itertuples(index=False)
        }

    def _third_place_candidates(path_status: pd.DataFrame) -> dict[str, str]:
        third = path_status.copy()
        third["prob_reach_round_32"] = pd.to_numeric(
            third["prob_reach_round_32"], errors="coerce"
        ).fillna(0.0)
        third = third[
            third["confirmed_slot"].astype(str).str.startswith("3", na=False)
            & (third["prob_reach_round_32"] >= THIRD_PLACE_CERTAINTY)
            & ~third["fixture_status"].astype(str).str.contains(
                "eliminated", case=False, na=False
            )
        ]
        return {
            str(row.group): str(row.team)
            for row in third.itertuples(index=False)
        }

    def _pair_score(path_status: pd.DataFrame, favourite: str, third_team: str) -> float:
        score = 0.0
        favourite_row = _path_row(path_status, favourite)
        third_row = _path_row(path_status, third_team)
        if favourite_row is not None and str(favourite_row.get("most_likely_opponent", "")) == third_team:
            score += float(pd.to_numeric(favourite_row.get("most_likely_opponent_probability_unconditional"), errors="coerce") or 0.0)
        if third_row is not None and str(third_row.get("most_likely_opponent", "")) == favourite:
            score += float(pd.to_numeric(third_row.get("most_likely_opponent_probability_unconditional"), errors="coerce") or 0.0)
        return score

    def _deterministic_third_assignment(path_status: pd.DataFrame) -> dict[int, str]:
        third_by_group = _third_place_candidates(path_status)
        if len(third_by_group) != 8:
            return {}
        groups = tuple(sorted(third_by_group))
        assignments = update_pipeline.valid_third_place_assignments(groups)
        if not assignments:
            return {}

        team_by_slot = _build_team_by_slot(path_status)
        best_assignment = None
        best_key = None
        for assignment in assignments:
            slot_to_group = dict(assignment)
            total_score = 0.0
            exact_pair_count = 0
            for slot, group in slot_to_group.items():
                favourite_slot = update_pipeline.THIRD_PLACE_R32_WINNER[int(slot)]
                favourite = team_by_slot.get(favourite_slot)
                third_team = third_by_group.get(group)
                if favourite and third_team:
                    pair_score = _pair_score(path_status, favourite, third_team)
                    total_score += pair_score
                    if pair_score >= 0.999:
                        exact_pair_count += 1
            # Stable tie-breaker keeps the same bracket on every run.
            key = (
                round(total_score, 9),
                exact_pair_count,
                tuple(sorted((int(slot), group) for slot, group in slot_to_group.items())),
            )
            if best_key is None or key > best_key:
                best_key = key
                best_assignment = slot_to_group

        if best_assignment is None:
            return {}
        return {
            int(slot): third_by_group[group]
            for slot, group in dict(best_assignment).items()
        }

    def _candidate_pairs(path_status: pd.DataFrame) -> dict[int, tuple[str, str]]:
        team_by_slot = _build_team_by_slot(path_status)
        pairs: dict[int, tuple[str, str]] = {}

        for match_id, slots in update_pipeline.FIXED_R32.items():
            if slots[0] in team_by_slot and slots[1] in team_by_slot:
                pairs[int(match_id)] = (team_by_slot[slots[0]], team_by_slot[slots[1]])

        third_assignment = _deterministic_third_assignment(path_status)
        for match_id, favourite_slot in update_pipeline.THIRD_PLACE_R32_WINNER.items():
            favourite = team_by_slot.get(favourite_slot)
            third_team = third_assignment.get(int(match_id))
            if favourite and third_team:
                pairs[int(match_id)] = (favourite, third_team)

        return pairs

    def _fallback(world_cup: pd.DataFrame) -> pd.DataFrame:
        official = original(world_cup)
        path = update_pipeline.DATA_DIR / "round_32_path_status_latest.csv"
        if not path.exists():
            return official
        try:
            path_status = pd.read_csv(path)
        except (OSError, pd.errors.ParserError):
            return official

        required = {
            "team",
            "group",
            "fixture_status",
            "confirmed_slot",
            "round_32_match_id",
            "prob_reach_round_32",
            "most_likely_opponent",
            "most_likely_opponent_probability_unconditional",
        }
        if path_status.empty or not required.issubset(path_status.columns):
            return official

        knockout_rows = world_cup[
            (world_cup["stage"] == "LAST_32")
            & world_cup["status"].isin(update_pipeline.UPCOMING_MATCH_STATUSES)
        ].copy()
        if knockout_rows.empty:
            return official

        official_ids = set(
            pd.to_numeric(official.get("match_id", pd.Series(dtype=float)), errors="coerce")
            .dropna()
            .astype(int)
            .tolist()
        )

        pairs = _candidate_pairs(path_status)
        fallback_rows = []
        for match_id, (home_team, away_team) in pairs.items():
            if int(match_id) in official_ids:
                continue
            source = knockout_rows[
                pd.to_numeric(knockout_rows["match_id"], errors="coerce") == int(match_id)
            ]
            if source.empty:
                continue
            if not update_pipeline.is_real_team_name(home_team) or not update_pipeline.is_real_team_name(away_team):
                continue
            row = source.iloc[0].copy()
            row["home_team"] = home_team
            row["away_team"] = away_team
            row["winner"] = np.nan
            row["home_score_full_time"] = np.nan
            row["away_score_full_time"] = np.nan
            row["provisional_fixture_source"] = "cupmarket_deterministic_round_32_lock"
            fallback_rows.append(row)

        if not fallback_rows:
            return official
        fallback = pd.DataFrame(fallback_rows)
        combined = pd.concat([official, fallback], ignore_index=True, sort=False)
        return combined.sort_values("utc_date").reset_index(drop=True)

    update_pipeline.official_upcoming_fixtures = _fallback
