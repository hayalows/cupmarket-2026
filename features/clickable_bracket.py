from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit.components.v1 as components

from features.bracket_tree import bracket_html, build_bracket_matches

ACTIVE_STATUSES = {"IN_PLAY", "LIVE", "PAUSED", "SUSPENDED"}
FINISHED_STATUSES = {"FINISHED", "AWARDED"}


def _number(value: Any) -> int | None:
    parsed = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(parsed) else int(parsed)


def _logical_match_number(row: pd.Series, fallback: int | None = None) -> int | None:
    for field in ("logical_match_number", "bracket_match_number", "match_number"):
        value = _number(row.get(field))
        if value is not None:
            return value
    return fallback


def _api_match_id(row: pd.Series) -> int | None:
    for field in ("api_match_id", "match_id"):
        value = _number(row.get(field))
        if value is not None:
            return value
    return None


def _target_view(status: str) -> str:
    normalised = str(status or "").upper()
    if normalised in ACTIVE_STATUSES:
        return "Live"
    if normalised in FINISHED_STATUSES:
        return "Results"
    return "Upcoming"


def _source_rows(source: pd.DataFrame) -> dict[int, pd.Series]:
    rows: dict[int, pd.Series] = {}
    if not isinstance(source, pd.DataFrame) or source.empty:
        return rows
    for index, row in source.iterrows():
        fallback = int(index) if isinstance(index, int) else None
        number = _logical_match_number(row, fallback)
        if number is not None:
            rows[number] = row
    return rows


def _first_number(row: pd.Series, fields: tuple[str, ...]) -> int | None:
    for field in fields:
        value = _number(row.get(field))
        if value is not None:
            return value
    return None


def _decision_method(row: pd.Series, match) -> str:
    raw = str(
        row.get("decision_method")
        or getattr(match, "decision_method", "")
        or row.get("duration")
        or ""
    ).upper()
    home_penalties = _first_number(row, ("home_penalties", "home_score_penalties"))
    away_penalties = _first_number(row, ("away_penalties", "away_score_penalties"))
    if "PENALT" in raw or (home_penalties is not None and away_penalties is not None):
        return "penalties"
    if "EXTRA" in raw:
        return "extra_time"
    return "regular_time"


def _playing_score(row: pd.Series, match, method: str) -> tuple[int | None, int | None]:
    home = _number(getattr(match, "home_score", None))
    away = _number(getattr(match, "away_score", None))
    if method != "penalties":
        return home, away

    regular_home = _first_number(row, ("home_score_regular_time",))
    regular_away = _first_number(row, ("away_score_regular_time",))
    extra_home = _first_number(row, ("home_score_extra_time",))
    extra_away = _first_number(row, ("away_score_extra_time",))
    if regular_home is not None and regular_away is not None:
        return regular_home + (extra_home or 0), regular_away + (extra_away or 0)

    home_penalties = _first_number(row, ("home_penalties", "home_score_penalties"))
    away_penalties = _first_number(row, ("away_penalties", "away_score_penalties"))
    if None not in (home, away, home_penalties, away_penalties):
        candidate_home = int(home) - int(home_penalties)
        candidate_away = int(away) - int(away_penalties)
        if candidate_home >= 0 and candidate_away >= 0 and candidate_home == candidate_away:
            return candidate_home, candidate_away
    return home, away


def _decision_status(row: pd.Series, match, method: str) -> str:
    if not match.is_finished:
        return "Live" if match.is_live else ""
    if method == "penalties":
        home_penalties = _first_number(row, ("home_penalties", "home_score_penalties"))
        away_penalties = _first_number(row, ("away_penalties", "away_score_penalties"))
        if home_penalties is not None and away_penalties is not None:
            return f"Pens {home_penalties}–{away_penalties}"
        return "On penalties"
    if method == "extra_time":
        return "After extra time"
    return "Regular time"


def _result_label(row: pd.Series, match, method: str) -> str:
    winner = str(getattr(match, "advancing_team", "") or "").strip()
    if not match.is_finished or not winner or winner == "TBD":
        return ""
    if method == "penalties":
        return f"{winner} won on penalties"
    if method == "extra_time":
        return f"{winner} won after extra time"
    return f"{winner} won in regular time"


def _match_links(source: pd.DataFrame) -> dict[str, dict[str, Any]]:
    matches = build_bracket_matches(source)
    rows = _source_rows(source)
    links: dict[str, dict[str, Any]] = {}

    for number, match in matches.items():
        row = rows.get(number, pd.Series(dtype=object))
        api_id = _api_match_id(row)
        method = _decision_method(row, match)
        home_score, away_score = _playing_score(row, match, method)
        home_penalties = _first_number(row, ("home_penalties", "home_score_penalties"))
        away_penalties = _first_number(row, ("away_penalties", "away_score_penalties"))
        links[str(number)] = {
            "match_id": api_id,
            "view": _target_view(match.status),
            "clickable": api_id is not None,
            "label": f"Open {match.stage} match {number}",
            "decision": method,
            "decision_status": _decision_status(row, match, method),
            "result_label": _result_label(row, match, method),
            "home_score": home_score,
            "away_score": away_score,
            "home_penalties": home_penalties,
            "away_penalties": away_penalties,
        }
    return links


def clickable_bracket_html(source: pd.DataFrame) -> str:
    html = bracket_html(source)
    payload = json.dumps(_match_links(source), separators=(",", ":")).replace("</", "<\\/")

    clickable_css = """
<style>
.match-card[data-clickable="true"] {
  cursor: pointer;
  touch-action: manipulation;
  -webkit-tap-highlight-color: rgba(124, 131, 255, .22);
  transition: transform 150ms ease, border-color 150ms ease, box-shadow 150ms ease;
}
.match-card[data-clickable="true"]:hover,
.match-card[data-clickable="true"]:focus-visible,
.match-card[data-clickable="true"]:active {
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
.match-card[data-clickable="true"]:focus-visible::after,
.match-card[data-clickable="true"]:active::after {
  opacity: 1;
}
.match-card[data-decision="penalties"] .match-status { color: #d8b4fe; }
.match-card[data-decision="extra_time"] .match-status { color: #facc6b; }
.match-card[data-decision="regular_time"].finished .match-status { color: #75dfb6; }
@media (hover: none) and (pointer: coarse) {
  .match-card[data-clickable="true"]::after { opacity: 1; content: "Tap"; }
  .match-card[data-clickable="true"] { border-color: rgba(124, 131, 255, .52); }
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
    toolbarHint.textContent = 'Tap or click a match for details. Swipe sideways to inspect every round.';
  }}

  const openMatch = (card) => {{
    const matchLabel = card.querySelector('.match-meta span:first-child');
    const number = matchLabel ? matchLabel.textContent.trim().replace(/^M/i, '') : '';
    const target = links[number];
    if (!target || !target.clickable || !target.match_id) return;
    const params = new URLSearchParams({{
      view: target.view,
      match_id: String(target.match_id),
    }});
    window.top.location.assign(`/4_Match_Hub?${{params.toString()}}`);
  }};

  cards.forEach((card) => {{
    const matchLabel = card.querySelector('.match-meta span:first-child');
    const number = matchLabel ? matchLabel.textContent.trim().replace(/^M/i, '') : '';
    const target = links[number];
    if (!target) return;

    card.dataset.decision = target.decision || '';
    const scores = card.querySelectorAll('.team-score');
    if (scores.length >= 2) {{
      scores[0].textContent = target.home_score ?? '';
      scores[1].textContent = target.away_score ?? '';
    }}
    const status = card.querySelector('.match-status');
    if (status && target.decision_status) {{
      status.textContent = target.decision_status;
    }}
    if (target.result_label) {{
      card.setAttribute('data-result', target.result_label);
    }}

    if (!target.clickable) return;
    card.dataset.clickable = 'true';
    card.setAttribute('role', 'link');
    card.setAttribute('tabindex', '0');
    card.setAttribute('aria-label', `${{target.label}}. ${{target.result_label || target.decision_status || ''}}`);
    card.setAttribute('title', target.result_label || 'Open match details');
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
