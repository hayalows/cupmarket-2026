from __future__ import annotations

import unittest

import pandas as pd

from features import tournament_path_page as page


class TournamentPathPageTests(unittest.TestCase):
    def test_finished_round_of_32_fixture_overrides_confirmed_path_label(self):
        fixture = pd.Series(
            {
                "stage": "LAST_32",
                "status": "FINISHED",
                "home_team": "South Africa",
                "away_team": "Canada",
                "home_score": 0,
                "away_score": 1,
                "advancing_team": "Canada",
            }
        )
        price = pd.Series({"prob_reach_round_16": 1.0})

        state = page._team_result_state(fixture, "Canada")
        reach_label, reach_value = page._reach_metric_for_state(
            price,
            pd.Series({"prob_reach_round_32": 1.0}),
            fixture,
        )

        self.assertEqual(state["status"], "Advanced to Round of 16")
        self.assertEqual(state["outcome"], "Advanced")
        self.assertEqual(reach_label, "Reach Round of 16")
        self.assertEqual(float(reach_value), 1.0)

    def test_fixture_timeline_puts_outcome_and_result_first(self):
        fixtures = pd.DataFrame(
            [
                {
                    "stage": "LAST_32",
                    "utc_date": pd.Timestamp("2026-06-28T19:00:00Z"),
                    "status": "FINISHED",
                    "home_team": "South Africa",
                    "away_team": "Canada",
                    "home_score": 0,
                    "away_score": 1,
                    "decision_method": "regular_time",
                    "advancing_team": "Canada",
                }
            ]
        )

        table = page._team_fixture_table(fixtures, "Canada")

        self.assertEqual(table.columns[:4].tolist(), ["Stage", "Outcome", "Fixture", "Opponent"])
        self.assertEqual(table.iloc[0]["Outcome"], "Advanced")
        self.assertIn("South Africa", table.iloc[0]["Fixture"])
        self.assertIn("Canada", table.iloc[0]["Fixture"])


if __name__ == "__main__":
    unittest.main()
