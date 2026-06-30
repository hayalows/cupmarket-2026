from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

import pandas as pd

from backend.market_impact_store import archive_market_movements


class MarketImpactStoreTests(unittest.TestCase):
    def test_uses_previous_archived_snapshot_not_stale_previous_price(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_fixture(root, match_count=1)

            result = archive_market_movements(root)
            latest = pd.read_csv(root / "data" / "market_movements_latest.csv")
            ghana = latest.loc[latest["team"] == "Ghana"].iloc[0]

            self.assertEqual(result["status"], "archived")
            self.assertEqual(result["attribution_scope"], "single_match")
            self.assertAlmostEqual(float(ghana["price_before"]), 7.10)
            self.assertAlmostEqual(float(ghana["price_after"]), 13.69)
            self.assertAlmostEqual(float(ghana["price_change"]), 6.59)
            self.assertAlmostEqual(
                float(ghana["price_change_percent"]),
                100.0 * 6.59 / 7.10,
                places=6,
            )
            self.assertEqual(
                ghana["before_source"], "previous_archived_snapshot"
            )
            self.assertTrue(bool(ghana["individual_match_attribution_available"]))

    def test_falls_back_to_previous_price_without_earlier_snapshot(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_fixture(root, match_count=1, include_prior=False)

            archive_market_movements(root)
            latest = pd.read_csv(root / "data" / "market_movements_latest.csv")
            ghana = latest.loc[latest["team"] == "Ghana"].iloc[0]

            self.assertAlmostEqual(float(ghana["price_before"]), 12.50)
            self.assertEqual(
                ghana["before_source"], "prices_previous_price_fallback"
            )

    def test_multiple_matches_are_labelled_as_combined_batch(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_fixture(root, match_count=2)

            result = archive_market_movements(root)
            latest = pd.read_csv(root / "data" / "market_movements_latest.csv")

            self.assertEqual(result["attribution_scope"], "match_batch")
            self.assertEqual(set(latest["attribution_scope"]), {"match_batch"})
            self.assertFalse(
                latest["individual_match_attribution_available"].astype(bool).any()
            )
            self.assertEqual(
                set(latest["trigger_match_ids"].astype(str)), {"9001|9002"}
            )

    def test_archive_is_idempotent_for_same_event(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_fixture(root, match_count=1)

            first = archive_market_movements(root)
            second = archive_market_movements(root)
            archive = pd.read_csv(
                root / "data" / "history" / "market_movements.csv"
            )

            self.assertEqual(first["rows_added"], 2)
            self.assertEqual(second["rows_added"], 0)
            self.assertEqual(len(archive), 2)

    def test_no_new_match_publication_is_archived_as_refresh(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_fixture(root, match_count=0)

            result = archive_market_movements(root)
            latest = pd.read_csv(root / "data" / "market_movements_latest.csv")
            ghana = latest.loc[latest["team"] == "Ghana"].iloc[0]

            self.assertEqual(result["status"], "archived")
            self.assertEqual(result["attribution_scope"], "publication_refresh")
            self.assertEqual(ghana["movement_type"], "publication_refresh")
            self.assertEqual(ghana["relationship_to_event"], "publication_refresh")
            self.assertFalse(bool(ghana["individual_match_attribution_available"]))
            self.assertEqual(ghana["trigger_matches"], "Official model refresh")
            self.assertAlmostEqual(float(ghana["price_before"]), 7.10)
            self.assertAlmostEqual(float(ghana["price_after"]), 13.69)

    def test_knockout_refresh_uses_previous_official_snapshot(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            history = data / "history"
            state = root / "backend" / "state"
            history.mkdir(parents=True)
            state.mkdir(parents=True)

            pd.DataFrame(
                [
                    {
                        "team": "Paraguay",
                        "group": "D",
                        "live_elo": 1910.0,
                        "cupmarket_price": 43.66,
                        "previous_price": 33.27,
                        "prob_reach_round_32": 1.0,
                        "prob_champion": 0.00825,
                        "model_version": "phase6_knockout_progression_v1",
                        "bracket_mode": "official_api_locked_knockout_progression",
                    }
                ]
            ).to_csv(data / "cupmarket_prices_latest.csv", index=False)

            pd.DataFrame(
                [
                    {
                        "snapshot_id": "2026-06-29T19:20:49+00:00",
                        "team": "Paraguay",
                        "group": "D",
                        "live_elo": 1870.0,
                        "cupmarket_price": 23.98,
                        "prob_reach_round_32": 1.0,
                        "prob_champion": 0.00235,
                        "model_version": "phase6_knockout_progression_v1",
                        "bracket_mode": "official_api_locked_knockout_progression",
                    },
                    {
                        "snapshot_id": "2026-06-29T23:45:39+00:00",
                        "team": "Paraguay",
                        "group": "D",
                        "live_elo": 1910.0,
                        "cupmarket_price": 33.27,
                        "prob_reach_round_32": 1.0,
                        "prob_champion": 0.00235,
                        "model_version": "phase9b_adaptive_prediction_v1",
                        "bracket_mode": "provisional_constraint_assignment",
                    },
                    {
                        "snapshot_id": "2026-06-29T23:45:50+00:00",
                        "team": "Paraguay",
                        "group": "D",
                        "live_elo": 1910.0,
                        "cupmarket_price": 43.66,
                        "prob_reach_round_32": 1.0,
                        "prob_champion": 0.00825,
                        "model_version": "phase6_knockout_progression_v1",
                        "bracket_mode": "official_api_locked_knockout_progression",
                    },
                ]
            ).to_csv(history / "team_snapshots.csv", index=False)

            summary = {
                "status": "updated",
                "pipeline_phase": "knockout_stage",
                "completed_at_utc": "2026-06-29T23:45:50+00:00",
                "new_finished_matches": 0,
                "new_matches": [],
            }
            (state / "last_automation_run.json").write_text(
                json.dumps(summary), encoding="utf-8"
            )

            archive_market_movements(root)
            latest = pd.read_csv(root / "data" / "market_movements_latest.csv")
            paraguay = latest.loc[latest["team"] == "Paraguay"].iloc[0]

            self.assertEqual(paraguay["movement_type"], "publication_refresh")
            self.assertAlmostEqual(float(paraguay["price_before"]), 23.98)
            self.assertAlmostEqual(float(paraguay["price_after"]), 43.66)
            self.assertAlmostEqual(float(paraguay["price_change"]), 19.68)

    @staticmethod
    def _write_fixture(
        root: Path,
        match_count: int,
        include_prior: bool = True,
    ) -> None:
        data = root / "data"
        history = data / "history"
        state = root / "backend" / "state"
        history.mkdir(parents=True)
        state.mkdir(parents=True)

        current_snapshot = "2026-06-18T12:00:00+00:00"
        prices = pd.DataFrame(
            [
                {
                    "team": "Ghana",
                    "group": "L",
                    "live_elo": 1665.0,
                    "cupmarket_price": 13.69,
                    "previous_price": 12.50,
                    "prob_reach_round_32": 0.6419,
                    "prob_champion": 0.0001,
                    "model_version": "test-v1",
                    "bracket_mode": "test-bracket",
                },
                {
                    "team": "Panama",
                    "group": "L",
                    "live_elo": 1710.0,
                    "cupmarket_price": 8.83,
                    "previous_price": 9.00,
                    "prob_reach_round_32": 0.20,
                    "prob_champion": 0.0,
                    "model_version": "test-v1",
                    "bracket_mode": "test-bracket",
                },
            ]
        )
        prices.to_csv(data / "cupmarket_prices_latest.csv", index=False)

        snapshot_rows = [
            {
                "snapshot_id": current_snapshot,
                "team": "Ghana",
                "group": "L",
                "live_elo": 1665.0,
                "cupmarket_price": 13.69,
                "prob_reach_round_32": 0.6419,
                "prob_champion": 0.0001,
            },
            {
                "snapshot_id": current_snapshot,
                "team": "Panama",
                "group": "L",
                "live_elo": 1710.0,
                "cupmarket_price": 8.83,
                "prob_reach_round_32": 0.20,
                "prob_champion": 0.0,
            },
        ]
        if include_prior:
            snapshot_rows.extend(
                [
                    {
                        "snapshot_id": "2026-06-17T12:00:00+00:00",
                        "team": "Ghana",
                        "group": "L",
                        "live_elo": 1610.0,
                        "cupmarket_price": 7.10,
                        "prob_reach_round_32": 0.22,
                        "prob_champion": 0.0,
                    },
                    {
                        "snapshot_id": "2026-06-17T12:00:00+00:00",
                        "team": "Panama",
                        "group": "L",
                        "live_elo": 1765.0,
                        "cupmarket_price": 9.40,
                        "prob_reach_round_32": 0.31,
                        "prob_champion": 0.0,
                    },
                ]
            )
        pd.DataFrame(snapshot_rows).to_csv(
            history / "team_snapshots.csv", index=False
        )

        matches = []
        if match_count:
            matches.append(
                {
                    "match_id": 9001,
                    "home_team": "Ghana",
                    "away_team": "Panama",
                    "home_score": 1,
                    "away_score": 0,
                }
            )
        if match_count == 2:
            matches.append(
                {
                    "match_id": 9002,
                    "home_team": "England",
                    "away_team": "Croatia",
                    "home_score": 2,
                    "away_score": 1,
                }
            )
        summary = {
            "status": "updated",
            "completed_at_utc": current_snapshot,
            "new_finished_matches": match_count,
            "new_matches": matches,
        }
        (state / "last_automation_run.json").write_text(
            json.dumps(summary), encoding="utf-8"
        )


if __name__ == "__main__":
    unittest.main()
