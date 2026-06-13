from __future__ import annotations

import json
import unittest

import pandas as pd

from backend import update_pipeline as pipeline


class ConstantGoalModel:
    def __init__(self, value: float) -> None:
        self.value = value

    def predict(self, frame: pd.DataFrame) -> list[float]:
        return [self.value for _ in range(len(frame))]


class OverlappingMatchSafetyTests(unittest.TestCase):
    def test_only_active_group_matches_block_official_publication(self) -> None:
        matches = pd.DataFrame(
            [
                {
                    "match_id": 1,
                    "utc_date": pd.Timestamp("2026-06-27T17:00:00Z"),
                    "last_updated": pd.Timestamp("2026-06-27T18:45:00Z"),
                    "stage": "GROUP_STAGE",
                    "group": "GROUP_L",
                    "status": "FINISHED",
                    "home_team": "Croatia",
                    "away_team": "Ghana",
                },
                {
                    "match_id": 2,
                    "utc_date": pd.Timestamp("2026-06-27T17:00:00Z"),
                    "last_updated": pd.Timestamp("2026-06-27T18:45:00Z"),
                    "stage": "GROUP_STAGE",
                    "group": "GROUP_L",
                    "status": "IN_PLAY",
                    "home_team": "Panama",
                    "away_team": "England",
                },
                {
                    "match_id": 3,
                    "utc_date": pd.Timestamp("2026-07-04T19:00:00Z"),
                    "last_updated": pd.Timestamp("2026-07-04T20:10:00Z"),
                    "stage": "LAST_16",
                    "group": None,
                    "status": "IN_PLAY",
                    "home_team": "Team A",
                    "away_team": "Team B",
                },
                {
                    "match_id": 4,
                    "utc_date": pd.Timestamp("2026-06-28T19:00:00Z"),
                    "last_updated": pd.Timestamp("2026-06-13T10:00:00Z"),
                    "stage": "GROUP_STAGE",
                    "group": "GROUP_K",
                    "status": "TIMED",
                    "home_team": "Portugal",
                    "away_team": "Colombia",
                },
            ]
        )

        active = pipeline.active_group_matches(matches)

        self.assertEqual(active["match_id"].tolist(), [2])
        self.assertEqual(active.iloc[0]["status"], "IN_PLAY")

    def test_active_match_summary_is_json_safe(self) -> None:
        matches = pd.DataFrame(
            [
                {
                    "match_id": 9,
                    "utc_date": pd.Timestamp("2026-06-27T17:00:00Z"),
                    "last_updated": pd.Timestamp("2026-06-27T18:45:00Z"),
                    "stage": "GROUP_STAGE",
                    "group": "GROUP_L",
                    "status": "PAUSED",
                    "home_team": "Panama",
                    "away_team": "England",
                }
            ]
        )

        summary = pipeline.active_group_match_summary(
            pipeline.active_group_matches(matches)
        )

        self.assertEqual(summary[0]["match_id"], 9)
        self.assertEqual(summary[0]["status"], "PAUSED")
        json.dumps(summary)

    def test_predictions_cover_in_play_and_paused_matches(self) -> None:
        world_cup = pd.DataFrame(
            [
                {
                    "match_id": 1,
                    "utc_date": pd.Timestamp("2026-06-27T17:00:00Z"),
                    "status": "IN_PLAY",
                    "stage": "GROUP_STAGE",
                    "group": "GROUP_L",
                    "home_team": "Croatia",
                    "away_team": "Ghana",
                },
                {
                    "match_id": 2,
                    "utc_date": pd.Timestamp("2026-06-27T17:00:00Z"),
                    "status": "PAUSED",
                    "stage": "GROUP_STAGE",
                    "group": "GROUP_L",
                    "home_team": "Panama",
                    "away_team": "England",
                },
            ]
        )
        teams = ["Croatia", "Ghana", "Panama", "England"]
        team_map = pd.DataFrame(
            {
                "live_team_name": teams,
                "historical_team_name": teams,
            }
        )
        live_elo = pd.DataFrame(
            {
                "team": teams,
                "elo_rating": [1950.0, 1800.0, 1650.0, 2070.0],
            }
        )
        live_team_state = pd.DataFrame(
            {
                "team": teams,
                "matches": [2, 2, 2, 2],
                "ema_goals_for": [1.4, 1.2, 0.9, 1.8],
                "ema_goals_against": [1.0, 1.3, 1.6, 0.8],
                "ema_points": [1.8, 1.2, 0.7, 2.2],
                "last_date": [pd.NaT, pd.NaT, pd.NaT, pd.NaT],
            }
        )

        predictions, _ = pipeline.generate_live_predictions(
            world_cup,
            ConstantGoalModel(1.4),
            ConstantGoalModel(1.1),
            team_map,
            live_elo,
            live_team_state,
            pd.DataFrame(),
            pd.DataFrame(),
        )

        self.assertEqual(set(predictions["match_id"]), {1, 2})
        self.assertTrue(
            predictions["status"].isin(["IN_PLAY", "PAUSED"]).all()
        )


if __name__ == "__main__":
    unittest.main()
