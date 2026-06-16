from __future__ import annotations

import unittest

import pandas as pd

from features.qualification_result_state import qualification_context_token, stored_result_is_current


class QualificationResultStateTests(unittest.TestCase):
    def setUp(self):
        self.matches = pd.DataFrame([
            {
                "match_id": 1,
                "group": "GROUP_A",
                "status": "FINISHED",
                "home_team": "Alpha",
                "away_team": "Bravo",
                "home_score_full_time": 2,
                "away_score_full_time": 0,
                "last_updated": "2026-06-15T10:00:00Z",
            },
            {
                "match_id": 2,
                "group": "GROUP_A",
                "status": "SCHEDULED",
                "home_team": "Charlie",
                "away_team": "Delta",
                "home_score_full_time": None,
                "away_score_full_time": None,
                "last_updated": "2026-06-15T10:00:00Z",
            },
        ])
        self.predictions = pd.DataFrame([
            {"generated_at_utc": "2026-06-15T09:00:00Z"}
        ])
        self.prices = pd.DataFrame([
            {"generated_at_utc": "2026-06-15T09:05:00Z"}
        ])

    def token(self, matches=None, predictions=None, prices=None, team="Charlie"):
        return qualification_context_token(
            self.matches if matches is None else matches,
            self.predictions if predictions is None else predictions,
            self.prices if prices is None else prices,
            2,
            team,
        )

    def test_timestamp_only_does_not_invalidate(self):
        changed = self.matches.copy()
        changed["last_updated"] = "2026-06-15T10:05:00Z"
        self.assertEqual(self.token(), self.token(matches=changed))

    def test_score_change_invalidates(self):
        changed = self.matches.copy()
        changed.loc[changed["match_id"] == 1, "home_score_full_time"] = 3
        self.assertNotEqual(self.token(), self.token(matches=changed))

    def test_model_generation_invalidates(self):
        predictions = pd.DataFrame([
            {"generated_at_utc": "2026-06-15T10:00:00Z"}
        ])
        self.assertNotEqual(self.token(), self.token(predictions=predictions))

    def test_stored_result_must_match(self):
        token = self.token()
        stored = {"team": "Charlie", "context_token": token, "result": {}}
        self.assertTrue(stored_result_is_current(stored, "Charlie", token))
        self.assertFalse(stored_result_is_current(stored, "Delta", token))
        self.assertFalse(stored_result_is_current(stored, "Charlie", "other"))


if __name__ == "__main__":
    unittest.main()
