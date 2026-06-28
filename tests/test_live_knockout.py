from __future__ import annotations

import unittest

import pandas as pd

from backend.live_knockout import (
    is_live_knockout_match,
    penalty_home_probability,
    run_live_knockout_projection,
)


def _match_row(**overrides):
    row = {
        "match_id": 9001,
        "utc_date": pd.Timestamp("2026-06-28T19:00:00Z"),
        "status": "IN_PLAY",
        "stage": "LAST_32",
        "group": pd.NA,
        "home_team": "South Africa",
        "away_team": "Canada",
        "home_score_full_time": 0,
        "away_score_full_time": 0,
        "minute": 60,
    }
    row.update(overrides)
    return row


def _prediction_row(**overrides):
    row = {
        "match_id": 9001,
        "generated_at_utc": pd.Timestamp("2026-06-28T18:00:00Z"),
        "expected_home_goals": 1.2,
        "expected_away_goals": 1.1,
        "prob_home_advance": 0.53,
        "prob_away_advance": 0.47,
        "home_prediction_elo": 1700.0,
        "away_prediction_elo": 1680.0,
    }
    row.update(overrides)
    return row


class LiveKnockoutTests(unittest.TestCase):
    def test_detects_live_knockout_but_not_group_stage(self):
        knockout = pd.Series(_match_row())
        group = pd.Series(_match_row(stage="GROUP_STAGE", group="GROUP_A"))

        self.assertTrue(is_live_knockout_match(knockout))
        self.assertFalse(is_live_knockout_match(group))

    def test_group_stage_live_match_is_not_projected(self):
        matches = pd.DataFrame([_match_row(stage="GROUP_STAGE", group="GROUP_A")])
        predictions = pd.DataFrame([_prediction_row()])

        result = run_live_knockout_projection(matches, predictions, match_id=9001)

        self.assertFalse(result["available"])

    def test_current_lead_and_minute_shift_advance_probability(self):
        matches = pd.DataFrame(
            [
                _match_row(
                    home_score_full_time=2,
                    away_score_full_time=0,
                    minute=80,
                )
            ]
        )
        predictions = pd.DataFrame([_prediction_row()])

        result = run_live_knockout_projection(
            matches,
            predictions,
            match_id=9001,
            n_simulations=1200,
            random_seed=11,
        )
        live = result["matches"][9001]

        self.assertTrue(result["available"])
        self.assertEqual(live["current_score"], "2-0")
        self.assertEqual(live["minute"], 80)
        self.assertGreater(live["home_advance_probability"], 0.95)
        self.assertLess(live["away_advance_probability"], 0.05)
        self.assertTrue(live["likely_final_scorelines"])

    def test_tied_after_extra_time_uses_bounded_penalty_probability(self):
        matches = pd.DataFrame(
            [
                _match_row(
                    home_score_full_time=1,
                    away_score_full_time=1,
                    minute=120,
                )
            ]
        )
        predictions = pd.DataFrame(
            [
                _prediction_row(
                    home_prediction_elo=2300.0,
                    away_prediction_elo=1400.0,
                )
            ]
        )

        penalty_probability = penalty_home_probability(predictions.iloc[0])
        result = run_live_knockout_projection(
            matches,
            predictions,
            match_id=9001,
            n_simulations=2000,
            random_seed=19,
        )
        live = result["matches"][9001]

        self.assertAlmostEqual(penalty_probability, 0.65)
        self.assertGreater(live["home_advance_probability"], 0.61)
        self.assertLess(live["home_advance_probability"], 0.69)
        self.assertGreater(live["method_probabilities"]["penalties"], 0.99)

    def test_missing_prediction_returns_unavailable(self):
        matches = pd.DataFrame([_match_row()])
        predictions = pd.DataFrame(columns=["match_id"])

        result = run_live_knockout_projection(matches, predictions, match_id=9001)

        self.assertFalse(result["available"])
        self.assertEqual(
            result["skipped"][0]["reason"],
            "missing_pre_match_prediction",
        )


if __name__ == "__main__":
    unittest.main()
