from __future__ import annotations

import numpy as np
import pandas as pd


def install(update_pipeline) -> None:
    """Patch official upcoming fixtures with a safe Round-of-32 fallback.

    The provider can publish LAST_32 match rows before it fills the two qualified teams.
    The normal predictor correctly skips those blank rows. This fallback adds provisional
    LAST_32 fixtures from CupMarket's path-status file only when two qualified teams are
    already mapped to the same official match id.
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
        return 2

    def _fallback(world_cup: pd.DataFrame) -> pd.DataFrame:
        official = original(world_cup)
        path = update_pipeline.DATA_DIR / "round_32_path_status_latest.csv"
        if not path.exists():
            return official
        try:
            path_status = pd.read_csv(path)
        except (OSError, pd.errors.ParserError):
            return official

        required = {"team", "fixture_status", "confirmed_slot", "round_32_match_id", "prob_reach_round_32"}
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

        eligible = path_status.copy()
        eligible["round_32_match_id"] = pd.to_numeric(eligible["round_32_match_id"], errors="coerce")
        eligible["prob_reach_round_32"] = pd.to_numeric(eligible["prob_reach_round_32"], errors="coerce")
        eligible = eligible[
            eligible["round_32_match_id"].notna()
            & eligible["confirmed_slot"].notna()
            & (eligible["confirmed_slot"].astype(str).str.strip() != "")
            & (eligible["prob_reach_round_32"] >= 0.999)
            & ~eligible["fixture_status"].astype(str).str.contains("eliminated", case=False, na=False)
        ].copy()

        fallback_rows = []
        for match_id, group in eligible.groupby(eligible["round_32_match_id"].astype(int)):
            if int(match_id) in official_ids:
                continue
            source = knockout_rows[pd.to_numeric(knockout_rows["match_id"], errors="coerce") == int(match_id)]
            if source.empty or len(group) != 2:
                continue
            ordered = group.sort_values(
                by="confirmed_slot",
                key=lambda slots: slots.map(lambda value: _slot_order_key(int(match_id), str(value))),
            )
            home_team = str(ordered.iloc[0]["team"])
            away_team = str(ordered.iloc[1]["team"])
            if not update_pipeline.is_real_team_name(home_team) or not update_pipeline.is_real_team_name(away_team):
                continue
            row = source.iloc[0].copy()
            row["home_team"] = home_team
            row["away_team"] = away_team
            row["winner"] = np.nan
            row["home_score_full_time"] = np.nan
            row["away_score_full_time"] = np.nan
            row["provisional_fixture_source"] = "cupmarket_round_32_path_status"
            fallback_rows.append(row)

        if not fallback_rows:
            return official
        fallback = pd.DataFrame(fallback_rows)
        combined = pd.concat([official, fallback], ignore_index=True, sort=False)
        return combined.sort_values("utc_date").reset_index(drop=True)

    update_pipeline.official_upcoming_fixtures = _fallback
