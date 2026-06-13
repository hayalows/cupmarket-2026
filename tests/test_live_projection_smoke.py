import unittest

import pandas as pd

from features.live_context import team_context
from features.team_projection import project_team


class LiveProjectionSmokeTests(unittest.TestCase):
    def setUp(self):
        teams = ["A1", "A2", "A3", "A4"]
        fixtures = [(0, 1), (2, 3), (0, 2), (1, 3), (0, 3), (1, 2)]
        rows = []
        predictions = []
        for match_id, (home, away) in enumerate(fixtures, start=1):
            status = "TIMED"
            home_score = away_score = None
            if match_id == 1:
                status, home_score, away_score = "FINISHED", 1, 0
            elif match_id in {5, 6}:
                status, home_score, away_score = "IN_PLAY", 3 if match_id == 5 else 0, 0
            rows.append({
                "match_id": match_id,
                "utc_date": pd.Timestamp("2026-06-20", tz="UTC"),
                "status": status,
                "stage": "GROUP_STAGE",
                "group": "GROUP_A",
                "home_team": teams[home],
                "away_team": teams[away],
                "home_score_full_time": home_score,
                "away_score_full_time": away_score,
            })
            predictions.append({
                "match_id": match_id,
                "expected_home_goals": 1.4,
                "expected_away_goals": 1.0,
            })
        self.matches = pd.DataFrame(rows)
        self.predictions = pd.DataFrame(predictions)
        self.strength = {team: 100 - index for index, team in enumerate(teams)}

    def test_live_score_enters_provisional_table(self):
        context = team_context(
            self.matches, self.predictions, "A1", self.strength
        )
        self.assertEqual(context["points"], 6)
        self.assertEqual(context["goal_difference"], 4)
        self.assertEqual(len(context["live_matches"]), 2)

    def test_projection_is_bounded(self):
        result = project_team(
            self.matches,
            self.predictions,
            "A1",
            self.strength,
            simulations=100,
            seed=7,
        )
        self.assertGreaterEqual(result["qualification_probability"], 0)
        self.assertLessEqual(result["qualification_probability"], 1)
        self.assertAlmostEqual(
            sum(result["position_probabilities"].values()), 1.0, places=6
        )


if __name__ == "__main__":
    unittest.main()
