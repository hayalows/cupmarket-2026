import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backend.publication_manifest import finalized_run_summary, is_archive_finalized
from backend.tournament_retrospective import settle_prediction_ledger
from backend import run_post_group_pipeline, run_update_pipeline


class TournamentRetrospectiveTests(unittest.TestCase):
    def test_settlement_keeps_latest_eligible_pre_match_forecast(self):
        matches = pd.DataFrame(
            [
                {
                    "match_id": 10,
                    "utc_date": "2026-07-19T19:00:00Z",
                    "status": "FINISHED",
                    "stage": "FINAL",
                    "home_team": "Spain",
                    "away_team": "Argentina",
                    "winner": "HOME_TEAM",
                    "duration": "EXTRA_TIME",
                    "home_score_full_time": 1,
                    "away_score_full_time": 0,
                },
                {
                    "match_id": 11,
                    "utc_date": "2026-07-18T19:00:00Z",
                    "status": "FINISHED",
                    "stage": "THIRD_PLACE",
                    "home_team": "France",
                    "away_team": "England",
                    "winner": "AWAY_TEAM",
                    "duration": "REGULAR",
                    "home_score_full_time": 4,
                    "away_score_full_time": 6,
                },
            ]
        )
        progress = pd.DataFrame(
            [
                {"api_match_id": 10, "advancing_team": "Spain"},
                {"api_match_id": 11, "advancing_team": "England"},
            ]
        )
        ledger = pd.DataFrame(
            [
                {
                    "match_id": 10,
                    "generated_at_utc": "2026-07-18T10:00:00Z",
                    "utc_date": "2026-07-19T19:00:00Z",
                    "created_before_kickoff": True,
                    "prediction_type": "knockout_pre_match",
                    "prediction_source": "test",
                    "model_version": "test",
                    "home_team": "Spain",
                    "away_team": "Argentina",
                    "prob_home_win": 0.40,
                    "prob_draw": 0.30,
                    "prob_away_win": 0.30,
                    "baseline_prob_home_win": 0.40,
                    "baseline_prob_draw": 0.30,
                    "baseline_prob_away_win": 0.30,
                    "predicted_result": "HOME_WIN",
                    "adaptive_prediction_enabled": True,
                },
                {
                    "match_id": 10,
                    "generated_at_utc": "2026-07-19T06:00:00Z",
                    "utc_date": "2026-07-19T19:00:00Z",
                    "created_before_kickoff": True,
                    "prediction_type": "knockout_pre_match",
                    "prediction_source": "test",
                    "model_version": "test",
                    "home_team": "Spain",
                    "away_team": "Argentina",
                    "prob_home_win": 0.25,
                    "prob_draw": 0.25,
                    "prob_away_win": 0.50,
                    "baseline_prob_home_win": 0.25,
                    "baseline_prob_draw": 0.25,
                    "baseline_prob_away_win": 0.50,
                    "predicted_result": "AWAY_WIN",
                    "adaptive_prediction_enabled": True,
                },
                {
                    "match_id": 11,
                    "generated_at_utc": "2026-07-18T20:00:00Z",
                    "utc_date": "2026-07-18T19:00:00Z",
                    "created_before_kickoff": False,
                    "prediction_type": "live_pre_match",
                    "prediction_source": "test",
                    "model_version": "test",
                    "home_team": "France",
                    "away_team": "England",
                    "prob_home_win": 0.50,
                    "prob_draw": 0.20,
                    "prob_away_win": 0.30,
                    "baseline_prob_home_win": 0.50,
                    "baseline_prob_draw": 0.20,
                    "baseline_prob_away_win": 0.30,
                    "predicted_result": "HOME_WIN",
                    "adaptive_prediction_enabled": True,
                },
            ]
        )

        settled = settle_prediction_ledger(matches, progress, ledger)

        self.assertEqual(len(settled), 2)
        final = settled.loc[settled["match_id"].eq("10")].iloc[0]
        self.assertEqual(final["model_result"], "AWAY_WIN")
        self.assertEqual(final["actual_result"], "HOME_WIN")
        self.assertEqual(final["actual_advancing_team"], "Spain")
        self.assertFalse(bool(final["model_correct"]))
        self.assertTrue(bool(final["prediction_available"]))
        self.assertFalse(bool(settled.loc[settled["match_id"].eq("11"), "prediction_available"].iloc[0]))

    def test_final_archive_lock_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "data" / "archive_manifest.json"
            archive_path.parent.mkdir(parents=True)
            archive_path.write_text(
                json.dumps({"status": "finalized", "archive_id": "cupmarket-2026-final"}),
                encoding="utf-8",
            )

            self.assertTrue(is_archive_finalized(root))
            summary = finalized_run_summary(root)
            self.assertEqual(summary["status"], "final_archive_locked")
            self.assertEqual(summary["archive_id"], "cupmarket-2026-final")

    def test_live_entrypoints_skip_network_when_archive_is_final(self):
        with patch.object(
            run_update_pipeline.publication_manifest,
            "is_archive_finalized",
            return_value=True,
        ), patch.object(run_update_pipeline.update_pipeline, "atomic_to_json"):
            self.assertFalse(run_update_pipeline.run_guarded_pipeline())

        with patch.object(
            run_post_group_pipeline.publication_manifest,
            "is_archive_finalized",
            return_value=True,
        ), patch.object(run_post_group_pipeline.update_pipeline, "atomic_to_json"):
            result = run_post_group_pipeline.run()
        self.assertEqual(result["status"], "final_archive_locked")


if __name__ == "__main__":
    unittest.main()
