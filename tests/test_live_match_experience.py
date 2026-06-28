from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from features import live_match_experience as experience


class LiveMatchExperienceTests(unittest.TestCase):
    def test_group_text_hides_missing_values(self):
        self.assertEqual(experience._group_text(np.nan), "")
        self.assertEqual(experience._group_text(""), "")
        self.assertEqual(experience._group_text("nan"), "")
        self.assertEqual(experience._group_text("GROUP_A"), "Group A")

    def test_missing_round_of_32_group_uses_stage_text(self):
        self.assertEqual(
            experience._group_text(np.nan, stage="LAST_32"),
            "Round of 32",
        )

    def test_match_context_uses_stage_for_knockout_rows(self):
        knockout = pd.Series({"stage": "LAST_32", "group": "GROUP_A"})
        group = pd.Series({"stage": "GROUP_STAGE", "group": "GROUP_A"})
        unknown = pd.Series({"stage": None, "group": np.nan})

        self.assertEqual(experience._match_context_text(knockout), "Round of 32")
        self.assertEqual(experience._match_context_text(group), "Group A")
        self.assertEqual(experience._match_context_text(unknown), "")


if __name__ == "__main__":
    unittest.main()
