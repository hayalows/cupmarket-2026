from __future__ import annotations

import unittest

import pandas as pd

from features import overview_v3


class TournamentPulseStateTests(unittest.TestCase):
    def test_eliminated_team_is_labelled_by_locked_exit_stage(self):
        prices = pd.DataFrame(
            [
                {
                    "team": "South Africa",
                    "cupmarket_price": 15.0,
                    "prob_round_32_exit": 1.0,
                    "prob_champion": 0.0,
                },
                {
                    "team": "Canada",
                    "cupmarket_price": 43.65,
                    "prob_round_32_exit": 0.0,
                    "prob_champion": 0.0157,
                },
            ]
        )

        eliminated = overview_v3._eliminated_teams(prices)
        alive = overview_v3._alive_teams(prices)

        self.assertEqual(eliminated.iloc[0]["Country"], "South Africa")
        self.assertEqual(eliminated.iloc[0]["Exit"], "Round of 32")
        self.assertEqual(alive.iloc[0]["team"], "Canada")

    def test_zero_champion_chance_does_not_mean_eliminated(self):
        prices = pd.DataFrame(
            [
                {
                    "team": "Cape Verde Islands",
                    "cupmarket_price": 16.1,
                    "prob_round_32_exit": 0.9457,
                    "prob_reach_round_16": 0.0543,
                    "prob_champion": 0.0,
                }
            ]
        )

        eliminated = overview_v3._eliminated_teams(prices)
        alive = overview_v3._alive_teams(prices)

        self.assertTrue(eliminated.empty)
        self.assertEqual(alive.iloc[0]["team"], "Cape Verde Islands")

    def test_knockout_result_names_advanced_and_eliminated_teams(self):
        progress = pd.DataFrame(
            [
                {
                    "api_match_id": 537417,
                    "stage": "LAST_32",
                    "utc_date": pd.Timestamp("2026-06-28T19:00:00Z"),
                    "status": "FINISHED",
                    "home_team": "South Africa",
                    "away_team": "Canada",
                    "home_score": 0,
                    "away_score": 1,
                    "advancing_team": "Canada",
                }
            ]
        )

        results = overview_v3._knockout_results(pd.DataFrame(), progress)

        self.assertEqual(results.iloc[0]["Advanced"], "Canada")
        self.assertEqual(results.iloc[0]["Eliminated"], "South Africa")
        self.assertIn("South Africa 0-1 Canada", results.iloc[0]["Result"])

    def test_default_stage_prefers_next_official_knockout_fixture(self):
        matches = pd.DataFrame(
            [
                {
                    "match_id": 1,
                    "stage": "GROUP_STAGE",
                    "status": "FINISHED",
                    "utc_date": "2026-06-20T19:00:00Z",
                    "home_team": "A",
                    "away_team": "B",
                }
            ]
        )
        progress = pd.DataFrame(
            [
                {
                    "api_match_id": 537423,
                    "stage": "LAST_32",
                    "status": "TIMED",
                    "utc_date": "2026-06-29T17:00:00Z",
                    "home_team": "Brazil",
                    "away_team": "Japan",
                }
            ]
        )

        self.assertEqual(overview_v3._default_stage(matches, progress), "LAST_32")

    def test_stage_fixture_table_uses_knockout_outcome_copy(self):
        fixtures = pd.DataFrame(
            [
                {
                    "api_match_id": 537417,
                    "stage": "LAST_32",
                    "status": "FINISHED",
                    "utc_date": "2026-06-28T19:00:00Z",
                    "home_team": "South Africa",
                    "away_team": "Canada",
                    "home_score": 0,
                    "away_score": 1,
                    "advancing_team": "Canada",
                }
            ]
        )

        table = overview_v3._stage_fixture_table(fixtures)

        self.assertEqual(table.iloc[0]["Stage"], "Round of 32")
        self.assertEqual(table.iloc[0]["Fixture"], "South Africa vs Canada")
        self.assertEqual(table.iloc[0]["Score"], "0-1")
        self.assertEqual(table.iloc[0]["Outcome"], "Canada advanced")

    def test_stage_decisions_split_advanced_eliminated_and_pending(self):
        fixtures = pd.DataFrame(
            [
                {
                    "stage": "LAST_32",
                    "status": "FINISHED",
                    "home_team": "South Africa",
                    "away_team": "Canada",
                    "home_score": 0,
                    "away_score": 1,
                    "advancing_team": "Canada",
                },
                {
                    "stage": "LAST_32",
                    "status": "TIMED",
                    "home_team": "Germany",
                    "away_team": "Paraguay",
                    "advancing_team": pd.NA,
                },
            ]
        )

        decisions = overview_v3._stage_decision_tables(fixtures)

        self.assertEqual(decisions["advanced"].iloc[0]["Country"], "Canada")
        self.assertEqual(decisions["eliminated"].iloc[0]["Country"], "South Africa")
        self.assertEqual(decisions["pending"].iloc[0]["Fixture"], "Germany vs Paraguay")

    def test_tbd_knockout_rows_do_not_become_stage_participants(self):
        fixtures = pd.DataFrame(
            [
                {
                    "stage": "LAST_16",
                    "status": "TIMED",
                    "home_team": "TBD",
                    "away_team": None,
                },
                {
                    "stage": "LAST_16",
                    "status": "TIMED",
                    "home_team": "Canada",
                    "away_team": "nan",
                },
            ]
        )

        participants = overview_v3._stage_participants(fixtures)

        self.assertEqual(participants, ["Canada"])

    def test_stage_story_says_chance_to_advance_for_live_knockout(self):
        fixtures = pd.DataFrame(
            [
                {
                    "stage": "LAST_32",
                    "status": "LIVE",
                    "utc_date": "2026-06-29T17:00:00Z",
                    "home_team": "Brazil",
                    "away_team": "Japan",
                    "home_score": 1,
                    "away_score": 1,
                }
            ]
        )

        story = overview_v3._stage_story("LAST_32", fixtures, pd.DataFrame())

        self.assertIn("chance to advance", story)
        self.assertNotIn("qualification", story.lower())


if __name__ == "__main__":
    unittest.main()
