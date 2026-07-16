import unittest

import pandas as pd

from backend.adaptive_governance import evaluate_adaptive_layer
from features.adaptive_ratings import adaptive_rating_adjustment


class AdaptiveGovernanceTests(unittest.TestCase):
    def test_mixed_timestamp_formats_keep_completed_forecasts(self):
        matches = pd.DataFrame(
            [
                {
                    "match_id": match_id,
                    "status": "FINISHED",
                    "home_score_full_time": 1,
                    "away_score_full_time": 0,
                }
                for match_id in (1, 2)
            ]
        )
        ledger = pd.DataFrame(
            [
                {
                    "match_id": 1,
                    "generated_at_utc": "2026-07-14 06:26:41.675946+00:00",
                    "created_before_kickoff": True,
                    "prob_home_win": 0.5,
                    "prob_draw": 0.3,
                    "prob_away_win": 0.2,
                    "baseline_prob_home_win": 0.5,
                    "baseline_prob_draw": 0.3,
                    "baseline_prob_away_win": 0.2,
                },
                {
                    "match_id": 2,
                    "generated_at_utc": "2026-07-16T23:07:01.107958+00:00",
                    "created_before_kickoff": True,
                    "prob_home_win": 0.5,
                    "prob_draw": 0.3,
                    "prob_away_win": 0.2,
                    "baseline_prob_home_win": 0.5,
                    "baseline_prob_draw": 0.3,
                    "baseline_prob_away_win": 0.2,
                },
            ]
        )

        health = evaluate_adaptive_layer(matches, ledger)

        self.assertEqual(health["comparison_sample_size"], 2)

    def test_rolls_back_when_adaptive_probabilities_regress_beyond_guardrail(self):
        matches = pd.DataFrame(
            [
                {
                    "match_id": index,
                    "status": "FINISHED",
                    "home_score_full_time": 1,
                    "away_score_full_time": 0,
                }
                for index in range(1, 22)
            ]
        )
        ledger = pd.DataFrame(
            [
                {
                    "match_id": index,
                    "generated_at_utc": "2026-06-01T00:00:00Z",
                    "created_before_kickoff": True,
                    "prob_home_win": 0.10,
                    "prob_draw": 0.10,
                    "prob_away_win": 0.80,
                    "baseline_prob_home_win": 0.80,
                    "baseline_prob_draw": 0.10,
                    "baseline_prob_away_win": 0.10,
                }
                for index in range(1, 22)
            ]
        )

        health = evaluate_adaptive_layer(matches, ledger)

        self.assertEqual(health["comparison_sample_size"], 21)
        self.assertEqual(health["decision"], "rollback")
        self.assertGreater(health["delta"]["brier"], 0.015)

    def test_collects_evidence_before_the_minimum_sample(self):
        health = evaluate_adaptive_layer(pd.DataFrame(), pd.DataFrame())

        self.assertEqual(health["decision"], "collecting_evidence")
        self.assertEqual(health["comparison_sample_size"], 0)

    def test_rollback_decision_disables_the_adaptive_nudge(self):
        ratings = pd.DataFrame(
            [
                {
                    "team": "Ghana",
                    "rating_change": 24.0,
                    "confidence_level": "High",
                    "overreaction_risk": "Stable signal",
                    "guardrail_decision": "rollback",
                }
            ]
        )

        self.assertEqual(adaptive_rating_adjustment("Ghana", ratings, stage="FINAL"), 0.0)
