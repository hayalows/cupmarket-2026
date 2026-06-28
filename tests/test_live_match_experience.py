from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from features import live_match_experience as experience
from features.live_match_room import _live_meta_text
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


if __name__ == "__main__":
    unittest.main()
