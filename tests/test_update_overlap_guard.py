from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

import pandas as pd

os.environ.setdefault("FOOTBALL_DATA_TOKEN", "test-token")

from backend import run_update_pipeline as runner


class OverlappingMatchSafetyTests(unittest.TestCase):
    @staticmethod
    def overlapping_snapshot() -> pd.DataFrame:
        return pd.DataFrame(
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

    def test_only_active_group_matches_block_publication(self) -> None:
        active = runner.active_group_matches(self.overlapping_snapshot())

        self.assertEqual(active["match_id"].tolist(), [2])
        self.assertEqual(active.iloc[0]["status"], "IN_PLAY")

    def test_deferred_summary_is_clear_and_json_safe(self) -> None:
        active = runner.active_group_matches(self.overlapping_snapshot())
        summary = runner.deferred_run_summary(active, {"http_status": 200})

        self.assertEqual(summary["status"], "deferred_active_group_matches")
        self.assertEqual(summary["active_group_match_count"], 1)
        self.assertEqual(summary["active_group_matches"][0]["match_id"], 2)
        self.assertIn("not changed", summary["message"])
        json.dumps(summary)

    def test_active_match_defers_before_model_or_state_changes(self) -> None:
        matches = self.overlapping_snapshot()
        metadata = {"http_status": 200, "matches_returned": len(matches)}

        with (
            patch.object(
                runner.update_pipeline,
                "fetch_world_cup_matches",
                return_value=(matches, metadata),
            ) as fetch_mock,
            patch.object(runner.update_pipeline, "atomic_to_json") as write_mock,
            patch.object(runner.update_pipeline, "main") as main_mock,
        ):
            did_run = runner.run_guarded_pipeline()

        self.assertFalse(did_run)
        fetch_mock.assert_called_once_with()
        main_mock.assert_not_called()
        write_mock.assert_called_once()
        summary = write_mock.call_args.args[0]
        self.assertEqual(summary["status"], "deferred_active_group_matches")

    def test_safe_snapshot_runs_pipeline_and_reuses_one_api_fetch(self) -> None:
        matches = self.overlapping_snapshot().copy()
        matches.loc[matches["match_id"] == 2, "status"] = "FINISHED"
        metadata = {"http_status": 200, "matches_returned": len(matches)}
        snapshot_seen_inside_main = []

        def fake_main() -> None:
            inner_matches, inner_metadata = (
                runner.update_pipeline.fetch_world_cup_matches()
            )
            snapshot_seen_inside_main.append((inner_matches, inner_metadata))

        with (
            patch.object(
                runner.update_pipeline,
                "fetch_world_cup_matches",
                return_value=(matches, metadata),
            ) as fetch_mock,
            patch.object(
                runner.update_pipeline,
                "main",
                side_effect=fake_main,
            ) as main_mock,
            patch.object(runner.update_pipeline, "atomic_to_json") as write_mock,
        ):
            did_run = runner.run_guarded_pipeline()

        self.assertTrue(did_run)
        fetch_mock.assert_called_once_with()
        main_mock.assert_called_once_with()
        write_mock.assert_not_called()
        self.assertEqual(len(snapshot_seen_inside_main), 1)
        self.assertEqual(
            snapshot_seen_inside_main[0][0]["match_id"].tolist(),
            matches["match_id"].tolist(),
        )
        self.assertEqual(snapshot_seen_inside_main[0][1], metadata)


if __name__ == "__main__":
    unittest.main()
