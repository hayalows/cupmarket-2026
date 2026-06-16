from __future__ import annotations

import unittest

import pandas as pd

from features.market_movement import add_rank_movement, rank_movement_text


class MarketMovementTests(unittest.TestCase):
    def test_reconstructs_previous_rank_from_previous_prices(self):
        prices = pd.DataFrame(
            [
                {"team": "Alpha", "market_rank": 1, "previous_price": 40.0},
                {"team": "Bravo", "market_rank": 2, "previous_price": 50.0},
                {"team": "Charlie", "market_rank": 3, "previous_price": 30.0},
            ]
        )

        result = add_rank_movement(prices).set_index("team")

        self.assertEqual(int(result.loc["Alpha", "previous_market_rank"]), 2)
        self.assertEqual(int(result.loc["Alpha", "rank_change"]), 1)
        self.assertEqual(int(result.loc["Bravo", "previous_market_rank"]), 1)
        self.assertEqual(int(result.loc["Bravo", "rank_change"]), -1)
        self.assertEqual(int(result.loc["Charlie", "rank_change"]), 0)

    def test_equal_prices_receive_stable_sequential_ranks(self):
        prices = pd.DataFrame(
            [
                {"team": "Bravo", "market_rank": 1, "previous_price": 40.0},
                {"team": "Alpha", "market_rank": 2, "previous_price": 40.0},
                {"team": "Charlie", "market_rank": 3, "previous_price": 30.0},
            ]
        )

        result = add_rank_movement(prices).set_index("team")

        self.assertEqual(int(result.loc["Alpha", "previous_market_rank"]), 1)
        self.assertEqual(int(result.loc["Bravo", "previous_market_rank"]), 2)
        self.assertEqual(int(result.loc["Charlie", "previous_market_rank"]), 3)

    def test_explicit_previous_rank_takes_priority(self):
        prices = pd.DataFrame(
            [
                {
                    "team": "Alpha",
                    "market_rank": 2,
                    "previous_market_rank": 5,
                    "previous_price": 99.0,
                }
            ]
        )

        result = add_rank_movement(prices).iloc[0]

        self.assertEqual(int(result["previous_market_rank"]), 5)
        self.assertEqual(int(result["rank_change"]), 3)

    def test_rank_movement_text_explains_direction_and_origin(self):
        self.assertEqual(
            rank_movement_text(3, 5, include_previous=True),
            "↑ 2 places from #5",
        )
        self.assertEqual(
            rank_movement_text(5, 3, include_previous=True),
            "↓ 2 places from #3",
        )
        self.assertEqual(
            rank_movement_text(4, 4, include_previous=True),
            "No change from #4",
        )

    def test_missing_previous_price_does_not_create_false_movement(self):
        prices = pd.DataFrame(
            [{"team": "Alpha", "market_rank": 1, "previous_price": None}]
        )
        result = add_rank_movement(prices)

        self.assertTrue(pd.isna(result.iloc[0]["previous_market_rank"]))
        self.assertEqual(
            rank_movement_text(1, result.iloc[0]["previous_market_rank"]),
            "Previous rank unavailable",
        )


if __name__ == "__main__":
    unittest.main()
