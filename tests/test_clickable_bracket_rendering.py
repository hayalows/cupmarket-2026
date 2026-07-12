import unittest
from unittest.mock import patch

import pandas as pd

from features.mobile_bracket_stage import _render_official_match
from features.reliable_clickable_bracket import (
    native_clickable_bracket_html,
    render_bracket_tree,
)


class ClickableBracketRenderingTests(unittest.TestCase):
    def setUp(self):
        self.source = pd.DataFrame(
            [
                {
                    "logical_match_number": 73,
                    "api_match_id": 537417,
                    "stage": "LAST_32",
                    "status": "FINISHED",
                    "home_team": "South Africa",
                    "away_team": "Canada",
                    "home_score": 0,
                    "away_score": 1,
                    "advancing_team": "Canada",
                    "decision_method": "regular_time",
                }
            ]
        )

    def test_full_bracket_uses_a_canonical_match_hub_link(self):
        html = native_clickable_bracket_html(self.source)

        self.assertIn(
            'href="/Match_Hub?view=Results&amp;match_id=537417"',
            html,
        )
        self.assertEqual(html.count('<a class="cm-native-match-link"'), 1)
        self.assertNotIn("open_match_id", html)

    @patch("features.reliable_clickable_bracket.st.html")
    def test_full_bracket_is_rendered_as_html_not_markdown(self, html_mock):
        render_bracket_tree(self.source)

        html_mock.assert_called_once()
        self.assertIn("<article", html_mock.call_args.args[0])

    @patch("features.mobile_bracket_stage.st.html")
    def test_mobile_card_is_one_full_card_link(self, html_mock):
        _render_official_match(self.source.iloc[0], "Round of 32", 73)

        html_mock.assert_called_once()
        card = html_mock.call_args.args[0]
        self.assertTrue(card.startswith('<a class="cm-mobile-bracket-card'))
        self.assertIn('href="/Match_Hub?view=Results&amp;match_id=537417"', card)
        self.assertTrue(card.endswith("</a>"))


if __name__ == "__main__":
    unittest.main()
