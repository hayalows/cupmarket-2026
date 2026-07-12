from __future__ import annotations

from html import escape
import re
from urllib.parse import urlencode

import pandas as pd
import streamlit as st

from features.bracket_tree import bracket_html
from features.clickable_bracket import _match_links


def _strip_outer_document(html: str) -> str:
    """Return an embeddable Streamlit HTML fragment instead of a full document."""

    html = re.sub(r"<!doctype[^>]*>", "", html, flags=re.IGNORECASE)
    html = re.sub(
        r"</?(?:html|head|body)\b[^>]*>",
        "",
        html,
        flags=re.IGNORECASE,
    )
    return html.strip()


def native_clickable_bracket_html(source: pd.DataFrame) -> str:
    """Build the visual bracket with real links in Streamlit's main document.

    The previous versions placed the bracket inside ``components.html``. That iframe
    could display the cards correctly but mobile browsers did not consistently follow
    links created inside it. Rendering the same bracket as ordinary Streamlit HTML keeps
    each full-card anchor in the app page itself, so taps are handled by the browser
    without iframe navigation or JavaScript.
    """

    html = bracket_html(source)
    links = _match_links(source)

    native_css = """
<style>
.match-card:has(.cm-native-match-link) {
  cursor: pointer;
  touch-action: manipulation;
  -webkit-tap-highlight-color: rgba(124, 131, 255, .24);
  transition: transform 150ms ease, border-color 150ms ease, box-shadow 150ms ease;
}
.match-card:has(.cm-native-match-link):hover,
.match-card:has(.cm-native-match-link):focus-within,
.match-card:has(.cm-native-match-link):active {
  transform: translateY(-3px);
  border-color: rgba(124, 131, 255, .95);
  box-shadow: 0 0 0 3px rgba(124, 131, 255, .14), 0 18px 36px rgba(0, 0, 0, .30);
}
.cm-native-match-link {
  position: absolute;
  inset: 0;
  z-index: 50;
  display: block;
  border-radius: inherit;
  text-decoration: none !important;
  color: transparent !important;
  background: transparent;
  touch-action: manipulation;
  -webkit-tap-highlight-color: rgba(124, 131, 255, .24);
}
.cm-native-match-link:focus-visible {
  outline: 3px solid rgba(185, 190, 255, .96);
  outline-offset: -3px;
}
.cm-native-match-link .cm-tap-hint {
  position: absolute;
  right: 7px;
  bottom: 4px;
  color: #b9beff;
  font-size: 8px;
  font-weight: 850;
  letter-spacing: .06em;
  line-height: 1;
  text-transform: uppercase;
  opacity: 0;
}
.match-card:has(.cm-native-match-link):hover .cm-tap-hint,
.match-card:has(.cm-native-match-link):focus-within .cm-tap-hint,
.match-card:has(.cm-native-match-link):active .cm-tap-hint {
  opacity: 1;
}
@media (hover: none) and (pointer: coarse) {
  .match-card:has(.cm-native-match-link) {
    border-color: rgba(124, 131, 255, .52);
  }
  .cm-native-match-link .cm-tap-hint {
    opacity: 1;
  }
}
</style>
"""

    for number, target in links.items():
        if not target.get("clickable") or not target.get("match_id"):
            continue

        params = urlencode(
            {
                "open_match_view": target.get("view") or "Upcoming",
                "open_match_id": str(target["match_id"]),
            }
        )
        href = f"?{params}"
        description = (
            target.get("result_label")
            or target.get("decision_status")
            or "Open match details"
        )
        aria_label = f"{target.get('label') or f'Open match {number}'}. {description}"
        anchor = (
            f'<a class="cm-native-match-link" '
            f'href="{escape(href, quote=True)}" target="_self" '
            f'aria-label="{escape(aria_label, quote=True)}" '
            f'title="{escape(description, quote=True)}">'
            '<span class="cm-tap-hint" aria-hidden="true">Open</span>'
            "</a>"
        )

        pattern = re.compile(
            rf'(<article\b[^>]*aria-label="[^"]* match {re.escape(str(number))}"[^>]*>)'
            r"(.*?)"
            r"(</article>)",
            flags=re.DOTALL,
        )
        html = pattern.sub(
            lambda match: f"{match.group(1)}{match.group(2)}{anchor}{match.group(3)}",
            html,
            count=1,
        )

    html = html.replace(
        "Swipe or scroll sideways to inspect every round",
        "Tap a match for details. Swipe sideways to inspect every round",
        1,
    )
    html = html.replace("</head>", f"{native_css}</head>", 1)
    return _strip_outer_document(html)


def render_bracket_tree(source: pd.DataFrame) -> None:
    st.markdown(native_clickable_bracket_html(source), unsafe_allow_html=True)
