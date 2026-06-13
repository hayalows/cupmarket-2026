from __future__ import annotations

import unittest

import pandas as pd

from features.live_match_data import group_freshness, parse_api_matches


class LiveMatchDataTests(unittest.TestCase):
    def test_parse_api_matches(self):
        payload = {
            "matches": [
                {
                    "id": 11,
                    "utcDate": "2026-06-20T18:00:00Z",
                    "status": "FINISHED",
                    "stage": "GROUP_STAGE",
                    "group": "GROUP_A",
                    "matchday": 2,
                    "homeTeam": {"name": "Ghana"},
                    "awayTeam": {"name": "Panama"},
                    "score": {
                        "winner": "HOME_TEAM",
                        "duration": "REGULAR",
                        "fullTime": {"home": 2, "away": 1},
                    },
                    "lastUpdated": "2026-06-20T20:00:00Z",
                }
            ]
        }
        frame = parse_api_matches(payload)
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["home_team"], "Ghana")
        self.assertEqual(frame.iloc[0]["away_team"], "Panama")
        self.assertEqual(frame.iloc[0]["home_score_full_time"], 2)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(frame["utc_date"]))

    def test_group_freshness_detects_pending_result(self):
        matches = pd.DataFrame(
            [
                {"stage": "GROUP_STAGE", "status": "FINISHED"},
                {"stage": "GROUP_STAGE", "status": "FINISHED"},
                {"stage": "GROUP_STAGE", "status": "TIMED"},
            ]
        )
        freshness = group_freshness(
            matches,
            {"finished_group_matches": 1},
        )
        self.assertEqual(freshness["live_finished_group_matches"], 2)
        self.assertEqual(freshness["model_finished_group_matches"], 1)
        self.assertEqual(freshness["pending_model_updates"], 1)


if __name__ == "__main__":
    unittest.main()
