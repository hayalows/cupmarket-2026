from __future__ import annotations

import unittest

import pandas as pd

from features.tournament_path_data import (
    available_teams,
    opponent_options,
    preferred_team,
    round_of_16_build,
    status_label,
    team_fixtures,
    team_next_knockout_slot,
    team_summary,
    tournament_summary,
)


class TournamentPathDataTests(unittest.TestCase):
    def test_available_teams_combines_market_and_fixture_sources(self):
        data = {
            "prices": pd.DataFrame({"team": ["Ghana", "England"]}),
            "path_status": pd.DataFrame({"team": ["Panama"]}),
            "opponents": pd.DataFrame({"team": ["Ghana"], "opponent": ["Colombia"]}),
            "movements": pd.DataFrame(),
            "snapshots": pd.DataFrame(),
            "progress": pd.DataFrame(
                {"home_team": ["Portugal"], "away_team": ["Uzbekistan"]}
            ),
            "bracket": pd.DataFrame(),
        }

        teams = available_teams(data)

        self.assertEqual(
            teams,
            ["England", "Ghana", "Panama", "Portugal", "Uzbekistan"],
        )

    def test_preferred_team_respects_request_then_ghana_then_market_leader(self):
        teams = ["Argentina", "England", "Ghana"]
        prices = pd.DataFrame(
            {
                "team": ["England", "Argentina", "Ghana"],
                "cupmarket_price": [60.0, 70.0, 20.0],
            }
        )

        self.assertEqual(preferred_team(teams, "England", prices), "England")
        self.assertEqual(preferred_team(teams, None, prices), "Ghana")
        self.assertEqual(
            preferred_team(["Argentina", "England"], None, prices),
            "Argentina",
        )

    def test_opponent_options_rank_conditional_probability(self):
        opponents = pd.DataFrame(
            {
                "team": ["Ghana", "Ghana", "Ghana", "England"],
                "opponent": ["Portugal", "Colombia", "DR Congo", "Panama"],
                "probability_given_qualification": [0.20, 0.55, 0.25, 1.0],
            }
        )

        result = opponent_options(opponents, "Ghana", limit=2)

        self.assertEqual(result["opponent"].tolist(), ["Colombia", "DR Congo"])

    def test_tournament_summary_handles_projected_locked_and_live_states(self):
        projected = tournament_summary(
            {
                "progress": pd.DataFrame(),
                "bracket": pd.DataFrame(),
                "path_status": pd.DataFrame({"team": ["Ghana"]}),
                "bracket_state": {},
            }
        )
        self.assertEqual(projected["current_stage"], "Group-stage paths")
        self.assertEqual(projected["bracket_status"], "Bracket projected")

        locked = tournament_summary(
            {
                "progress": pd.DataFrame(),
                "bracket": pd.DataFrame(
                    {
                        "home_team": ["Ghana"],
                        "away_team": ["Colombia"],
                    }
                ),
                "path_status": pd.DataFrame(),
                "bracket_state": {"status": "locked"},
            }
        )
        self.assertEqual(locked["current_stage"], "Round of 32")
        self.assertEqual(locked["upcoming_knockout_matches"], 1)
        self.assertTrue(locked["is_locked"])

        live = tournament_summary(
            {
                "progress": pd.DataFrame(
                    {
                        "stage": ["LAST_32", "LAST_32", "LAST_16"],
                        "status": ["FINISHED", "IN_PLAY", "TIMED"],
                    }
                ),
                "bracket": pd.DataFrame(),
                "path_status": pd.DataFrame(),
                "bracket_state": {"status": "locked"},
            }
        )
        self.assertEqual(live["current_stage"], "Round of 32")
        self.assertEqual(live["completed_knockout_matches"], 1)
        self.assertEqual(live["live_knockout_matches"], 1)
        self.assertEqual(live["upcoming_knockout_matches"], 1)

    def test_team_fixtures_uses_progress_before_locked_bracket(self):
        progress = pd.DataFrame(
            {
                "home_team": ["Ghana", "England"],
                "away_team": ["Colombia", "Panama"],
                "status": ["FINISHED", "TIMED"],
                "utc_date": ["2026-06-29T12:00:00Z", "2026-06-30T12:00:00Z"],
            }
        )
        bracket = pd.DataFrame(
            {
                "home_team": ["Ghana"],
                "away_team": ["Portugal"],
                "utc_date": ["2026-06-29T12:00:00Z"],
            }
        )

        rows = team_fixtures(progress, bracket, "Ghana")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.iloc[0]["away_team"], "Colombia")

    def test_status_labels_are_plain_language(self):
        self.assertEqual(status_label("confirmed"), "Fixture confirmed")
        self.assertEqual(status_label("slot_confirmed"), "Slot confirmed")
        self.assertEqual(status_label("custom_state"), "Custom State")

    def test_round_of_16_build_uses_known_winner_and_pending_opponent(self):
        progress = pd.DataFrame(
            [
                {
                    "logical_match_number": 73,
                    "stage": "LAST_32",
                    "status": "FINISHED",
                    "home_team": "South Africa",
                    "away_team": "Canada",
                    "home_score": 0,
                    "away_score": 1,
                    "advancing_team": "Canada",
                },
                {
                    "logical_match_number": 75,
                    "stage": "LAST_32",
                    "status": "TIMED",
                    "home_team": "Germany",
                    "away_team": "Paraguay",
                    "advancing_team": pd.NA,
                },
                {
                    "logical_match_number": 90,
                    "stage": "LAST_16",
                    "status": "TIMED",
                    "home_team": pd.NA,
                    "away_team": pd.NA,
                    "utc_date": "2026-07-04T21:00:00Z",
                },
            ]
        )

        slots = round_of_16_build(progress)
        canada_slot = team_next_knockout_slot(progress, "Canada")

        row = slots.loc[slots["match_number"].eq(90)].iloc[0]
        self.assertEqual(row["fixture"], "Canada vs Germany/Paraguay winner")
        self.assertEqual(row["state"], "One team through")
        self.assertEqual(canada_slot["match_number"], 90)
        self.assertEqual(canada_slot["fixture"], "Canada vs Germany/Paraguay winner")

    def test_team_summary_prefers_played_event_and_keeps_latest_refresh(self):
        movements = pd.DataFrame(
            [
                {
                    "team": "Canada",
                    "snapshot_id": "2026-06-28T21:42:00Z",
                    "price_before": 32.09,
                    "price_after": 38.00,
                    "price_change": 5.91,
                    "movement_type": "match_event",
                    "relationship_to_event": "played",
                    "trigger_matches": "South Africa 0-1 Canada",
                },
                {
                    "team": "Canada",
                    "snapshot_id": "2026-06-29T04:42:00Z",
                    "price_before": 43.65,
                    "price_after": 43.57,
                    "price_change": -0.08,
                    "movement_type": "publication_refresh",
                    "relationship_to_event": "publication_refresh",
                    "trigger_matches": "Official knockout model refresh",
                },
                {
                    "team": "Brazil",
                    "snapshot_id": "2026-06-28T21:42:00Z",
                    "price_before": 38.00,
                    "price_after": 37.05,
                    "movement_type": "match_event",
                    "relationship_to_event": "other",
                    "trigger_matches": "South Africa 0-1 Canada",
                },
            ]
        )
        data = {
            "prices": pd.DataFrame(
                {"team": ["Canada", "Brazil"], "cupmarket_price": [43.57, 39.07]}
            ),
            "path_status": pd.DataFrame(),
            "movement_history": movements,
            "movements": pd.DataFrame(),
            "opponents": pd.DataFrame(),
            "progress": pd.DataFrame(),
            "bracket": pd.DataFrame(),
        }

        canada = team_summary(data, "Canada")
        brazil = team_summary(data, "Brazil")

        self.assertEqual(canada["movement"]["trigger_matches"], "South Africa 0-1 Canada")
        self.assertEqual(canada["movement"]["movement_type"], "match_event")
        self.assertEqual(canada["latest_movement"]["movement_type"], "publication_refresh")
        self.assertTrue(brazil["movement"].empty)


if __name__ == "__main__":
    unittest.main()
