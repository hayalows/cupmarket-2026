from __future__ import annotations

import unittest

import pandas as pd

from features.live_group_table import build_live_group_table
from features.live_match_data import (
    ACTIVE_REFRESH_SECONDS,
    IDLE_REFRESH_SECONDS,
    expected_live_matches,
    group_freshness,
    parse_api_matches,
    recommended_refresh_seconds,
)
from features.live_match_reconciliation import (
    mark_impossible_live_states,
    merge_terminal_states,
)


class LiveMatchDataTests(unittest.TestCase):
    def test_parse_api_matches(self):
        payload = {
            "matches": [
                {
                    "id": 11,
                    "utcDate": "2026-06-20T18:00:00Z",
                    "status": "FINISHED",
                    "stage": "GROUP_STAGE",
                    "group": "GROUP_A",
                    "matchday": 2,
                    "homeTeam": {"name": "Ghana"},
                    "awayTeam": {"name": "Panama"},
                    "score": {
                        "winner": "HOME_TEAM",
                        "duration": "REGULAR",
                        "fullTime": {"home": 2, "away": 1},
                    },
                    "lastUpdated": "2026-06-20T20:00:00Z",
                }
            ]
        }
        frame = parse_api_matches(payload)
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["home_team"], "Ghana")
        self.assertEqual(frame.iloc[0]["away_team"], "Panama")
        self.assertEqual(frame.iloc[0]["home_score_full_time"], 2)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(frame["utc_date"]))

    def test_parse_live_match_keeps_clock_and_current_score(self):
        payload = {
            "matches": [
                {
                    "id": 12,
                    "utcDate": "2026-06-20T18:00:00Z",
                    "status": "IN_PLAY",
                    "stage": "GROUP_STAGE",
                    "group": "GROUP_A",
                    "matchday": 2,
                    "minute": 37,
                    "injuryTime": 0,
                    "homeTeam": {"name": "Ghana"},
                    "awayTeam": {"name": "Panama"},
                    "score": {
                        "winner": "HOME_TEAM",
                        "duration": "REGULAR",
                        "fullTime": {"home": 1, "away": 0},
                    },
                    "lastUpdated": "2026-06-20T18:37:00Z",
                }
            ]
        }
        frame = parse_api_matches(payload)
        self.assertEqual(frame.iloc[0]["status"], "IN_PLAY")
        self.assertEqual(int(frame.iloc[0]["minute"]), 37)
        self.assertEqual(int(frame.iloc[0]["home_score_full_time"]), 1)
        self.assertEqual(int(frame.iloc[0]["away_score_full_time"]), 0)

    def test_expected_live_match_detects_scheduled_fixture_after_kickoff(self):
        now = pd.Timestamp("2026-06-20T18:30:00Z")
        matches = pd.DataFrame(
            [
                {
                    "utc_date": pd.Timestamp("2026-06-20T18:00:00Z"),
                    "status": "TIMED",
                },
                {
                    "utc_date": pd.Timestamp("2026-06-21T18:00:00Z"),
                    "status": "TIMED",
                },
            ]
        )
        expected = expected_live_matches(matches, now=now)
        self.assertEqual(len(expected), 1)

    def test_impossible_live_status_is_quarantined(self):
        matches = pd.DataFrame(
            [
                {
                    "match_id": 1,
                    "utc_date": pd.Timestamp("2026-06-14T23:00:00Z"),
                    "status": "IN_PLAY",
                    "home_team": "Ivory Coast",
                    "away_team": "Ecuador",
                },
                {
                    "match_id": 2,
                    "utc_date": pd.Timestamp("2026-06-15T02:00:00Z"),
                    "status": "FINISHED",
                    "home_team": "Sweden",
                    "away_team": "Tunisia",
                },
            ]
        )
        reconciled, stale = mark_impossible_live_states(
            matches,
            now=pd.Timestamp("2026-06-15T06:00:00Z"),
        )
        self.assertEqual(reconciled.iloc[0]["status"], "AWAITING_CONFIRMATION")
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["match_id"], 1)

    def test_genuine_live_match_is_not_quarantined(self):
        matches = pd.DataFrame(
            [
                {
                    "match_id": 1,
                    "utc_date": pd.Timestamp("2026-06-20T18:00:00Z"),
                    "status": "IN_PLAY",
                    "home_team": "Ghana",
                    "away_team": "Panama",
                }
            ]
        )
        reconciled, stale = mark_impossible_live_states(
            matches,
            now=pd.Timestamp("2026-06-20T18:45:00Z"),
        )
        self.assertEqual(reconciled.iloc[0]["status"], "IN_PLAY")
        self.assertEqual(stale, [])

    def test_finished_snapshot_overrides_regressed_provider_status(self):
        provider = pd.DataFrame(
            [
                {
                    "match_id": 537352,
                    "status": "IN_PLAY",
                    "home_score_full_time": 1,
                    "away_score_full_time": 0,
                    "last_updated": pd.Timestamp("2026-06-15T01:00:00Z"),
                }
            ]
        )
        snapshot = pd.DataFrame(
            [
                {
                    "match_id": 537352,
                    "status": "FINISHED",
                    "winner": "HOME_TEAM",
                    "duration": "REGULAR",
                    "home_score_full_time": 1,
                    "away_score_full_time": 0,
                    "last_updated": pd.Timestamp("2026-06-15T01:09:24Z"),
                }
            ]
        )
        merged, report = merge_terminal_states(provider, snapshot)
        self.assertEqual(merged.iloc[0]["status"], "FINISHED")
        self.assertEqual(report.restored_match_ids, (537352,))

    def test_newer_official_terminal_correction_is_applied(self):
        current = pd.DataFrame(
            [
                {
                    "match_id": 1,
                    "status": "FINISHED",
                    "winner": "HOME_TEAM",
                    "duration": "REGULAR",
                    "home_score_full_time": 1,
                    "away_score_full_time": 0,
                    "last_updated": pd.Timestamp("2026-06-20T20:00:00Z"),
                }
            ]
        )
        corrected = pd.DataFrame(
            [
                {
                    "match_id": 1,
                    "status": "FINISHED",
                    "winner": "DRAW",
                    "duration": "REGULAR",
                    "home_score_full_time": 1,
                    "away_score_full_time": 1,
                    "last_updated": pd.Timestamp("2026-06-20T20:05:00Z"),
                }
            ]
        )
        merged, report = merge_terminal_states(current, corrected)
        self.assertEqual(int(merged.iloc[0]["away_score_full_time"]), 1)
        self.assertEqual(merged.iloc[0]["winner"], "DRAW")
        self.assertEqual(report.corrected_match_ids, (1,))

    def test_older_terminal_record_does_not_overwrite_newer_result(self):
        current = pd.DataFrame(
            [
                {
                    "match_id": 1,
                    "status": "FINISHED",
                    "winner": "DRAW",
                    "duration": "REGULAR",
                    "home_score_full_time": 1,
                    "away_score_full_time": 1,
                    "last_updated": pd.Timestamp("2026-06-20T20:10:00Z"),
                }
            ]
        )
        older = pd.DataFrame(
            [
                {
                    "match_id": 1,
                    "status": "FINISHED",
                    "winner": "HOME_TEAM",
                    "duration": "REGULAR",
                    "home_score_full_time": 1,
                    "away_score_full_time": 0,
                    "last_updated": pd.Timestamp("2026-06-20T20:05:00Z"),
                }
            ]
        )
        merged, report = merge_terminal_states(current, older)
        self.assertEqual(int(merged.iloc[0]["away_score_full_time"]), 1)
        self.assertEqual(report.corrected_match_ids, ())

    def test_refresh_rate_is_fast_only_during_match_activity(self):
        live = pd.DataFrame([{"status": "IN_PLAY", "utc_date": pd.Timestamp.now(tz="UTC")}])
        finished = pd.DataFrame([{"status": "FINISHED", "utc_date": pd.Timestamp.now(tz="UTC")}])
        self.assertEqual(recommended_refresh_seconds(live), ACTIVE_REFRESH_SECONDS)
        self.assertEqual(recommended_refresh_seconds(finished), IDLE_REFRESH_SECONDS)

    def test_group_freshness_detects_pending_result(self):
        matches = pd.DataFrame(
            [
                {"stage": "GROUP_STAGE", "status": "FINISHED"},
                {"stage": "GROUP_STAGE", "status": "FINISHED"},
                {"stage": "GROUP_STAGE", "status": "TIMED"},
            ]
        )
        freshness = group_freshness(matches, {"finished_group_matches": 1})
        self.assertEqual(freshness["live_finished_group_matches"], 2)
        self.assertEqual(freshness["model_finished_group_matches"], 1)
        self.assertEqual(freshness["pending_model_updates"], 1)

    def test_live_group_table_uses_current_scores(self):
        fixtures = [
            (1, "Ghana", "Panama", "FINISHED", 2, 0),
            (2, "Japan", "Sweden", "FINISHED", 1, 1),
            (3, "Ghana", "Japan", "TIMED", None, None),
            (4, "Panama", "Sweden", "TIMED", None, None),
            (5, "Ghana", "Sweden", "TIMED", None, None),
            (6, "Panama", "Japan", "TIMED", None, None),
        ]
        matches = pd.DataFrame(
            [
                {
                    "match_id": match_id,
                    "utc_date": pd.Timestamp("2026-06-20", tz="UTC")
                    + pd.Timedelta(days=match_id),
                    "status": status,
                    "stage": "GROUP_STAGE",
                    "group": "GROUP_A",
                    "home_team": home,
                    "away_team": away,
                    "home_score_full_time": home_score,
                    "away_score_full_time": away_score,
                }
                for match_id, home, away, status, home_score, away_score in fixtures
            ]
        )
        table = build_live_group_table(
            matches,
            "A",
            {"Ghana": 100, "Japan": 90, "Sweden": 80, "Panama": 70},
        )
        self.assertEqual(table.iloc[0]["team"], "Ghana")
        self.assertEqual(int(table.iloc[0]["points"]), 3)
        self.assertEqual(int(table.iloc[0]["goal_difference"]), 2)


if __name__ == "__main__":
    unittest.main()
