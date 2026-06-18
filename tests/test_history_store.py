from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

import pandas as pd

from backend.history_store import archive_latest_outputs


class TournamentHistoryStoreTests(unittest.TestCase):
    def test_archives_once_and_prevents_duplicate_rows(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_repository_fixture(root)

            first = archive_latest_outputs(root)
            second = archive_latest_outputs(root)

            self.assertEqual(first["status"], "archived")
            self.assertTrue(first["baseline_created"])
            self.assertEqual(first["rows_added"]["team_snapshots"], 2)
            self.assertEqual(first["rows_added"]["elo_events"], 2)
            self.assertEqual(first["rows_added"]["match_impacts"], 2)
            self.assertEqual(first["rows_added"]["bracket_snapshots"], 2)

            self.assertEqual(second["status"], "archived")
            self.assertFalse(second["baseline_created"])
            self.assertEqual(second["rows_added"]["team_snapshots"], 0)
            self.assertEqual(second["rows_added"]["elo_events"], 0)
            self.assertEqual(second["rows_added"]["match_impacts"], 0)
            self.assertEqual(second["rows_added"]["bracket_snapshots"], 0)

            history = root / "data" / "history"
            self.assertEqual(len(pd.read_csv(history / "team_snapshots.csv")), 2)
            self.assertEqual(len(pd.read_csv(history / "elo_events.csv")), 2)
            self.assertEqual(len(pd.read_csv(history / "match_impacts.csv")), 2)
            self.assertEqual(len(pd.read_csv(history / "bracket_snapshots.csv")), 2)
            self.assertEqual(len(pd.read_csv(history / "tournament_baseline.csv")), 2)

    def test_skips_non_updated_runs(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            summary_path = root / "backend" / "state" / "last_automation_run.json"
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text(
                json.dumps({"status": "no_new_finished_match"}),
                encoding="utf-8",
            )

            result = archive_latest_outputs(root)

            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["reason"], "no_new_finished_match")
            self.assertFalse((root / "data" / "history").exists())

    def test_elo_event_reconstructs_before_and_after_values(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_repository_fixture(root)
            archive_latest_outputs(root)

            events = pd.read_csv(root / "data" / "history" / "elo_events.csv")
            ghana = events.loc[events["team"] == "Ghana"].iloc[0]
            england = events.loc[events["team"] == "England"].iloc[0]

            self.assertAlmostEqual(float(ghana["elo_before"]), 1600.0)
            self.assertAlmostEqual(float(ghana["elo_after"]), 1612.5)
            self.assertAlmostEqual(float(ghana["elo_change"]), 12.5)
            self.assertAlmostEqual(float(england["elo_before"]), 2100.0)
            self.assertAlmostEqual(float(england["elo_after"]), 2087.5)
            self.assertAlmostEqual(float(england["elo_change"]), -12.5)

    @staticmethod
    def _write_repository_fixture(root: Path) -> None:
        data = root / "data"
        state = root / "backend" / "state"
        market_history = data / "market_history"
        data.mkdir(parents=True)
        state.mkdir(parents=True)
        market_history.mkdir(parents=True)

        generated = "2026-06-18T11:30:00+00:00"
        rows = [
            {
                "team": "Ghana",
                "group": "L",
                "live_elo": 1612.5,
                "prob_finish_1st_group": 0.30,
                "prob_finish_2nd_group": 0.40,
                "prob_finish_3rd_group": 0.20,
                "prob_best_third_qualifier": 0.10,
                "prob_reach_round_32": 0.70,
                "prob_reach_round_16": 0.20,
                "prob_reach_quarter_final": 0.05,
                "prob_reach_semi_final": 0.01,
                "prob_reach_final": 0.002,
                "prob_champion": 0.001,
                "cupmarket_price": 15.0,
                "market_rank": 20,
                "previous_price": 13.0,
                "price_change": 2.0,
                "price_change_percent": 15.3846,
                "generated_at_utc": generated,
                "model_version": "test-v1",
                "bracket_mode": "test-bracket",
            },
            {
                "team": "England",
                "group": "L",
                "live_elo": 2087.5,
                "prob_finish_1st_group": 0.60,
                "prob_finish_2nd_group": 0.30,
                "prob_finish_3rd_group": 0.08,
                "prob_best_third_qualifier": 0.02,
                "prob_reach_round_32": 0.98,
                "prob_reach_round_16": 0.70,
                "prob_reach_quarter_final": 0.40,
                "prob_reach_semi_final": 0.20,
                "prob_reach_final": 0.10,
                "prob_champion": 0.05,
                "cupmarket_price": 45.0,
                "market_rank": 4,
                "previous_price": 47.0,
                "price_change": -2.0,
                "price_change_percent": -4.2553,
                "generated_at_utc": generated,
                "model_version": "test-v1",
                "bracket_mode": "test-bracket",
            },
        ]
        prices = pd.DataFrame(rows)
        probabilities = prices.drop(
            columns=[
                "cupmarket_price",
                "market_rank",
                "previous_price",
                "price_change",
                "price_change_percent",
            ]
        )
        tables = pd.DataFrame(
            [
                {"team": "Ghana", "position": 2, "points": 4, "goal_difference": 1},
                {"team": "England", "position": 1, "points": 4, "goal_difference": 2},
            ]
        )

        prices.to_csv(data / "cupmarket_prices_latest.csv", index=False)
        probabilities.to_csv(data / "tournament_probabilities_latest.csv", index=False)
        tables.to_csv(data / "current_group_tables.csv", index=False)

        opening = prices.copy()
        opening["cupmarket_price"] = [7.10, 50.0]
        opening["market_rank"] = [35, 3]
        opening["live_elo"] = [1600.0, 2100.0]
        opening.to_csv(
            market_history / "cupmarket_prices_20260611T000000Z.csv",
            index=False,
        )

        summary = {
            "status": "updated",
            "completed_at_utc": generated,
            "new_finished_matches": 1,
            "new_matches": [
                {
                    "match_id": 9001,
                    "home_team": "Ghana",
                    "away_team": "England",
                    "home_score": 1,
                    "away_score": 1,
                    "home_elo_change": 12.5,
                    "away_elo_change": -12.5,
                }
            ],
        }
        (state / "last_automation_run.json").write_text(
            json.dumps(summary),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
