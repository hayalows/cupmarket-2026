from __future__ import annotations

import unittest

import pandas as pd

from features import overview_v3


class TournamentPulseStateTests(unittest.TestCase):
    def test_eliminated_team_is_labelled_by_locked_exit_stage(self):
        prices = pd.DataFrame(
            [
                {
                    "team": "South Africa",
                    "cupmarket_price": 15.0,
                    "prob_round_32_exit": 1.0,
                    "prob_champion": 0.0,
                },
                {
                    "team": "Canada",
                    "cupmarket_price": 43.65,
                    "prob_round_32_exit": 0.0,
                    "prob_champion": 0.0157,
                },
            ]
        )

        eliminated = overview_v3._eliminated_teams(prices)
        alive = overview_v3._alive_teams(prices)

        self.assertEqual(eliminated.iloc[0]["Country"], "South Africa")
        self.assertEqual(eliminated.iloc[0]["Exit"], "Round of 32")
        self.assertEqual(alive.iloc[0]["team"], "Canada")

    def test_knockout_result_names_advanced_and_eliminated_teams(self):
        progress = pd.DataFrame(
            [
                {
                    "api_match_id": 537417,
                    "stage": "LAST_32",
                    "utc_date": pd.Timestamp("2026-06-28T19:00:00Z"),
                    "status": "FINISHED",
                    "home_team": "South Africa",
                    "away_team": "Canada",
                    "home_score": 0,
                    "away_score": 1,
                    "advancing_team": "Canada",
                }
            ]
        )

        results = overview_v3._knockout_results(pd.DataFrame(), progress)

        self.assertEqual(results.iloc[0]["Advanced"], "Canada")
        self.assertEqual(results.iloc[0]["Eliminated"], "South Africa")
        self.assertIn("South Africa 0-1 Canada", results.iloc[0]["Result"])


if __name__ == "__main__":
    unittest.main()
