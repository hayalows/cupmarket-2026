from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("FOOTBALL_DATA_TOKEN", "test-token")
os.environ.setdefault("N_SIMULATIONS", "20")

from backend import run_update_pipeline
from backend import update_pipeline


class ConstantGoalModel:
    def __init__(self, value: float):
        self.value = value

    def predict(self, frame):
        return np.array([self.value] * len(frame))


def team_map(*teams: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "live_team_name": list(teams),
            "historical_team_name": list(teams),
        }
    )


def live_elo(*teams: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "team": list(teams),
            "elo_rating": np.linspace(1700.0, 1400.0, len(teams)),
            "rank": range(1, len(teams) + 1),
        }
    )


def live_state(*teams: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "team": list(teams),
            "matches": [3] * len(teams),
            "ema_goals_for": [1.25] * len(teams),
            "ema_goals_against": [1.25] * len(teams),
            "ema_points": [1.5] * len(teams),
            "last_date": [pd.NaT] * len(teams),
        }
    )


class Phase8KnockoutPublicationTests(unittest.TestCase):
    def test_group_and_knockout_predictions_publish_while_tbd_is_skipped(self):
        matches = pd.DataFrame(
            [
                {
                    "match_id": 1,
                    "utc_date": pd.Timestamp("2026-06-20", tz="UTC"),
                    "status": "TIMED",
                    "stage": "GROUP_STAGE",
                    "group": "GROUP_A",
                    "home_team": "Team A",
                    "away_team": "Team B",
                },
                {
                    "match_id": 2,
                    "utc_date": pd.Timestamp("2026-07-01", tz="UTC"),
                    "status": "SCHEDULED",
                    "stage": "LAST_32",
                    "group": None,
                    "home_team": "Team C",
                    "away_team": "Team D",
                },
                {
                    "match_id": 3,
                    "utc_date": pd.Timestamp("2026-07-02", tz="UTC"),
                    "status": "SCHEDULED",
                    "stage": "LAST_32",
                    "group": None,
                    "home_team": "TBD",
                    "away_team": "Team A",
                },
            ]
        )

        predictions, ledger = update_pipeline.generate_live_predictions(
            matches,
            ConstantGoalModel(1.4),
            ConstantGoalModel(1.1),
            team_map("Team A", "Team B", "Team C", "Team D"),
            live_elo("Team A", "Team B", "Team C", "Team D"),
            live_state("Team A", "Team B", "Team C", "Team D"),
            pd.DataFrame(columns=["match_id"]),
            pd.DataFrame(),
        )

        self.assertEqual(set(predictions["match_id"]), {1, 2})
        by_match = predictions.set_index("match_id")
        self.assertEqual(by_match.loc[1, "prediction_type"], "live_pre_match")
        self.assertEqual(
            by_match.loc[2, "prediction_type"],
            "knockout_pre_match",
        )
        for column in [
            "expected_home_goals",
            "expected_away_goals",
            "prob_home_win",
            "prob_draw",
            "prob_away_win",
            "most_likely_score",
            "second_likely_score",
            "third_likely_score",
        ]:
            self.assertIn(column, predictions.columns)
            self.assertFalse(predictions[column].isna().any())
        self.assertEqual(len(ledger), 2)

    def test_finished_knockout_match_updates_processed_ledger(self):
        matches = pd.DataFrame(
            [
                {
                    "match_id": 10,
                    "utc_date": pd.Timestamp("2026-06-20", tz="UTC"),
                    "status": "FINISHED",
                    "stage": "GROUP_STAGE",
                    "group": "GROUP_A",
                    "home_team": "Team A",
                    "away_team": "Team B",
                    "winner": "HOME_TEAM",
                    "duration": "REGULAR",
                    "home_score_full_time": 2,
                    "away_score_full_time": 0,
                },
                {
                    "match_id": 20,
                    "utc_date": pd.Timestamp("2026-07-01", tz="UTC"),
                    "status": "FINISHED",
                    "stage": "LAST_32",
                    "group": None,
                    "home_team": "Team C",
                    "away_team": "Team D",
                    "winner": "AWAY_TEAM",
                    "duration": "REGULAR",
                    "home_score_full_time": 1,
                    "away_score_full_time": 2,
                },
            ]
        )

        _, _, ledger, new_matches, _, finished_group_matches, _ = (
            update_pipeline.update_live_state(
                matches,
                team_map("Team A", "Team B", "Team C", "Team D"),
                live_elo("Team A", "Team B", "Team C", "Team D"),
                live_state("Team A", "Team B", "Team C", "Team D"),
                pd.DataFrame(columns=["match_id"]),
            )
        )

        self.assertEqual(set(new_matches["match_id"]), {10, 20})
        self.assertEqual(set(ledger["stage"]), {"GROUP_STAGE", "LAST_32"})
        self.assertIn(20, set(ledger["match_id"].astype(int)))
        self.assertEqual(len(finished_group_matches), 1)

    def test_knockout_settlement_locks_loser_and_advances_winner(self):
        probabilities = pd.DataFrame(
            [
                {
                    "team": "Team C",
                    "group": "A",
                    "live_elo": 1600.0,
                    "prob_finish_1st_group": 1.0,
                    "prob_finish_2nd_group": 0.0,
                    "prob_finish_3rd_group": 0.0,
                    "prob_best_third_qualifier": 0.0,
                    "prob_reach_round_32": 1.0,
                    "prob_reach_round_16": 0.5,
                    "prob_reach_quarter_final": 0.25,
                    "prob_reach_semi_final": 0.1,
                    "prob_reach_final": 0.05,
                    "prob_champion": 0.02,
                    "champion_rank": 1,
                },
                {
                    "team": "Team D",
                    "group": "A",
                    "live_elo": 1500.0,
                    "prob_finish_1st_group": 0.0,
                    "prob_finish_2nd_group": 1.0,
                    "prob_finish_3rd_group": 0.0,
                    "prob_best_third_qualifier": 0.0,
                    "prob_reach_round_32": 1.0,
                    "prob_reach_round_16": 0.5,
                    "prob_reach_quarter_final": 0.25,
                    "prob_reach_semi_final": 0.1,
                    "prob_reach_final": 0.05,
                    "prob_champion": 0.02,
                    "champion_rank": 2,
                },
            ]
        )
        matches = pd.DataFrame(
            [
                {
                    "match_id": 20,
                    "utc_date": pd.Timestamp("2026-07-01", tz="UTC"),
                    "status": "FINISHED",
                    "stage": "LAST_32",
                    "home_team": "Team C",
                    "away_team": "Team D",
                    "winner": "HOME_TEAM",
                    "home_score_full_time": 2,
                    "away_score_full_time": 1,
                }
            ]
        )

        adjusted, settlements = update_pipeline.apply_knockout_settlements(
            probabilities,
            matches,
        )

        indexed = adjusted.set_index("team")
        self.assertEqual(len(settlements), 1)
        self.assertEqual(indexed.loc["Team C", "prob_reach_round_16"], 1.0)
        self.assertEqual(indexed.loc["Team C", "prob_round_32_exit"], 0.0)
        self.assertEqual(indexed.loc["Team D", "prob_round_32_exit"], 1.0)
        self.assertEqual(indexed.loc["Team D", "prob_reach_round_16"], 0.0)
        self.assertEqual(indexed.loc["Team D", "prob_champion"], 0.0)

    def test_official_upcoming_prediction_gaps_force_real_missing_fixtures_only(self):
        matches = pd.DataFrame(
            [
                {
                    "match_id": 1,
                    "utc_date": pd.Timestamp("2026-06-20", tz="UTC"),
                    "status": "TIMED",
                    "stage": "GROUP_STAGE",
                    "home_team": "Team A",
                    "away_team": "Team B",
                },
                {
                    "match_id": 2,
                    "utc_date": pd.Timestamp("2026-07-01", tz="UTC"),
                    "status": "SCHEDULED",
                    "stage": "LAST_32",
                    "home_team": "Team C",
                    "away_team": "Team D",
                },
                {
                    "match_id": 3,
                    "utc_date": pd.Timestamp("2026-07-02", tz="UTC"),
                    "status": "SCHEDULED",
                    "stage": "LAST_32",
                    "home_team": None,
                    "away_team": "Team A",
                },
            ]
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.csv"
            pd.DataFrame({"match_id": [1]}).to_csv(path, index=False)
            missing = run_update_pipeline.official_upcoming_prediction_gaps(
                matches,
                predictions_path=path,
            )

        self.assertEqual(missing["match_id"].astype(int).tolist(), [2])


if __name__ == "__main__":
    unittest.main()
