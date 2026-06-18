from __future__ import annotations

from pathlib import Path
import unittest

import pandas as pd

from backend.output_contracts import (
    ContractViolation,
    OutputFrames,
    validate_output_frames,
    validate_repository_outputs,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class PublishedOutputContractTests(unittest.TestCase):
    def test_current_repository_outputs_satisfy_contract(self):
        validate_repository_outputs(REPO_ROOT)

    def test_duplicate_match_ids_are_rejected(self):
        frames = self._minimal_valid_frames()
        frames.matches.loc[1, "match_id"] = frames.matches.loc[0, "match_id"]

        with self.assertRaisesRegex(ContractViolation, "duplicate keys"):
            validate_output_frames(frames)

    def test_probability_outside_unit_interval_is_rejected(self):
        frames = self._minimal_valid_frames()
        frames.probabilities.loc[0, "prob_champion"] = 1.2

        with self.assertRaisesRegex(ContractViolation, "outside \\[0, 1\\]"):
            validate_output_frames(frames)

    def test_broken_group_table_arithmetic_is_rejected(self):
        frames = self._minimal_valid_frames()
        frames.group_tables.loc[0, "points"] = 99

        with self.assertRaisesRegex(ContractViolation, "points must equal"):
            validate_output_frames(frames)

    def test_missing_team_is_rejected(self):
        frames = self._minimal_valid_frames()
        frames.prices = frames.prices.iloc[:-1].copy()

        with self.assertRaisesRegex(ContractViolation, "prices must contain 48 teams"):
            validate_output_frames(frames)

    @staticmethod
    def _minimal_valid_frames() -> OutputFrames:
        teams = []
        for group in "ABCDEFGHIJKL":
            for position in range(1, 5):
                teams.append((f"Team {group}{position}", group, position))

        probability_rows = []
        price_rows = []
        group_rows = []
        generated_at = "2026-06-18T10:00:00+00:00"

        # Totals across 48 teams match the tournament bracket sizes exactly.
        reach_r32 = [1.0] * 32 + [0.0] * 16
        reach_r16 = [1.0] * 16 + [0.0] * 32
        reach_qf = [1.0] * 8 + [0.0] * 40
        reach_sf = [1.0] * 4 + [0.0] * 44
        reach_final = [1.0] * 2 + [0.0] * 46
        champion = [1.0] + [0.0] * 47

        for index, (team, group, position) in enumerate(teams):
            settlement = {
                "prob_group_exit": 1.0,
                "prob_round_32_exit": 0.0,
                "prob_round_16_exit": 0.0,
                "prob_quarter_final_exit": 0.0,
                "prob_semi_final_exit": 0.0,
                "prob_runner_up": 0.0,
                "prob_champion": 0.0,
            }
            if index < 32:
                settlement = {
                    "prob_group_exit": 0.0,
                    "prob_round_32_exit": 1.0,
                    "prob_round_16_exit": 0.0,
                    "prob_quarter_final_exit": 0.0,
                    "prob_semi_final_exit": 0.0,
                    "prob_runner_up": 0.0,
                    "prob_champion": 0.0,
                }
            if index < 16:
                settlement.update(
                    prob_round_32_exit=0.0,
                    prob_round_16_exit=1.0,
                )
            if index < 8:
                settlement.update(
                    prob_round_16_exit=0.0,
                    prob_quarter_final_exit=1.0,
                )
            if index < 4:
                settlement.update(
                    prob_quarter_final_exit=0.0,
                    prob_semi_final_exit=1.0,
                )
            if index < 2:
                settlement.update(
                    prob_semi_final_exit=0.0,
                    prob_runner_up=1.0,
                )
            if index == 0:
                settlement.update(prob_runner_up=0.0, prob_champion=1.0)

            probability_rows.append(
                {
                    "team": team,
                    "group": group,
                    "live_elo": 1500.0,
                    "prob_finish_1st_group": 0.25,
                    "prob_finish_2nd_group": 0.25,
                    "prob_finish_3rd_group": 0.25,
                    "prob_best_third_qualifier": 0.125,
                    "prob_reach_round_32": reach_r32[index],
                    "prob_reach_round_16": reach_r16[index],
                    "prob_reach_quarter_final": reach_qf[index],
                    "prob_reach_semi_final": reach_sf[index],
                    "prob_reach_final": reach_final[index],
                    **settlement,
                    "champion_rank": index + 1,
                    "generated_at_utc": generated_at,
                    "model_version": "test",
                    "bracket_mode": "test",
                }
            )

            price_rows.append(
                {
                    **probability_rows[-1],
                    "cupmarket_price": 100.0 - index,
                    "market_rank": index + 1,
                    "previous_price": 100.0 - index,
                    "price_change": 0.0,
                    "price_change_percent": 0.0,
                }
            )

            group_rows.append(
                {
                    "group": group,
                    "position": position,
                    "team": team,
                    "played": 0,
                    "wins": 0,
                    "draws": 0,
                    "losses": 0,
                    "goals_for": 0,
                    "goals_against": 0,
                    "goal_difference": 0,
                    "points": 0,
                }
            )

        matches = pd.DataFrame(
            [
                {
                    "match_id": 1,
                    "utc_date": "2026-06-11T00:00:00Z",
                    "status": "FINISHED",
                    "stage": "GROUP_STAGE",
                    "home_team": "Team A1",
                    "away_team": "Team A2",
                },
                {
                    "match_id": 2,
                    "utc_date": "2026-06-12T00:00:00Z",
                    "status": "TIMED",
                    "stage": "GROUP_STAGE",
                    "home_team": "Team A3",
                    "away_team": "Team A4",
                },
            ]
        )

        return OutputFrames(
            prices=pd.DataFrame(price_rows),
            probabilities=pd.DataFrame(probability_rows),
            group_tables=pd.DataFrame(group_rows),
            matches=matches,
        )


if __name__ == "__main__":
    unittest.main()
