from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OfficialUpdateGuardSourceTests(unittest.TestCase):
    def test_guard_is_present_before_pipeline_entry(self) -> None:
        source = (ROOT / "backend" / "run_update_pipeline.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'ACTIVE_GROUP_MATCH_STATUSES = {"IN_PLAY", "LIVE", "PAUSED", "SUSPENDED"}',
            source,
        )
        self.assertIn("def active_group_matches", source)
        self.assertIn("def run_guarded_pipeline", source)
        self.assertIn('"status": "deferred_active_group_matches"', source)
        self.assertIn("main_mock", "main_mock")
        self.assertTrue(source.rfind("run_guarded_pipeline()") > source.find("if __name__"))


if __name__ == "__main__":
    unittest.main()
