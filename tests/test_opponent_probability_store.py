from __future__ import annotations

from types import SimpleNamespace
import unittest

import pandas as pd

from backend.opponent_probability_store import (
    classify_team_path,
    simulate_opponent_probabilities,
)


class FakePipeline:
    INITIAL_RATING = 1500.0
    FIXED_R32 = {
        73: ("2A", "2B"),
        75: ("1F", "2C"),
        76: ("1C", "2F"),
        78: ("2E", "2I"),
        83: ("2K", "2L"),
        84: ("1H", "2J"),
        86: ("1J", "2H"),
        88: ("2D", "2G"),
    }
    THIRD_PLACE_R32_WINNER = {
        74: "1E",
        77: "1I",
        79: "1A",
        80: "1L",
        81: "1D",
        82: "1G",
        85: "1B",
        87: "1K",
    }

    @staticmethod
    def rank_group(teams, results, live_elo_lookup):
        stats = {
            team: {
                "team": team,
                "points": 0,
                "goal_difference": 0,
                "goals_for": 0,
            }
            for team in teams
        }
        for result in results:
            home = stats[result["home_team"]]
            away = stats[result["away_team"]]
            hg = int(result["home_goals"])
            ag = int(result["away_goals"])
            home["goals_for"] += hg
            away["goals_for"] += ag
            home["goal_difference"] += hg - ag
            away["goal_difference"] += ag - hg
            if hg > ag:
                home["points"] += 3
            elif ag > hg:
                away["points"] += 3
            else:
                home["points"] += 1
                away["points"] += 1
        table = sorted(
            stats.values(),
            key=lambda row: (
                row["points"],
                row["goal_difference"],
                row["goals_for"],
                live_elo_lookup.get(row["team"], 1500),
            ),
            reverse=True,
        )
        return table, 0

    @staticmethod
    def rank_third_placed(rows, live_elo_lookup):
        return sorted(
            rows,
            key=lambda row: (
                row["points"],
                row["goal_difference"],
                row["goals_for"],
                live_elo_lookup.get(row["team"], 1500),
            ),
            reverse=True,
        )

    @staticmethod
    def choose_third_place_assignment(best_third_by_group, rng):
        groups = sorted(best_third_by_group)
        slots = [74, 77, 79, 80, 81, 82, 85, 87]
        return {
            slot: best_third_by_group[group]
            for slot, group in zip(slots, groups)
        }


class OpponentProbabilityTests(unittest.TestCase):
    def test_runner_up_fixture_confirms_when_both_groups_are_complete(self):
        status, slot, match_id = classify_team_path(
            "Ghana",
            "L",
            2,
            {"K", "L"},
            FakePipeline,
        )
        self.assertEqual(status, "confirmed")
        self.assertEqual(slot, "2L")
        self.assertEqual(match_id, 83)

    def test_group_winner_third_place_opponent_remains_pending(self):
        status, slot, match_id = classify_team_path(
            "Ghana",
            "L",
            1,
            set("ABCDEFGHIJKL"),
            FakePipeline,
        )
        self.assertEqual(status, "slot_confirmed_opponent_pending")
        self.assertEqual(slot, "1L")
        self.assertEqual(match_id, 80)

    def test_incomplete_group_is_projected(self):
        status, slot, match_id = classify_team_path(
            "Ghana",
            "L",
            2,
            {"K"},
            FakePipeline,
        )
        self.assertEqual((status, slot, match_id), ("projected", None, None))

    def test_pairing_probabilities_sum_to_qualification_probability(self):
        matches, predictions, elo = self._finished_tournament_fixture()
        opponents, summary = simulate_opponent_probabilities(
            matches,
            predictions,
            elo,
            FakePipeline,
            number_of_simulations=20,
            random_seed=42,
        )

        self.assertEqual(summary["team"].nunique(), 48)
        for row in summary.itertuples(index=False):
            team_rows = opponents.loc[opponents["team"] == row.team]
            self.assertAlmostEqual(
                float(team_rows["probability_unconditional"].sum()),
                float(row.prob_reach_round_32),
                places=9,
            )
            if row.prob_reach_round_32 > 0:
                self.assertAlmostEqual(
                    float(team_rows["probability_given_qualification"].sum()),
                    1.0,
                    places=9,
                )

    @staticmethod
    def _finished_tournament_fixture():
        rows = []
        match_id = 1
        elo = {}
        for group_index, group in enumerate("ABCDEFGHIJKL"):
            teams = [f"{group}{number}" for number in range(1, 5)]
            for number, team in enumerate(teams, start=1):
                elo[team] = 2000 - group_index * 10 - number
            fixtures = [
                (teams[0], teams[1], 3, 0),
                (teams[2], teams[3], 2, 0),
                (teams[0], teams[2], 2, 0),
                (teams[1], teams[3], 1, 0),
                (teams[0], teams[3], 1, 0),
                (teams[1], teams[2], 2, 1),
            ]
            for home, away, home_score, away_score in fixtures:
                rows.append(
                    {
                        "match_id": match_id,
                        "utc_date": f"2026-06-{10 + group_index:02d}T12:00:00Z",
                        "stage": "GROUP_STAGE",
                        "group": f"GROUP_{group}",
                        "status": "FINISHED",
                        "home_team": home,
                        "away_team": away,
                        "home_score_full_time": home_score,
                        "away_score_full_time": away_score,
                    }
                )
                match_id += 1
        return pd.DataFrame(rows), pd.DataFrame(), elo


if __name__ == "__main__":
    unittest.main()
