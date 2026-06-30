from __future__ import annotations

import unittest

import pandas as pd

from features.tournament_helpers import batch_context_for_match


class TournamentHelperTests(unittest.TestCase):
    def test_batch_context_prefers_official_knockout_snapshot(self):
        processed = pd.DataFrame(
            [
                {
                    "match_id": 537415,
                    "processed_at_utc": "2026-06-29T23:43:34+00:00",
                    "home_team": "Germany",
                    "away_team": "Paraguay",
                }
            ]
        )
        history = pd.DataFrame(
            [
                {
                    "team": "Paraguay",
                    "generated_at_utc": "2026-06-29T23:45:39+00:00",
                    "cupmarket_price": 33.27,
                    "model_version": "phase9b_adaptive_prediction_v1",
                    "bracket_mode": "provisional_constraint_assignment",
                },
                {
                    "team": "Paraguay",
                    "generated_at_utc": "2026-06-29T23:45:50+00:00",
                    "cupmarket_price": 43.66,
                    "model_version": "phase6_knockout_progression_v1",
                    "bracket_mode": "official_api_locked_knockout_progression",
                },
            ]
        )
        history["generated_at_utc"] = pd.to_datetime(
            history["generated_at_utc"], utc=True
        )

        context = batch_context_for_match(537415, processed, history)
        snapshot = context["snapshot"]

        self.assertTrue(context["available"])
        self.assertEqual(float(snapshot.iloc[0]["cupmarket_price"]), 43.66)
        self.assertEqual(
            str(snapshot.iloc[0]["model_version"]),
            "phase6_knockout_progression_v1",
        )


if __name__ == "__main__":
    unittest.main()
