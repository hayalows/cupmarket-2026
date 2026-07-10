import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.publication_manifest import build_publication_manifest


class PublicationManifestTests(unittest.TestCase):
    def test_manifest_captures_publication_and_archive_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            state = root / "backend" / "state"
            history = data / "history"
            history.mkdir(parents=True)
            state.mkdir(parents=True)
            pd.DataFrame(
                [{"team": "Ghana", "generated_at_utc": "2026-07-10T12:00:00Z", "prob_champion": 0.25}]
            ).to_csv(data / "cupmarket_prices_latest.csv", index=False)
            pd.DataFrame(
                [{"match_id": 1, "stage": "FINAL", "status": "TIMED"}]
            ).to_csv(data / "world_cup_2026_matches_latest.csv", index=False)
            pd.DataFrame(
                [{"snapshot_id": "2026-07-10T12:00:00Z", "team": "Ghana"}]
            ).to_csv(history / "team_snapshots.csv", index=False)
            (data / "phase5_simulation_metadata.json").write_text(json.dumps({"model_version": "test", "number_of_simulations": 20}))
            (state / "last_automation_run.json").write_text(json.dumps({"status": "updated", "completed_at_utc": "2026-07-10T12:01:00Z"}))

            manifest = build_publication_manifest(root)

        self.assertEqual(manifest["publication"]["status"], "updated")
        self.assertEqual(manifest["tournament"]["teams_tracked"], 1)
        self.assertFalse(manifest["archive"]["final_completed"])
