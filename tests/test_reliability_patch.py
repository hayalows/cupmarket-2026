from __future__ import annotations

import unittest

import pandas as pd

from features.adaptive_ratings import adaptive_rating_adjustment
from features.tournament_path_data import team_next_knockout_slot


class ReliabilityPatchTests(unittest.TestCase):
    def test_next_fixture_tracks_current_knockout_stage(self):
        progress = pd.DataFrame(
            [
                {
                    "logical_match_number": 90,
                    "stage": "LAST_16",
                    "utc_date": "2026-07-04T21:00:00Z",
                    "status": "FINISHED",
                    "home_team": "Paraguay",
                    "away_team": "France",
                },
                {
                    "logical_match_number": 97,
                    "stage": "QUARTER_FINALS",
                    "utc_date": "2026-07-09T20:00:00Z",
                    "status": "FINISHED",
                    "home_team": "France",
                    "away_team": "Morocco",
                },
                {
                    "logical_match_number": 101,
                    "stage": "SEMI_FINALS",
                    "utc_date": "2026-07-14T19:00:00Z",
                    "status": "TIMED",
                    "home_team": "France",
                    "away_team": None,
                },
            ]
        )
        slot = team_next_knockout_slot(progress, "France")
        self.assertEqual(slot["match_number"], 101)
        self.assertEqual(slot["stage_label"], "Semi-finals")
        self.assertEqual(slot["fixture"], "France vs opponent pending")

    def test_eliminated_country_has_no_next_fixture(self):
        progress = pd.DataFrame(
            [
                {
                    "logical_match_number": 97,
                    "stage": "QUARTER_FINALS",
                    "utc_date": "2026-07-09T20:00:00Z",
                    "status": "FINISHED",
                    "home_team": "France",
                    "away_team": "Morocco",
                }
            ]
        )
        self.assertTrue(team_next_knockout_slot(progress, "Morocco").empty)

    def test_adaptive_adjustment_waits_for_evidence(self):
        collecting = pd.DataFrame(
            [
                {
                    "team": "France",
                    "rating_change": 100.0,
                    "confidence_level": "High",
                    "overreaction_risk": "Stable signal",
                    "guardrail_decision": "collecting_evidence",
                }
            ]
        )
        trusted = collecting.copy()
        trusted.loc[0, "guardrail_decision"] = "trusted"
        self.assertEqual(adaptive_rating_adjustment("France", collecting, "SEMI_FINALS"), 0.0)
        self.assertGreater(adaptive_rating_adjustment("France", trusted, "SEMI_FINALS"), 0.0)


if __name__ == "__main__":
    unittest.main()
