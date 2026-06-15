from __future__ import annotations

import unittest

import pandas as pd

from features.reliable_live_match_data import merge_terminal_states


class ReliableLiveMatchDataTests(unittest.TestCase):
    def test_finished_snapshot_overrides_regressed_live_status(self):
        provider = pd.DataFrame(
            [
                {
                    "match_id": 537352,
                    "utc_date": pd.Timestamp("2026-06-14T23:00:00Z"),
                    "status": "AWAITING_CONFIRMATION",
                    "home_team": "Ivory Coast",
                    "away_team": "Ecuador",
                    "home_score_full_time": 1,
                    "away_score_full_time": 0,
                }
            ]
        )
        snapshot = pd.DataFrame(
            [
                {
                    "match_id": 537352,
                    "utc_date": pd.Timestamp("2026-06-14T23:00:00Z"),
                    "status": "FINISHED",
                    "home_team": "Ivory Coast",
                    "away_team": "Ecuador",
                    "winner": "HOME_TEAM",
                    "duration": "REGULAR",
                    "home_score_full_time": 1,
                    "away_score_full_time": 0,
                    "last_updated": pd.Timestamp("2026-06-15T01:09:24Z"),
                }
            ]
        )

        merged, restored = merge_terminal_states(provider, snapshot)

        self.assertEqual(merged.iloc[0]["status"], "FINISHED")
        self.assertEqual(merged.iloc[0]["winner"], "HOME_TEAM")
        self.assertEqual(int(merged.iloc[0]["home_score_full_time"]), 1)
        self.assertEqual(restored, {537352})

    def test_finished_match_never_moves_backwards(self):
        current = pd.DataFrame(
            [
                {
                    "match_id": 1,
                    "status": "FINISHED",
                    "home_score_full_time": 2,
                    "away_score_full_time": 1,
                }
            ]
        )
        trusted = pd.DataFrame(
            [
                {
                    "match_id": 1,
                    "status": "FINISHED",
                    "home_score_full_time": 2,
                    "away_score_full_time": 1,
                }
            ]
        )

        merged, restored = merge_terminal_states(current, trusted)

        self.assertEqual(merged.iloc[0]["status"], "FINISHED")
        self.assertEqual(restored, set())


if __name__ == "__main__":
    unittest.main()
