from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from backend import knockout_stage as ks


class ConstantModel:
    def __init__(self, value=1.2):
        self.value = value

    def predict(self, frame):
        return np.array([self.value] * len(frame))


class FakePipeline:
    INITIAL_RATING = 1500.0
    INITIAL_GOALS_AVERAGE = 1.25
    INITIAL_POINTS_AVERAGE = 1.25
    STATE_ALPHA = 0.18
    WORLD_CUP_K = 60.0
    HOST_ELO_ADJUSTMENT = 65.0
    WORLD_CUP_HOSTS = {"Mexico", "Canada", "United States"}
    EXTRA_TIME_GOAL_FACTOR = 0.30
    FEATURE_COLUMNS = [
        "home_elo",
        "away_elo",
        "elo_diff",
        "abs_elo_diff",
        "neutral",
        "home_attack_form",
        "home_defence_form",
        "away_attack_form",
        "away_defence_form",
        "home_points_form",
        "away_points_form",
        "home_matches_before",
        "away_matches_before",
        "home_rest_days",
        "away_rest_days",
        "k_factor",
    ]
    SETTLEMENT_VALUES = {
        "group_exit": 5.0,
        "round_32_exit": 15.0,
        "round_16_exit": 30.0,
        "quarter_final_exit": 50.0,
        "semi_final_exit": 70.0,
        "runner_up": 85.0,
        "champion": 100.0,
    }
    ROUND_OF_16 = {
        89: (73, 76),
        90: (75, 78),
        91: (74, 77),
        92: (79, 80),
        93: (83, 84),
        94: (81, 82),
        95: (87, 86),
        96: (85, 88),
    }
    QUARTER_FINALS = {
        97: (89, 90),
        98: (93, 94),
        99: (91, 92),
        100: (95, 96),
    }
    SEMI_FINALS = {101: (97, 98), 102: (99, 100)}

    @staticmethod
    def apply_performance_adjusted_settlement_columns(
        probabilities,
        *args,
        **kwargs,
    ):
        current = probabilities.copy()
        current["exit_stage_floor"] = np.nan
        current["performance_premium"] = 0.0
        current["adjusted_settlement_value"] = np.nan
        current["settlement_reason"] = "Test pipeline uses flat settlements."
        current["is_eliminated"] = False
        return current

    @staticmethod
    def calculate_cupmarket_price(probabilities):
        price = pd.Series(0.0, index=probabilities.index, dtype=float)
        for stage, column in {
            "group_exit": "prob_group_exit",
            "round_32_exit": "prob_round_32_exit",
            "round_16_exit": "prob_round_16_exit",
            "quarter_final_exit": "prob_quarter_final_exit",
            "semi_final_exit": "prob_semi_final_exit",
            "runner_up": "prob_runner_up",
            "champion": "prob_champion",
        }.items():
            price += (
                pd.to_numeric(probabilities[column], errors="coerce").fillna(0.0)
                * FakePipeline.SETTLEMENT_VALUES[stage]
            )
        return price

    @staticmethod
    def elo_expected_score(home_rating, away_rating, host_adjustment=0.0):
        return 1.0 / (
            1.0
            + 10
            ** ((away_rating - (home_rating + host_adjustment)) / 400.0)
        )

    @staticmethod
    def goal_margin_multiplier(home_score, away_score):
        return 1.0

    @staticmethod
    def points_from_score(goals_for, goals_against):
        if goals_for > goals_against:
            return 3.0
        if goals_for == goals_against:
            return 1.0
        return 0.0

    @staticmethod
    def clip_xg(value):
        return float(np.clip(value, 0.05, 5.5))

    @staticmethod
    def score_probability_matrix(home_xg, away_xg, max_goals=10):
        def probabilities(mean):
            values = [np.exp(-mean)]
            for number in range(1, max_goals + 1):
                values.append(values[-1] * mean / number)
            values = np.array(values)
            return values / values.sum()

        matrix = np.outer(probabilities(home_xg), probabilities(away_xg))
        return matrix / matrix.sum()

    @staticmethod
    def summarize_score_matrix(matrix):
        return {
            "prob_home_win": float(np.tril(matrix, -1).sum()),
            "prob_draw": float(np.trace(matrix)),
            "prob_away_win": float(np.triu(matrix, 1).sum()),
            "prob_btts_yes": float(matrix[1:, 1:].sum()),
            "prob_over_2_5": 0.5,
            "top_scorelines": [
                {"score": "1-1", "probability": 0.20},
                {"score": "1-0", "probability": 0.15},
                {"score": "0-0", "probability": 0.10},
            ],
        }


class KnockoutStageTests(unittest.TestCase):
    def test_penalty_shootout_advances_winner_but_is_draw_for_elo(self):
        matches = pd.DataFrame(
            [
                {
                    "match_id": 1000,
                    "utc_date": pd.Timestamp("2026-06-28", tz="UTC"),
                    "status": "FINISHED",
                    "stage": "LAST_32",
                    "home_team": "A",
                    "away_team": "B",
                    "winner": "HOME_TEAM",
                    "duration": "PENALTY_SHOOTOUT",
                    "home_score_full_time": 1,
                    "away_score_full_time": 1,
                    "home_score_penalties": 4,
                    "away_score_penalties": 3,
                }
            ]
        )
        team_map = pd.DataFrame(
            {
                "live_team_name": ["A", "B"],
                "historical_team_name": ["A", "B"],
            }
        )
        elo = pd.DataFrame(
            {
                "team": ["A", "B"],
                "elo_rating": [1500.0, 1500.0],
                "rank": [1, 2],
            }
        )
        state = pd.DataFrame(
            {
                "team": ["A", "B"],
                "matches": [3, 3],
                "ema_goals_for": [1.2, 1.2],
                "ema_goals_against": [1.2, 1.2],
                "ema_points": [1.5, 1.5],
                "last_date": [pd.NaT, pd.NaT],
            }
        )
        ledger = pd.DataFrame(columns=["match_id", "utc_date", "stage"])

        elo_updated, state_updated, ledger_updated, new, audit = (
            ks.apply_new_finished_knockout_matches(
                matches,
                team_map,
                elo,
                state,
                ledger,
                FakePipeline,
            )
        )

        self.assertEqual(len(new), 1)
        self.assertEqual(audit[0]["advancing_team"], "A")
        self.assertEqual(audit[0]["decision_method"], "penalties")
        self.assertAlmostEqual(
            float(elo_updated.set_index("team").loc["A", "elo_rating"]),
            1500.0,
        )
        _, _, ledger_second, new_second, _ = (
            ks.apply_new_finished_knockout_matches(
                matches,
                team_map,
                elo_updated,
                state_updated,
                ledger_updated,
                FakePipeline,
            )
        )
        self.assertTrue(new_second.empty)
        self.assertEqual(len(ledger_second), 1)

    def test_actual_round_of_32_result_overrides_simulation(self):
        matches, bracket, tables, team_map, elo, state = self._base_fixture()
        first = bracket.iloc[0]
        mask = matches["match_id"] == first.api_match_id
        matches.loc[
            mask,
            [
                "status",
                "winner",
                "duration",
                "home_score_full_time",
                "away_score_full_time",
            ],
        ] = ["FINISHED", "AWAY_TEAM", "REGULAR", 0, 1]

        probabilities, _, metadata = ks.run_progressive_simulation(
            matches,
            bracket,
            tables,
            ConstantModel(),
            ConstantModel(),
            team_map,
            elo,
            state,
            None,
            FakePipeline,
            40,
            7,
        )

        indexed = probabilities.set_index("team")
        self.assertEqual(
            indexed.loc[first.away_team, "prob_reach_round_16"], 1.0
        )
        self.assertEqual(
            indexed.loc[first.home_team, "prob_reach_round_16"], 0.0
        )
        self.assertEqual(metadata["actual_knockout_results_used"], 1)

    def test_probability_totals_hold_during_knockout_progression(self):
        matches, bracket, tables, team_map, elo, state = self._base_fixture()
        probabilities, _, metadata = ks.run_progressive_simulation(
            matches,
            bracket,
            tables,
            ConstantModel(),
            ConstantModel(),
            team_map,
            elo,
            state,
            None,
            FakePipeline,
            30,
            11,
        )

        totals = metadata["stage_probability_totals"]
        self.assertAlmostEqual(totals["round_32_total"], 32.0)
        self.assertAlmostEqual(totals["round_16_total"], 16.0)
        self.assertAlmostEqual(totals["quarter_final_total"], 8.0)
        self.assertAlmostEqual(totals["semi_final_total"], 4.0)
        self.assertAlmostEqual(totals["final_total"], 2.0)
        self.assertAlmostEqual(totals["champion_total"], 1.0)
        settlement_columns = [
            "prob_group_exit",
            "prob_round_32_exit",
            "prob_round_16_exit",
            "prob_quarter_final_exit",
            "prob_semi_final_exit",
            "prob_runner_up",
            "prob_champion",
        ]
        settlements = probabilities[settlement_columns].sum(axis=1)
        self.assertTrue(np.allclose(settlements, 1.0))

    def test_official_lower_right_round_of_16_matches_bracket_path(self):
        matches, bracket, tables, team_map, elo, state = self._base_fixture()
        bracket_by_logical = bracket.set_index("bracket_match_number")
        r32_winners = {
            85: bracket_by_logical.loc[85, "home_team"],
            86: bracket_by_logical.loc[86, "away_team"],
            87: bracket_by_logical.loc[87, "home_team"],
            88: bracket_by_logical.loc[88, "away_team"],
        }
        for logical, winner in r32_winners.items():
            fixture = bracket.loc[
                bracket["bracket_match_number"].eq(logical)
            ].iloc[0]
            is_home = fixture.home_team == winner
            matches.loc[
                matches["match_id"].eq(fixture.api_match_id),
                [
                    "status",
                    "winner",
                    "duration",
                    "home_score_full_time",
                    "away_score_full_time",
                ],
            ] = [
                "FINISHED",
                "HOME_TEAM" if is_home else "AWAY_TEAM",
                "REGULAR",
                1 if is_home else 0,
                0 if is_home else 1,
            ]

        matches = pd.concat(
            [
                matches,
                pd.DataFrame(
                    [
                        {
                            "match_id": 1994 + offset,
                            "utc_date": pd.Timestamp(
                                "2026-07-04T12:00:00Z"
                            )
                            + pd.Timedelta(hours=offset),
                            "status": "TIMED",
                            "stage": "LAST_16",
                            "home_team": f"Earlier Home {offset}",
                            "away_team": f"Earlier Away {offset}",
                            "winner": None,
                            "duration": None,
                            "home_score_full_time": np.nan,
                            "away_score_full_time": np.nan,
                            "home_score_penalties": np.nan,
                            "away_score_penalties": np.nan,
                        }
                        for offset in range(6)
                    ]
                    + [
                        {
                            "match_id": 2000,
                            "utc_date": pd.Timestamp(
                                "2026-07-07T16:00:00Z"
                            ),
                            "status": "FINISHED",
                            "stage": "LAST_16",
                            "home_team": r32_winners[87],
                            "away_team": r32_winners[86],
                            "winner": "HOME_TEAM",
                            "duration": "REGULAR",
                            "home_score_full_time": 3,
                            "away_score_full_time": 2,
                            "home_score_penalties": np.nan,
                            "away_score_penalties": np.nan,
                        },
                        {
                            "match_id": 2001,
                            "utc_date": pd.Timestamp(
                                "2026-07-07T20:00:00Z"
                            ),
                            "status": "TIMED",
                            "stage": "LAST_16",
                            "home_team": r32_winners[85],
                            "away_team": r32_winners[88],
                            "winner": None,
                            "duration": None,
                            "home_score_full_time": np.nan,
                            "away_score_full_time": np.nan,
                            "home_score_penalties": np.nan,
                            "away_score_penalties": np.nan,
                        },
                    ]
                ),
            ],
            ignore_index=True,
        )

        mapping = ks.logical_match_map(matches, bracket)
        actual_results = ks.build_actual_results(matches, bracket)

        self.assertEqual(mapping[2000], 95)
        self.assertEqual(mapping[2001], 96)
        self.assertEqual(actual_results[95]["winner"], r32_winners[87])
        self.assertEqual(actual_results[95]["loser"], r32_winners[86])

    def test_group_stage_metadata_counts_finished_active_and_latest(self):
        matches = pd.DataFrame(
            [
                {
                    "stage": "GROUP_STAGE",
                    "status": "FINISHED",
                    "utc_date": pd.Timestamp("2026-06-25T19:00:00Z"),
                },
                {
                    "stage": "GROUP_STAGE",
                    "status": "FINISHED",
                    "utc_date": pd.Timestamp("2026-06-28T02:00:00Z"),
                },
                {
                    "stage": "GROUP_STAGE",
                    "status": "IN_PLAY",
                    "utc_date": pd.Timestamp("2026-06-28T19:00:00Z"),
                },
                {
                    "stage": "GROUP_STAGE",
                    "status": "SUSPENDED",
                    "utc_date": pd.Timestamp("2026-06-28T22:00:00Z"),
                },
                {
                    "stage": "LAST_32",
                    "status": "FINISHED",
                    "utc_date": pd.Timestamp("2026-06-29T19:00:00Z"),
                },
            ]
        )

        metadata = ks.group_stage_metadata(matches)

        self.assertEqual(metadata["finished_group_matches"], 2)
        self.assertEqual(metadata["active_group_matches"], 2)
        self.assertEqual(
            metadata["latest_completed_group_match_utc"],
            "2026-06-28T02:00:00+00:00",
        )

    def test_active_knockout_matches_include_provider_live_statuses(self):
        matches = pd.DataFrame(
            [
                {"match_id": 1, "stage": "LAST_32", "status": "IN_PLAY"},
                {"match_id": 2, "stage": "LAST_32", "status": "LIVE"},
                {"match_id": 3, "stage": "LAST_32", "status": "PAUSED"},
                {"match_id": 4, "stage": "LAST_32", "status": "SUSPENDED"},
                {"match_id": 5, "stage": "LAST_32", "status": "TIMED"},
                {"match_id": 6, "stage": "GROUP_STAGE", "status": "LIVE"},
            ]
        )

        active = ks.active_knockout_matches(matches)

        self.assertEqual(active["match_id"].astype(int).tolist(), [1, 2, 3, 4])

    def test_advancement_probabilities_sum_to_one(self):
        home, away = ks.advancement_probabilities(
            1.5,
            1.1,
            0.56,
            FakePipeline,
        )
        self.assertAlmostEqual(home + away, 1.0)
        self.assertGreater(home, 0.0)
        self.assertLess(home, 1.0)

    @staticmethod
    def _base_fixture():
        teams = [f"Team {number:02d}" for number in range(1, 49)]
        group_rows = []
        for index, team in enumerate(teams):
            group_rows.append(
                {
                    "team": team,
                    "group": chr(65 + index // 4),
                    "position": index % 4 + 1,
                }
            )
        tables = pd.DataFrame(group_rows)
        qualified = []
        for group in "ABCDEFGHIJKL":
            group_teams = tables.loc[
                tables["group"] == group
            ].sort_values("position")
            qualified.extend(group_teams.iloc[:2]["team"].tolist())
        qualified.extend(
            tables.loc[tables["position"] == 3, "team"].iloc[:8].tolist()
        )

        bracket_rows = []
        match_rows = []
        for offset in range(16):
            home = qualified[2 * offset]
            away = qualified[2 * offset + 1]
            api_id = 1000 + offset
            bracket_rows.append(
                {
                    "bracket_match_number": 73 + offset,
                    "api_match_id": api_id,
                    "utc_date": "2026-06-28T12:00:00Z",
                    "status": "TIMED",
                    "home_team": home,
                    "away_team": away,
                    "home_source_slot": "x",
                    "away_source_slot": "y",
                    "fixture_status": "confirmed",
                    "bracket_mode": "official_api_locked",
                }
            )
            match_rows.append(
                {
                    "match_id": api_id,
                    "utc_date": (
                        pd.Timestamp("2026-06-28", tz="UTC")
                        + pd.Timedelta(hours=offset)
                    ),
                    "status": "TIMED",
                    "stage": "LAST_32",
                    "home_team": home,
                    "away_team": away,
                    "winner": None,
                    "duration": None,
                    "home_score_full_time": np.nan,
                    "away_score_full_time": np.nan,
                    "home_score_penalties": np.nan,
                    "away_score_penalties": np.nan,
                }
            )
        matches = pd.DataFrame(match_rows)
        bracket = pd.DataFrame(bracket_rows)
        team_map = pd.DataFrame(
            {
                "live_team_name": teams,
                "historical_team_name": teams,
            }
        )
        elo = pd.DataFrame(
            {
                "team": teams,
                "elo_rating": np.linspace(1800, 1400, 48),
                "rank": range(1, 49),
            }
        )
        state = pd.DataFrame(
            {
                "team": teams,
                "matches": [3] * 48,
                "ema_goals_for": [1.25] * 48,
                "ema_goals_against": [1.25] * 48,
                "ema_points": [1.5] * 48,
                "last_date": [pd.NaT] * 48,
            }
        )
        return matches, bracket, tables, team_map, elo, state


if __name__ == "__main__":
    unittest.main()
