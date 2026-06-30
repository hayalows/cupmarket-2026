from __future__ import annotations

import unittest

import pandas as pd

from features.tournament_insights import add_next_target_columns, next_meaningful_target


class TournamentInsightsTests(unittest.TestCase):
    def test_next_target_for_round_of_32_team(self):
        status, target, chance = next_meaningful_target(
            pd.Series(
                {
                    "prob_reach_round_16": 0.42,
                    "prob_reach_quarter_final": 0.20,
                    "prob_champion": 0.01,
                }
            )
        )

        self.assertEqual(status, "Round of 32")
        self.assertEqual(target, "Reach Round of 16")
        self.assertEqual(chance, "42.0%")

    def test_next_target_for_round_of_16_team(self):
        status, target, chance = next_meaningful_target(
            pd.Series(
                {
                    "prob_reach_round_16": 1.0,
                    "prob_reach_quarter_final": 0.35,
                    "prob_champion": 0.03,
                }
            )
        )

        self.assertEqual(status, "Round of 16")
        self.assertEqual(target, "Reach Quarter-final")
        self.assertEqual(chance, "35.0%")

    def test_eliminated_team_uses_exit_stage(self):
        status, target, chance = next_meaningful_target(
            pd.Series(
                {
                    "prob_round_32_exit": 1.0,
                    "prob_reach_round_16": 0.0,
                    "prob_champion": 0.0,
                }
            )
        )

        self.assertEqual(status, "Eliminated")
        self.assertEqual(target, "Out at Round of 32")
        self.assertEqual(chance, "—")

    def test_add_next_target_columns_keeps_mobile_order_fields(self):
        frame = pd.DataFrame(
            [
                {
                    "team": "Morocco",
                    "prob_reach_round_16": 1.0,
                    "prob_reach_quarter_final": 0.48,
                    "prob_champion": 0.02,
                }
            ]
        )

        result = add_next_target_columns(frame)

        self.assertEqual(result.iloc[0]["stage_status"], "Round of 16")
        self.assertEqual(result.iloc[0]["next_target"], "Reach Quarter-final")
        self.assertEqual(result.iloc[0]["next_target_chance"], "48.0%")


if __name__ == "__main__":
    unittest.main()
