from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NavigationContractTest(unittest.TestCase):
    def test_navigation_uses_supported_icons_and_single_menu(self):
        app_text = (ROOT / "app.py").read_text(encoding="utf-8")
        product_ui_text = (ROOT / "features" / "product_ui.py").read_text(encoding="utf-8")
        config_text = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")

        combined = app_text + product_ui_text
        self.assertNotIn('icon="◇"', combined)
        self.assertNotIn('icon="◉"', combined)
        self.assertNotIn("disabled=active_page", product_ui_text)
        self.assertIn("showSidebarNavigation = false", config_text)

        for sidebar_text in (app_text, product_ui_text):
            self.assertIn('with st.expander("Tools", expanded=False):', sidebar_text)
            for label in [
                "Overview", "Countries", "Matches", "Bracket",
                "Simulator", "Analysis", "System Health", "Archive",
            ]:
                self.assertIn(f'label="{label}"', sidebar_text)
        self.assertIn('initial_sidebar_state="auto"', app_text)


if __name__ == "__main__":
    unittest.main()
