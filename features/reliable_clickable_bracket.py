from __future__ import annotations

import json

import pandas as pd
import streamlit.components.v1 as components

from features.clickable_bracket import _match_links, clickable_bracket_html


def reliable_clickable_bracket_html(source: pd.DataFrame) -> str:
    """Add native link overlays that work inside Streamlit's component iframe.

    Streamlit renders ``components.html`` inside a sandboxed iframe. Direct attempts to
    change ``window.top.location`` can be blocked by that sandbox, especially on mobile
    browsers. A real anchor opened from a user tap is more reliable, so every official
    match card receives a full-card link overlay.
    """

    html = clickable_bracket_html(source)
    payload = json.dumps(_match_links(source), separators=(",", ":")).replace("</", "<\\/")

    overlay_css = """
<style>
.match-card .cm-match-link-overlay {
  position: absolute;
  inset: 0;
  z-index: 40;
  display: block;
  border-radius: inherit;
  text-decoration: none;
  color: transparent;
  background: transparent;
  touch-action: manipulation;
  -webkit-tap-highlight-color: rgba(124, 131, 255, .22);
}
.match-card .cm-match-link-overlay:focus-visible {
  outline: 3px solid rgba(185, 190, 255, .92);
  outline-offset: -3px;
}
.match-card[data-clickable="true"] {
  cursor: pointer;
}
@media (hover: none) and (pointer: coarse) {
  .match-card[data-clickable="true"]::after {
    content: "Tap";
    opacity: 1;
  }
}
</style>
"""

    overlay_script = f"""
<script>
(() => {{
  const links = {payload};
  const cards = document.querySelectorAll('.match-card');
  const toolbarHint = document.querySelector('.bracket-toolbar span');
  if (toolbarHint) {{
    toolbarHint.textContent = 'Tap a match to open its Match Hub page. Swipe sideways to inspect every round.';
  }}

  cards.forEach((card) => {{
    const matchLabel = card.querySelector('.match-meta span:first-child');
    const number = matchLabel ? matchLabel.textContent.trim().replace(/^M/i, '') : '';
    const target = links[number];
    if (!target || !target.clickable || !target.match_id) return;
    if (card.querySelector('.cm-match-link-overlay')) return;

    const params = new URLSearchParams({{
      view: target.view,
      match_id: String(target.match_id),
    }});
    const anchor = document.createElement('a');
    anchor.className = 'cm-match-link-overlay';
    anchor.href = `/4_Match_Hub?${{params.toString()}}`;
    anchor.target = '_blank';
    anchor.rel = 'noopener noreferrer';
    anchor.setAttribute(
      'aria-label',
      `${{target.label}}. ${{target.result_label || target.decision_status || ''}}`
    );
    anchor.setAttribute('title', target.result_label || 'Open match details');
    anchor.addEventListener('click', (event) => event.stopPropagation());
    anchor.addEventListener('keydown', (event) => event.stopPropagation());
    card.appendChild(anchor);
  }});
}})();
</script>
"""

    return html.replace("</head>", f"{overlay_css}</head>", 1).replace(
        "</body>", f"{overlay_script}</body>", 1
    )


def render_bracket_tree(source: pd.DataFrame) -> None:
    components.html(reliable_clickable_bracket_html(source), height=1285, scrolling=False)
