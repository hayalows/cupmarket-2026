from __future__ import annotations

from pathlib import Path
import unittest

from backend.output_contracts import (
    ContractViolation,
    OutputFrames,
    load_output_frames,
    validate_output_frames,
    validate_repository_outputs,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def cloned_frames() -> OutputFrames:
    frames = load_output_frames(REPO_ROOT)
    return OutputFrames(
        prices=frames.prices.copy(deep=True),
        probabilities=frames.probabilities.copy(deep=True),
        group_tables=frames.group_tables.copy(deep=True),
        matches=frames.matches.copy(deep=True),
    )


class PublishedOutputContractTests(unittest.TestCase):
    def test_current_repository_outputs_satisfy_contract(self):
        validate_repository_outputs(REPO_ROOT)

    def test_duplicate_match_ids_are_rejected(self):
        frames = cloned_frames()
        frames.matches.loc[1, "match_id"] = frames.matches.loc[0, "match_id"]
        with self.assertRaisesRegex(ContractViolation, "duplicate keys"):
            validate_output_frames(frames)

    def test_probability_outside_unit_interval_is_rejected(self):
        frames = cloned_frames()
        frames.probabilities.loc[0, "prob_champion"] = 1.2
        with self.assertRaisesRegex(ContractViolation, "outside \\[0, 1\\]"):
            validate_output_frames(frames)

    def test_broken_group_table_arithmetic_is_rejected(self):
        frames = cloned_frames()
        frames.group_tables.loc[0, "points"] = 99
        with self.assertRaisesRegex(ContractViolation, "points must equal"):
            validate_output_frames(frames)

    def test_missing_team_is_rejected(self):
        frames = cloned_frames()
        incomplete = OutputFrames(
            prices=frames.prices.iloc[:-1].copy(),
            probabilities=frames.probabilities,
            group_tables=frames.group_tables,
            matches=frames.matches,
        )
        with self.assertRaisesRegex(ContractViolation, "prices must contain 48 teams"):
            validate_output_frames(incomplete)


if __name__ == "__main__":
    unittest.main()
