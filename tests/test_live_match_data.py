from __future__ import annotations

import unittest

import pandas as pd

from features.live_group_table import build_live_group_table
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

    def test_live_group_table_uses_current_scores(self):
        fixtures = [
            (1, "Ghana", "Panama", "FINISHED", 2, 0),
            (2, "Japan", "Sweden", "FINISHED", 1, 1),
            (3, "Ghana", "Japan", "TIMED", None, None),
            (4, "Panama", "Sweden", "TIMED", None, None),
            (5, "Ghana", "Sweden", "TIMED", None, None),
            (6, "Panama", "Japan", "TIMED", None, None),
        ]
        matches = pd.DataFrame(
            [
                {
                    "match_id": match_id,
                    "utc_date": pd.Timestamp("2026-06-20", tz="UTC")
                    + pd.Timedelta(days=match_id),
                    "status": status,
                    "stage": "GROUP_STAGE",
                    "group": "GROUP_A",
                    "home_team": home,
                    "away_team": away,
                    "home_score_full_time": home_score,
                    "away_score_full_time": away_score,
                }
                for match_id, home, away, status, home_score, away_score in fixtures
            ]
        )
        table = build_live_group_table(
            matches,
            "A",
            {"Ghana": 100, "Japan": 90, "Sweden": 80, "Panama": 70},
        )
        self.assertEqual(table.iloc[0]["team"], "Ghana")
        self.assertEqual(int(table.iloc[0]["points"]), 3)
        self.assertEqual(int(table.iloc[0]["goal_difference"]), 2)


if __name__ == "__main__":
    unittest.main()
