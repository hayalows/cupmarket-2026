from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

import pandas as pd

from backend.bracket_lock_execution import lock_official_bracket_from_matches
from backend.bracket_lock_store import BracketLockError, build_official_bracket


class ExactBracketLockTests(unittest.TestCase):
    def test_waits_until_all_group_matches_are_finished(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            matches, tables = self._fixture()
            matches.loc[0, "status"] = "TIMED"
            self._write_tables(root, tables)

            result = lock_official_bracket_from_matches(root, matches)

            self.assertEqual(result["status"], "waiting_for_group_stage_completion")
            self.assertFalse(
                (root / "data" / "official_round_32_bracket_locked.csv").exists()
            )

    def test_waits_for_all_official_round_32_teams(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            matches, tables = self._fixture()
            matches.loc[matches["stage"] == "LAST_32", "away_team"] = "TBD"
            self._write_tables(root, tables)

            result = lock_official_bracket_from_matches(root, matches)

            self.assertEqual(result["status"], "waiting_for_official_round_32_teams")

    def test_locks_exact_fixtures_and_replaces_projections(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            matches, tables = self._fixture()
            self._write_tables(root, tables)

            result = lock_official_bracket_from_matches(root, matches)

            self.assertEqual(result["status"], "locked")
            data = root / "data"
            bracket = pd.read_csv(data / "official_round_32_bracket_locked.csv")
            opponents = pd.read_csv(
                data / "round_32_opponent_probabilities_latest.csv"
            )
            paths = pd.read_csv(data / "round_32_path_status_latest.csv")
            state = json.loads(
                (data / "official_round_32_bracket_lock.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(len(bracket), 16)
            self.assertEqual(
                len(set(bracket["home_team"]).union(bracket["away_team"])), 32
            )
            self.assertEqual(set(bracket["fixture_status"]), {"confirmed"})
            self.assertEqual(set(bracket["bracket_mode"]), {"official_api_locked"})
            self.assertEqual(len(opponents), 32)
            self.assertTrue((opponents["probability_unconditional"] == 1.0).all())
            self.assertEqual(len(paths), 48)
            self.assertEqual(
                int((paths["fixture_status"] == "confirmed").sum()), 32
            )
            self.assertEqual(
                int((paths["fixture_status"] == "eliminated").sum()), 16
            )
            self.assertEqual(state["status"], "locked")
            self.assertEqual(state["fingerprint"], result["fingerprint"])

    def test_repeating_same_lock_is_idempotent(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            matches, tables = self._fixture()
            self._write_tables(root, tables)

            first = lock_official_bracket_from_matches(root, matches)
            second = lock_official_bracket_from_matches(root, matches)

            self.assertEqual(first["status"], "locked")
            self.assertEqual(second["status"], "already_locked")
            self.assertEqual(first["fingerprint"], second["fingerprint"])

    def test_existing_lock_tolerates_status_and_schedule_drift(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            matches, tables = self._fixture()
            self._write_tables(root, tables)

            lock_official_bracket_from_matches(root, matches)
            data = root / "data"
            original_lock = pd.read_csv(data / "official_round_32_bracket_locked.csv")
            first_fixture = original_lock.iloc[0]

            knockout = matches.index[matches["stage"] == "LAST_32"].tolist()
            for offset, row_index in enumerate(knockout):
                matches.loc[row_index, "status"] = "FINISHED"
                matches.loc[row_index, "utc_date"] = (
                    f"2026-07-{16 - offset:02d}T20:00:00Z"
                )

            result = lock_official_bracket_from_matches(root, matches)

            self.assertEqual(result["status"], "already_locked")
            repeated_lock = pd.read_csv(data / "official_round_32_bracket_locked.csv")
            pd.testing.assert_frame_equal(original_lock, repeated_lock)

            paths = pd.read_csv(data / "round_32_path_status_latest.csv")
            first_home_path = paths.loc[
                paths["team"] == first_fixture["home_team"]
            ].iloc[0]
            self.assertEqual(
                int(first_home_path["round_32_match_id"]),
                int(first_fixture["bracket_match_number"]),
            )

    def test_conflicting_fixture_cannot_rewrite_existing_lock(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            matches, tables = self._fixture()
            self._write_tables(root, tables)
            lock_official_bracket_from_matches(root, matches)

            knockout = matches.index[matches["stage"] == "LAST_32"].tolist()
            first, second = knockout[0], knockout[1]
            matches.loc[first, "away_team"], matches.loc[second, "away_team"] = (
                matches.loc[second, "away_team"],
                matches.loc[first, "away_team"],
            )

            with self.assertRaisesRegex(BracketLockError, "immutable lock"):
                lock_official_bracket_from_matches(root, matches)

    def test_builder_rejects_duplicate_knockout_team(self):
        matches, tables = self._fixture()
        knockout = matches.index[matches["stage"] == "LAST_32"].tolist()
        matches.loc[knockout[1], "home_team"] = matches.loc[
            knockout[0], "home_team"
        ]

        with self.assertRaisesRegex(BracketLockError, "32 unique teams"):
            build_official_bracket(matches, tables)

    @staticmethod
    def _write_tables(root: Path, tables: pd.DataFrame) -> None:
        data = root / "data"
        data.mkdir(parents=True)
        tables.to_csv(data / "current_group_tables.csv", index=False)

    @staticmethod
    def _fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
        group_rows = []
        match_rows = []
        match_id = 1
        winners = []
        runners_up = []
        third_teams = []

        for group_index, group in enumerate("ABCDEFGHIJKL"):
            teams = [f"{group}{position}" for position in range(1, 5)]
            winners.append(teams[0])
            runners_up.append(teams[1])
            third_teams.append(teams[2])
            for position, team in enumerate(teams, start=1):
                group_rows.append(
                    {
                        "group": group,
                        "position": position,
                        "team": team,
                        "played": 3,
                        "wins": max(0, 4 - position),
                        "draws": 0,
                        "losses": position - 1,
                        "goals_for": 5 - position,
                        "goals_against": position - 1,
                        "goal_difference": 6 - 2 * position,
                        "points": 3 * max(0, 4 - position),
                    }
                )

            fixtures = [
                (teams[0], teams[1]),
                (teams[2], teams[3]),
                (teams[0], teams[2]),
                (teams[1], teams[3]),
                (teams[0], teams[3]),
                (teams[1], teams[2]),
            ]
            for home, away in fixtures:
                match_rows.append(
                    {
                        "match_id": match_id,
                        "utc_date": f"2026-06-{11 + group_index:02d}T12:00:00Z",
                        "status": "FINISHED",
                        "stage": "GROUP_STAGE",
                        "group": f"GROUP_{group}",
                        "matchday": 3,
                        "home_team": home,
                        "away_team": away,
                        "home_score_full_time": 1,
                        "away_score_full_time": 0,
                    }
                )
                match_id += 1

        qualified_thirds = third_teams[:8]
        qualified = winners + runners_up + qualified_thirds
        pairings = [(qualified[index], qualified[index + 1]) for index in range(0, 32, 2)]
        for offset, (home, away) in enumerate(pairings):
            match_rows.append(
                {
                    "match_id": 1000 + offset,
                    "utc_date": f"2026-06-{28 + offset // 4:02d}T{12 + offset % 4:02d}:00:00Z",
                    "status": "TIMED",
                    "stage": "LAST_32",
                    "group": None,
                    "matchday": None,
                    "home_team": home,
                    "away_team": away,
                    "home_score_full_time": None,
                    "away_score_full_time": None,
                }
            )

        return pd.DataFrame(match_rows), pd.DataFrame(group_rows)


if __name__ == "__main__":
    unittest.main()
