from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProductInformationArchitectureTests(unittest.TestCase):
    def test_overview_does_not_embed_the_full_simulator(self):
        text = (ROOT / "features" / "overview_v3.py").read_text(encoding="utf-8")
        self.assertNotIn("render_tournament_simulator", text)
        self.assertIn('["Current round", "Market", "Today"]', text)
        self.assertIn('st.tabs(["Fixtures", "Countries"])', text)
        self.assertNotIn('"Market signals"', text)

    def test_market_deep_links_open_country_market(self):
        text = (ROOT / "features" / "overview_v3.py").read_text(encoding="utf-8")
        self.assertIn("cupmarket_country_requested_section", text)
        self.assertNotIn('st.switch_page("pages/5_Market_Story.py")', text)

    def test_country_page_is_country_specific(self):
        text = (ROOT / "features" / "tournament_path_page.py").read_text(encoding="utf-8")
        active = text[text.index("def _render_country_page_v2") :]
        self.assertIn("st.segmented_control(", active)
        self.assertIn('["Overview", "Path", "Market", "Fixtures"]', active)
        self.assertNotIn("_render_tournament_forecast(data)", active)
        self.assertNotIn("_render_tournament_fixtures(data)", active)
        self.assertIn("This table contains only the selected country's fixtures.", active)

    def test_analysis_and_archive_have_distinct_jobs(self):
        analysis = (ROOT / "pages" / "11_Tournament_Insights.py").read_text(encoding="utf-8")
        archive = (ROOT / "pages" / "13_Tournament_Archive.py").read_text(encoding="utf-8")
        archive_feature = (ROOT / "features" / "tournament_archive.py").read_text(encoding="utf-8")
        self.assertIn("<h1>Model analysis</h1>", analysis)
        self.assertNotIn("Specialist tools", analysis)
        self.assertIn("Open Archive for the permanent tournament story", analysis)
        self.assertIn("<h1>Tournament archive</h1>", archive)
        self.assertIn('key="cupmarket_analysis_view"', analysis)
        self.assertNotIn("tabs = st.tabs", analysis)
        self.assertIn('key="cupmarket_archive_view"', archive_feature)
        self.assertNotIn("story_tab, market_tab", archive_feature)
        self.assertIn('"Group-stage record"', archive_feature)
        research = (ROOT / "features" / "tournament_insights.py").read_text(encoding="utf-8")
        self.assertNotIn("Group/R32 archive", research)

    def test_primary_headings_are_direct(self):
        expected = {
            ROOT / "features" / "tournament_pulse_page.py": "<h1>Tournament overview</h1>",
            ROOT / "features" / "match_hub_v2.py": "<h1>Matches and results</h1>",
            ROOT / "features" / "tournament_path_page.py": "<h1>Country profile</h1>",
            ROOT / "pages" / "8_Bracket_View.py": "<h1>Tournament bracket</h1>",
            ROOT / "pages" / "12_Tournament_Simulator.py": "<h1>Scenario simulator</h1>",
            ROOT / "pages" / "9_Model_Health.py": "<h1>System health</h1>",
        }
        for path, heading in expected.items():
            self.assertIn(heading, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
