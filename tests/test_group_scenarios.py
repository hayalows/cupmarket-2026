from __future__ import annotations

import unittest

import pandas as pd

from backend.group_scenarios import (
    current_team_summary,
    run_qualification_scenarios,
)


class GroupScenarioTests(unittest.TestCase):
    @staticmethod
    def build_tournament() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
        matches = []
        predictions = []
        match_id = 1

        for group in "ABCDEFGHIJKL":
            teams = [f"{group}{number}" for number in range(1, 5)]
            fixtures = [
                (0, 1),
                (2, 3),
                (0, 2),
                (1, 3),
                (0, 3),
                (1, 2),
            ]

            for fixture_number, (home_index, away_index) in enumerate(fixtures):
                finished = fixture_number < 2
                matches.append(
                    {
                        "match_id": match_id,
                        "utc_date": pd.Timestamp("2026-06-10", tz="UTC")
                        + pd.Timedelta(days=fixture_number),
                        "status": "FINISHED" if finished else "TIMED",
                        "stage": "GROUP_STAGE",
                        "group": f"GROUP_{group}",
                        "home_team": teams[home_index],
                        "away_team": teams[away_index],
                        "home_score_full_time": (
                            2 if fixture_number == 0 else 1 if fixture_number == 1 else None
                        ),
                        "away_score_full_time": (
                            0 if fixture_number == 0 else 1 if fixture_number == 1 else None
                        ),
                    }
                )
                predictions.append(
                    {
                        "match_id": match_id,
                        "generated_at_utc": pd.Timestamp("2026-06-11", tz="UTC"),
                        "expected_home_goals": (
                            2.0 if teams[home_index] == f"{group}1" else 1.3
                        ),
                        "expected_away_goals": (
                            0.7 if teams[home_index] == f"{group}1" else 1.1
                        ),
                    }
                )
                match_id += 1

        strength = {
            f"{group}{number}": 100.0 - number
            for group in "ABCDEFGHIJKL"
            for number in range(1, 5)
        }
        return pd.DataFrame(matches), pd.DataFrame(predictions), strength

    def test_current_summary_finds_next_match(self):
        matches, _, strength = self.build_tournament()
        summary = current_team_summary(matches, "A1", strength)

        self.assertEqual(summary["group"], "A")
        self.assertEqual(summary["current_points"], 3)
        self.assertEqual(summary["played"], 1)
        self.assertEqual(summary["matches_remaining"], 2)
        self.assertEqual(summary["next_opponent"], "A3")

    def test_win_draw_loss_scenarios_are_valid(self):
        matches, predictions, strength = self.build_tournament()
        result = run_qualification_scenarios(
            matches,
            predictions,
            "A1",
            strength,
            n_simulations=300,
            random_seed=7,
        )

        self.assertTrue(result["available"])
        self.assertEqual(set(result["scenarios"]), {"WIN", "DRAW", "LOSS"})
        self.assertEqual(result["scenarios"]["WIN"]["points_after_next_match"], 6)
        self.assertEqual(result["scenarios"]["DRAW"]["points_after_next_match"], 4)
        self.assertEqual(result["scenarios"]["LOSS"]["points_after_next_match"], 3)

        for scenario in result["scenarios"].values():
            self.assertGreaterEqual(scenario["qualification_probability"], 0.0)
            self.assertLessEqual(scenario["qualification_probability"], 1.0)
            position_total = sum(
                scenario[key]
                for key in [
                    "finish_first_probability",
                    "finish_second_probability",
                    "finish_third_probability",
                    "finish_fourth_probability",
                ]
            )
            self.assertAlmostEqual(position_total, 1.0, places=6)

    def test_no_future_match_returns_unavailable(self):
        matches, predictions, strength = self.build_tournament()
        team_mask = (
            (matches["home_team"] == "A1")
            | (matches["away_team"] == "A1")
        )
        matches.loc[team_mask, "status"] = "FINISHED"
        matches.loc[team_mask & matches["home_score_full_time"].isna(), "home_score_full_time"] = 1
        matches.loc[team_mask & matches["away_score_full_time"].isna(), "away_score_full_time"] = 0

        result = run_qualification_scenarios(
            matches,
            predictions,
            "A1",
            strength,
            n_simulations=100,
        )
        self.assertFalse(result["available"])
        self.assertIn("No unplayed", result["reason"])


if __name__ == "__main__":
    unittest.main()
