from __future__ import annotations

import unittest

import pandas as pd

from features.tournament_simulator import (
    _advance_probabilities,
    _knockout_fixtures,
    _scenario_rows,
)


class TournamentSimulatorTests(unittest.TestCase):
    def test_knockout_fixtures_skip_tbd_rows(self):
        matches = pd.DataFrame(
            [
                {
                    "match_id": 1,
                    "status": "TIMED",
                    "stage": "LAST_32",
                    "home_team": "Ghana",
                    "away_team": "Norway",
                },
                {
                    "match_id": 2,
                    "status": "TIMED",
                    "stage": "LAST_16",
                    "home_team": "Canada",
                    "away_team": pd.NA,
                },
            ]
        )

        result = _knockout_fixtures(matches)

        self.assertEqual(result["match_id"].astype(int).tolist(), [1])

    def test_advance_probabilities_use_saved_knockout_columns(self):
        match = pd.Series({"match_id": 10})
        predictions = pd.DataFrame(
            [
                {
                    "match_id": 10,
                    "prob_home_advance": 0.7,
                    "prob_away_advance": 0.3,
                }
            ]
        )

        home, away = _advance_probabilities(match, predictions)

        self.assertAlmostEqual(home, 0.7)
        self.assertAlmostEqual(away, 0.3)

    def test_scenario_rows_settle_winner_and_loser(self):
        prices = pd.DataFrame(
            [
                {"team": "Ghana", "cupmarket_price": 22.0},
                {"team": "Norway", "cupmarket_price": 35.0},
            ]
        )
        matches = pd.DataFrame(
            [
                {
                    "match_id": 10,
                    "status": "TIMED",
                    "stage": "LAST_32",
                    "home_team": "Ghana",
                    "away_team": "Norway",
                }
            ]
        )
        predictions = pd.DataFrame(
            [
                {
                    "match_id": 10,
                    "prob_home_advance": 0.4,
                    "prob_away_advance": 0.6,
                }
            ]
        )

        result = _scenario_rows(prices, matches, predictions, {10: "HOME"})
        by_team = {row.Country: row for row in result.itertuples(index=False)}

        self.assertGreaterEqual(float(by_team["Ghana"].Scenario), 30.0)
        self.assertEqual(float(by_team["Norway"].Scenario), 15.0)
        self.assertEqual(by_team["Ghana"].Note, "Advances from Round of 32")
        self.assertEqual(by_team["Norway"].Note, "Out at Round of 32")


if __name__ == "__main__":
    unittest.main()
