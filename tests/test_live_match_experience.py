from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from features import live_match_experience as experience
from features.live_match_room import (
    _advance_consequence,
    _current_score_caption,
    _live_meta_text,
)
from features.match_ui import clean_text, match_stage_label


class LiveMatchExperienceTests(unittest.TestCase):
    def test_clean_text_hides_missing_values(self):
        self.assertEqual(clean_text(np.nan), "")
        self.assertEqual(clean_text(""), "")
        self.assertEqual(clean_text("nan"), "")
        self.assertEqual(clean_text("None"), "")

    def test_match_stage_label_uses_group_for_group_stage_rows(self):
        self.assertEqual(
            match_stage_label(pd.Series({"stage": "GROUP_STAGE", "group": "GROUP_A"})),
            "Group A",
        )

    def test_match_stage_label_uses_stage_for_knockout_rows(self):
        cases = {
            "LAST_32": "Round of 32",
            "LAST_16": "Round of 16",
            "QUARTER_FINALS": "Quarter-final",
            "QUARTER_FINAL": "Quarter-final",
            "SEMI_FINALS": "Semi-final",
            "SEMI_FINAL": "Semi-final",
            "FINAL": "Final",
        }
        for stage, label in cases.items():
            with self.subTest(stage=stage):
                row = pd.Series({"stage": stage, "group": np.nan})
                self.assertEqual(match_stage_label(row), label)

    def test_match_context_uses_stage_for_knockout_rows(self):
        knockout = pd.Series({"stage": "LAST_32", "group": "GROUP_A"})
        group = pd.Series({"stage": "GROUP_STAGE", "group": "GROUP_A"})
        unknown = pd.Series({"stage": None, "group": np.nan})

        self.assertEqual(experience._match_context_text(knockout), "Round of 32")
        self.assertEqual(experience._match_context_text(group), "Group A")
        self.assertEqual(experience._match_context_text(unknown), "")

    def test_live_meta_text_uses_knockout_stage_without_group(self):
        match = pd.Series(
            {
                "status": "IN_PLAY",
                "minute": np.nan,
                "stage": "LAST_32",
                "group": np.nan,
            }
        )

        self.assertEqual(_live_meta_text(match), "LIVE · Round of 32")


    def test_current_score_caption_uses_clock_source(self):
        self.assertEqual(
            _current_score_caption(
                {
                    "current_score": "0-0",
                    "minute": 20,
                    "minute_source": "kickoff_inferred",
                }
            ),
            "Current score: 0-0 after about 20 minutes.",
        )
        self.assertEqual(
            _current_score_caption(
                {
                    "current_score": "0-0",
                    "minute": 20,
                    "minute_source": "api",
                }
            ),
            "Current score: 0-0 after 20 minutes.",
        )
        unavailable = _current_score_caption(
            {
                "current_score": "0-0",
                "minute": 0,
                "minute_source": "unavailable",
            }
        )
        self.assertNotIn("0 minutes", unavailable)
        self.assertIn("minute unavailable", unavailable)

    def test_knockout_consequence_uses_connected_bracket_slot(self):
        progress = pd.DataFrame(
            [
                {
                    "logical_match_number": 73,
                    "api_match_id": 537417,
                    "stage": "LAST_32",
                    "home_team": "South Africa",
                    "away_team": "Canada",
                    "advancing_team": np.nan,
                },
                {
                    "logical_match_number": 75,
                    "api_match_id": 537415,
                    "stage": "LAST_32",
                    "home_team": "Germany",
                    "away_team": "Paraguay",
                    "advancing_team": np.nan,
                },
                {
                    "logical_match_number": 90,
                    "api_match_id": 537375,
                    "stage": "LAST_16",
                    "home_team": np.nan,
                    "away_team": np.nan,
                    "advancing_team": np.nan,
                },
            ]
        )
        consequence = _advance_consequence(
            pd.Series(
                {
                    "match_id": 537417,
                    "stage": "LAST_32",
                }
            ),
            progress,
        )

        self.assertEqual(consequence["destination"], "Round of 16")
        self.assertEqual(consequence["target_match"], 90)
        self.assertEqual(consequence["opponent_label"], "Germany/Paraguay winner")


if __name__ == "__main__":
    unittest.main()
