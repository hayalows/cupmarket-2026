from __future__ import annotations

import os
import subprocess
import sys
import unittest

import pandas as pd

from backend import update_pipeline as pipeline


class ConstantGoalModel:
    def __init__(self, value: float) -> None:
        self.value = value

    def predict(self, frame: pd.DataFrame) -> list[float]:
        return [self.value for _ in range(len(frame))]


class UpdatePipelineTests(unittest.TestCase):
    def test_backend_import_does_not_require_token(self) -> None:
        env = os.environ.copy()
        env.pop("FOOTBALL_DATA_TOKEN", None)

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import backend.update_pipeline; print('ok')",
            ],
            cwd=os.getcwd(),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok", result.stdout)

    def test_live_predictions_cover_in_play_group_matches(self) -> None:
        world_cup = pd.DataFrame(
            [
                {
                    "match_id": 1,
                    "utc_date": pd.Timestamp("2026-06-13T18:00:00Z"),
                    "status": "IN_PLAY",
                    "stage": "GROUP_STAGE",
                    "group": "GROUP_A",
                    "home_team": "United States",
                    "away_team": "Paraguay",
                },
                {
                    "match_id": 2,
                    "utc_date": pd.Timestamp("2026-06-14T18:00:00Z"),
                    "status": "PAUSED",
                    "stage": "GROUP_STAGE",
                    "group": "GROUP_A",
                    "home_team": "Mexico",
                    "away_team": "Canada",
                },
            ]
        )
        team_map = pd.DataFrame(
            {
                "live_team_name": [
                    "United States",
                    "Paraguay",
                    "Mexico",
                    "Canada",
                ],
                "historical_team_name": [
                    "United States",
                    "Paraguay",
                    "Mexico",
                    "Canada",
                ],
            }
        )
        live_elo = pd.DataFrame(
            {
                "team": [
                    "United States",
                    "Paraguay",
                    "Mexico",
                    "Canada",
                ],
                "elo_rating": [1600.0, 1500.0, 1550.0, 1525.0],
            }
        )
        live_team_state = pd.DataFrame(
            {
                "team": [
                    "United States",
                    "Paraguay",
                    "Mexico",
                    "Canada",
                ],
                "matches": [0, 0, 0, 0],
                "ema_goals_for": [1.25, 1.25, 1.25, 1.25],
                "ema_goals_against": [1.25, 1.25, 1.25, 1.25],
                "ema_points": [1.25, 1.25, 1.25, 1.25],
                "last_date": [pd.NaT, pd.NaT, pd.NaT, pd.NaT],
            }
        )

        live_predictions, _ = pipeline.generate_live_predictions(
            world_cup,
            ConstantGoalModel(1.4),
            ConstantGoalModel(1.1),
            team_map,
            live_elo,
            live_team_state,
            pd.DataFrame(),
            pd.DataFrame(),
        )

        self.assertEqual(set(live_predictions["match_id"]), {1, 2})
        self.assertTrue(
            live_predictions["status"].isin(["IN_PLAY", "PAUSED"]).all()
        )


if __name__ == "__main__":
    unittest.main()
