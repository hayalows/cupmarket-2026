from __future__ import annotations

import unittest

import pandas as pd

from features import tournament_stage


class TournamentStageTests(unittest.TestCase):
    def test_live_round_of_32_focuses_on_round_of_16_target(self):
        prices = pd.DataFrame(
            [
                {
                    "team": "Canada",
                    "prob_reach_round_32": 1.0,
                    "prob_reach_round_16": 1.0,
                    "prob_reach_quarter_final": 0.52,
                    "prob_champion": 0.02,
                },
                {
                    "team": "Norway",
                    "prob_reach_round_32": 1.0,
                    "prob_reach_round_16": 0.67,
                    "prob_reach_quarter_final": 0.30,
                    "prob_champion": 0.01,
                },
            ]
        )
        progress = pd.DataFrame(
            [
                {
                    "stage": "LAST_32",
                    "status": "IN_PLAY",
                    "utc_date": "2026-06-30T17:00:00Z",
                }
            ]
        )

        focus = tournament_stage.current_stage_target(prices, progress)

        self.assertEqual(focus.label, "Round of 16")
        self.assertEqual(focus.reach_column, "prob_reach_round_16")

    def test_stage_ladder_counts_confirmed_and_possible_teams(self):
        prices = pd.DataFrame(
            [
                {
                    "team": "Canada",
                    "cupmarket_price": 45.2,
                    "prob_reach_round_32": 1.0,
                    "prob_reach_round_16": 1.0,
                    "prob_reach_quarter_final": 0.52,
                    "prob_champion": 0.02,
                },
                {
                    "team": "South Africa",
                    "cupmarket_price": 0.0,
                    "prob_reach_round_32": 1.0,
                    "prob_reach_round_16": 0.0,
                    "prob_reach_quarter_final": 0.0,
                    "prob_champion": 0.0,
                    "prob_round_32_exit": 1.0,
                },
                {
                    "team": "Norway",
                    "cupmarket_price": 35.0,
                    "prob_reach_round_32": 1.0,
                    "prob_reach_round_16": 0.67,
                    "prob_reach_quarter_final": 0.30,
                    "prob_champion": 0.01,
                },
            ]
        )

        ladder = tournament_stage.stage_ladder(prices)
        round_16 = ladder.loc[ladder["Stage"].eq("Round of 16")].iloc[0]

        self.assertEqual(round_16["Confirmed"], 1)
        self.assertEqual(round_16["Still possible"], 1)
        self.assertIn("Canada", round_16["Leading countries"])

    def test_continent_ladder_keeps_tournament_stage_order(self):
        prices = pd.DataFrame(
            [
                {
                    "team": "Canada",
                    "prob_reach_round_32": 1.0,
                    "prob_reach_round_16": 1.0,
                    "prob_champion": 0.02,
                },
                {
                    "team": "Brazil",
                    "prob_reach_round_32": 1.0,
                    "prob_reach_round_16": 1.0,
                    "prob_champion": 0.08,
                },
            ]
        )

        ladder = tournament_stage.continent_ladder(prices)

        self.assertEqual(ladder.iloc[0]["Stage"], "Round of 32")


if __name__ == "__main__":
    unittest.main()
