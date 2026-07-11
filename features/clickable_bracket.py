from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit.components.v1 as components

from features.bracket_tree import bracket_html, build_bracket_matches


ACTIVE_STATUSES = {"IN_PLAY", "LIVE", "PAUSED", "SUSPENDED"}
FINISHED_STATUSES = {"FINISHED", "AWARDED"}


def _logical_match_number(row: pd.Series, fallback: int | None = None) -> int | None:
    for field in ("logical_match_number", "bracket_match_number", "match_number"):
        value = pd.to_numeric(row.get(field), errors="coerce")
        if pd.notna(value):
            return int(value)
    return fallback


def _api_match_id(row: pd.Series) -> int | None:
    for field in ("api_match_id", "match_id"):
        value = pd.to_numeric(row.get(field), errors="coerce")
        if pd.notna(value):
            return int(value)
    return None


def _target_view(status: str) -> str:
    normalised = str(status or "").upper()
    if normalised in ACTIVE_STATUSES:
        return "Live"
    if normalised in FINISHED_STATUSES:
        return "Results"
    return "Upcoming"


def _match_links(source: pd.DataFrame) -> dict[str, dict[str, Any]]:
    matches = build_bracket_matches(source)
    api_ids: dict[int, int] = {}

    if isinstance(source, pd.DataFrame) and not source.empty:
        for index, row in source.iterrows():
            fallback = int(index) if isinstance(index, int) else None
            number = _logical_match_number(row, fallback)
            api_id = _api_match_id(row)
            if number is not None and api_id is not None:
                api_ids[number] = api_id

    links: dict[str, dict[str, Any]] = {}
    for number, match in matches.items():
        api_id = api_ids.get(number)
        if api_id is None:
            continue
        links[str(number)] = {
            "match_id": api_id,
            "view": _target_view(match.status),
            "label": f"Open {match.stage} match {number}",
        }
    return links


def clickable_bracket_html(source: pd.DataFrame) -> str:
    html = bracket_html(source)
    payload = json.dumps(_match_links(source), separators=(",", ":")).replace("</", "<\\/")

    clickable_css = """
<style>
.match-card[data-clickable="true"] {
  cursor: pointer;
  transition: transform 150ms ease, border-color 150ms ease, box-shadow 150ms ease;
}
.match-card[data-clickable="true"]:hover,
.match-card[data-clickable="true"]:focus-visible {
  transform: translateY(-3px);
  border-color: rgba(124, 131, 255, .95);
  box-shadow: 0 0 0 3px rgba(124, 131, 255, .14), 0 18px 36px rgba(0, 0, 0, .30);
  outline: none;
}
.match-card[data-clickable="true"]::after {
  content: "Open";
  position: absolute;
  right: 8px;
  bottom: 5px;
  color: #b9beff;
  font-size: 8px;
  font-weight: 800;
  letter-spacing: .06em;
  text-transform: uppercase;
  opacity: 0;
  transition: opacity 150ms ease;
}
.match-card[data-clickable="true"]:hover::after,
.match-card[data-clickable="true"]:focus-visible::after {
  opacity: 1;
}
</style>
"""

    clickable_script = f"""
<script>
(() => {{
  const links = {payload};
  const cards = document.querySelectorAll('.match-card');
  const toolbarHint = document.querySelector('.bracket-toolbar span');
  if (toolbarHint) {{
    toolbarHint.textContent = 'Click a match for details. Swipe or scroll sideways to inspect every round.';
  }}

  const openMatch = (card) => {{
    const matchLabel = card.querySelector('.match-meta span:first-child');
    const number = matchLabel ? matchLabel.textContent.trim().replace(/^M/i, '') : '';
    const target = links[number];
    if (!target) return;
    const params = new URLSearchParams({{
      view: target.view,
      match_id: String(target.match_id),
    }});
    window.top.location.href = `/4_Match_Hub?${{params.toString()}}`;
  }};

  cards.forEach((card) => {{
    const matchLabel = card.querySelector('.match-meta span:first-child');
    const number = matchLabel ? matchLabel.textContent.trim().replace(/^M/i, '') : '';
    const target = links[number];
    if (!target) return;

    card.dataset.clickable = 'true';
    card.setAttribute('role', 'link');
    card.setAttribute('tabindex', '0');
    card.setAttribute('aria-label', target.label);
    card.setAttribute('title', 'Open match details');
    card.addEventListener('click', () => openMatch(card));
    card.addEventListener('keydown', (event) => {{
      if (event.key === 'Enter' || event.key === ' ') {{
        event.preventDefault();
        openMatch(card);
      }}
    }});
  }});
}})();
</script>
"""

    return html.replace("</head>", f"{clickable_css}</head>", 1).replace(
        "</body>", f"{clickable_script}</body>", 1
    )


def render_bracket_tree(source: pd.DataFrame) -> None:
    components.html(clickable_bracket_html(source), height=1285, scrolling=False)
