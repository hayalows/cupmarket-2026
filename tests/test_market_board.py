from __future__ import annotations

import unittest

import pandas as pd

from features.market_board import (
    adaptive_health,
    build_market_board,
    display_market_board,
    filter_market_board,
)


class MarketBoardTests(unittest.TestCase):
    def _prices(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "team": "Canada",
                    "market_rank": 6,
                    "cupmarket_price": 43.57,
                    "previous_price": 43.65,
                    "price_change": -0.08,
                    "price_change_percent": -0.18,
                    "prob_reach_round_32": 1.0,
                    "prob_reach_round_16": 1.0,
                    "prob_reach_quarter_final": 0.45,
                    "prob_reach_semi_final": 0.17,
                    "prob_reach_final": 0.06,
                    "prob_champion": 0.016,
                    "prob_group_exit": 0.0,
                    "prob_round_32_exit": 0.0,
                    "prob_round_16_exit": 0.55,
                    "prob_quarter_final_exit": 0.28,
                    "prob_semi_final_exit": 0.11,
                    "prob_runner_up": 0.04,
                },
                {
                    "team": "South Africa",
                    "market_rank": 48,
                    "cupmarket_price": 0.0,
                    "previous_price": 12.0,
                    "price_change": -12.0,
                    "price_change_percent": -100.0,
                    "prob_reach_round_32": 1.0,
                    "prob_reach_round_16": 0.0,
                    "prob_reach_quarter_final": 0.0,
                    "prob_reach_semi_final": 0.0,
                    "prob_reach_final": 0.0,
                    "prob_champion": 0.0,
                    "prob_group_exit": 0.0,
                    "prob_round_32_exit": 1.0,
                    "prob_round_16_exit": 0.0,
                    "prob_quarter_final_exit": 0.0,
                    "prob_semi_final_exit": 0.0,
                    "prob_runner_up": 0.0,
                },
            ]
        )

    def test_build_market_board_keeps_status_and_next_target(self):
        ratings = pd.DataFrame(
            [
                {
                    "team": "Canada",
                    "rating_change": 63.3,
                    "confidence_level": "High",
                    "overreaction_risk": "Stable signal",
                }
            ]
        )

        board = build_market_board(self._prices(), ratings)
        canada = board.loc[board["team"].eq("Canada")].iloc[0]
        south_africa = board.loc[board["team"].eq("South Africa")].iloc[0]

        self.assertEqual(len(board), 2)
        self.assertEqual(canada["market_status"], "In Round of 16")
        self.assertEqual(canada["next_target"], "Quarter-final")
        self.assertAlmostEqual(float(canada["next_stage_probability"]), 0.45)
        self.assertEqual(south_africa["market_status"], "Out: Round of 32")

    def test_filter_market_board_sorts_and_filters(self):
        board = build_market_board(self._prices())

        alive = filter_market_board(board, status_filter="Alive")
        fallers = filter_market_board(board, sort_by="Biggest fallers")

        self.assertEqual(alive["team"].tolist(), ["Canada"])
        self.assertEqual(fallers.iloc[0]["team"], "South Africa")

    def test_display_market_board_formats_probabilities(self):
        display = display_market_board(build_market_board(self._prices()))

        self.assertIn("Champion", display.columns)
        self.assertEqual(display.loc[display["Country"].eq("Canada"), "QF"].iloc[0], "45.0%")
        self.assertIn("CM", display.loc[display["Country"].eq("Canada"), "Price"].iloc[0])

    def test_adaptive_health_detects_enabled_nonzero_predictions(self):
        predictions = pd.DataFrame(
            [
                {
                    "home_adaptive_adjustment": 4.2,
                    "away_adaptive_adjustment": 0.0,
                    "adaptive_prediction_enabled": True,
                    "adaptive_model_version": "phase9b_adaptive_prediction_v1",
                }
            ]
        )
        ratings = pd.DataFrame([{"team": "Canada"}])

        health = adaptive_health(predictions, ratings)

        self.assertTrue(health["working"])
        self.assertEqual(health["enabled_rows"], 1)
        self.assertEqual(health["nonzero_prediction_rows"], 1)
        self.assertEqual(health["rating_rows"], 1)


if __name__ == "__main__":
    unittest.main()
