from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class NavigationContractTest(unittest.TestCase):
    def test_navigation_uses_supported_icons_and_single_menu(self):
        app_text = (ROOT / "app.py").read_text(encoding="utf-8")
        product_ui_text = (ROOT / "features" / "product_ui.py").read_text(encoding="utf-8")
        patch_text = (ROOT / "scripts" / "apply_product_experience_refresh.py").read_text(encoding="utf-8")
        config_text = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")

        combined = app_text + product_ui_text + patch_text
        self.assertNotIn('icon="◇"', combined)
        self.assertNotIn('icon="◉"', combined)
        self.assertNotIn("disabled=active_page", product_ui_text)
        self.assertIn("showSidebarNavigation = false", config_text)
        for sidebar_text in (app_text, product_ui_text):
            self.assertIn('with st.expander("More", expanded=False):', sidebar_text)
            self.assertIn('label="Analysis Lab"', sidebar_text)
            self.assertNotIn('label="Live Match Room"', sidebar_text)
            self.assertNotIn('label="Market Story"', sidebar_text)
            self.assertNotIn('label="Group Archive"', sidebar_text)
            self.assertNotIn('label="Group Centre"', sidebar_text)
            self.assertNotIn('label="Guide"', sidebar_text)
        self.assertIn('initial_sidebar_state="auto"', app_text)


if __name__ == "__main__":
    unittest.main()
