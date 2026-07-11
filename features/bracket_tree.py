from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

import pandas as pd
import streamlit.components.v1 as components

from features.tournament_path_data import ROUND_OF_16_SOURCES

FLAG_ICONS_VERSION = "7.5.0"
FLAG_BASE_URL = (
    "https://cdn.jsdelivr.net/gh/lipis/flag-icons@"
    f"{FLAG_ICONS_VERSION}/flags/4x3"
)

TEAM_FLAG_CODES = {
    "Algeria": "dz",
    "Argentina": "ar",
    "Australia": "au",
    "Austria": "at",
    "Belgium": "be",
    "Bosnia-Herzegovina": "ba",
    "Bosnia and Herzegovina": "ba",
    "Brazil": "br",
    "Canada": "ca",
    "Cape Verde Islands": "cv",
    "Cabo Verde": "cv",
    "Colombia": "co",
    "Congo DR": "cd",
    "DR Congo": "cd",
    "Croatia": "hr",
    "Ecuador": "ec",
    "Egypt": "eg",
    "England": "gb-eng",
    "France": "fr",
    "Germany": "de",
    "Ghana": "gh",
    "Ivory Coast": "ci",
    "Côte d’Ivoire": "ci",
    "Cote d'Ivoire": "ci",
    "Japan": "jp",
    "Mexico": "mx",
    "Morocco": "ma",
    "Netherlands": "nl",
    "Norway": "no",
    "Paraguay": "py",
    "Portugal": "pt",
    "Senegal": "sn",
    "South Africa": "za",
    "Spain": "es",
    "Sweden": "se",
    "Switzerland": "ch",
    "United States": "us",
    "United States of America": "us",
    "USA": "us",
}

STAGE_BY_MATCH = {
    **{number: "Round of 32" for number in range(73, 89)},
    **{number: "Round of 16" for number in range(89, 97)},
    **{number: "Quarter-finals" for number in range(97, 101)},
    101: "Semi-finals",
    102: "Semi-finals",
    103: "Third place",
    104: "Final",
}

WINNER_SOURCES = {
    **ROUND_OF_16_SOURCES,
    97: (90, 89),
    98: (93, 94),
    99: (91, 92),
    100: (95, 96),
    101: (97, 98),
    102: (99, 100),
    104: (101, 102),
}

LEFT_COLUMNS = {
    "r32": [73, 76, 75, 78, 83, 84, 81, 82],
    "r16": [89, 90, 93, 94],
    "qf": [97, 98],
    "sf": [101],
}
RIGHT_COLUMNS = {
    "sf": [102],
    "qf": [99, 100],
    "r16": [91, 92, 95, 96],
    "r32": [74, 77, 79, 80, 87, 86, 85, 88],
}

ACTIVE_STATUSES = {"IN_PLAY", "LIVE", "PAUSED", "SUSPENDED"}
UPCOMING_STATUSES = {"TIMED", "SCHEDULED"}
FINISHED_STATUSES = {"FINISHED", "AWARDED"}
VALID_STATUSES = ACTIVE_STATUSES | UPCOMING_STATUSES | FINISHED_STATUSES | {
    "CANCELLED",
    "POSTPONED",
}

CANVAS_WIDTH = 2380
CANVAS_HEIGHT = 1210
CARD_WIDTH = 210
CARD_HEIGHT = 92
COLUMN_X = {
    "left_r32": 30,
    "left_r16": 300,
    "left_qf": 570,
    "left_sf": 840,
    "final": 1085,
    "right_sf": 1330,
    "right_qf": 1600,
    "right_r16": 1870,
    "right_r32": 2140,
}
ROW_CENTRES = {
    "r32": [140, 265, 390, 515, 640, 765, 890, 1015],
    "r16": [202.5, 452.5, 702.5, 952.5],
    "qf": [327.5, 827.5],
    "sf": [577.5],
    "final": [577.5],
    "third": [1005],
}


@dataclass(frozen=True)
class BracketMatch:
    number: int
    stage: str
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None
    status: str
    kickoff: pd.Timestamp | None
    advancing_team: str
    decision_method: str
    home_penalties: int | None
    away_penalties: int | None

    @property
    def is_live(self) -> bool:
        return self.status in ACTIVE_STATUSES

    @property
    def is_finished(self) -> bool:
        return self.status in FINISHED_STATUSES


def _clean_team(value: Any) -> str:
    try:
        if pd.isna(value):
            return "TBD"
    except (TypeError, ValueError):
        pass
    text = str(value or "").strip()
    return "TBD" if not text or text.lower() in {"nan", "none", "null", "tbd"} else text


def _optional_int(value: Any) -> int | None:
    number = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(number) else int(number)


def _kickoff(value: Any) -> pd.Timestamp | None:
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    return None if pd.isna(timestamp) else timestamp


def _normalise_status(
    raw_status: Any,
    kickoff: pd.Timestamp | None,
    home_score: int | None,
    away_score: int | None,
    advancing_team: str,
) -> str:
    status = str(raw_status or "").strip().upper()
    if status in VALID_STATUSES:
        return status
    if advancing_team != "TBD":
        return "FINISHED"
    if home_score is not None and away_score is not None:
        now = pd.Timestamp.now(tz="UTC")
        if kickoff is None or kickoff <= now:
            return "FINISHED"
    if kickoff is not None and kickoff > pd.Timestamp.now(tz="UTC"):
        return "TIMED"
    return "SCHEDULED"


def _infer_winner(
    status: str,
    home_team: str,
    away_team: str,
    home_score: int | None,
    away_score: int | None,
    advancing_team: str,
    home_penalties: int | None,
    away_penalties: int | None,
) -> str:
    if advancing_team != "TBD":
        return advancing_team
    if status not in FINISHED_STATUSES:
        return "TBD"
    if home_penalties is not None and away_penalties is not None:
        if home_penalties > away_penalties:
            return home_team
        if away_penalties > home_penalties:
            return away_team
    if home_score is not None and away_score is not None:
        if home_score > away_score:
            return home_team
        if away_score > home_score:
            return away_team
    return "TBD"


def _placeholder_team(match_number: int, side: int) -> str:
    if match_number == 103:
        return f"Loser of M{101 + side}"
    sources = WINNER_SOURCES.get(match_number)
    if not sources:
        return "TBD"
    return f"Winner of M{sources[side]}"


def _stage_for_number(number: int, raw_stage: Any = None) -> str:
    return STAGE_BY_MATCH.get(number, str(raw_stage or "Knockout"))


def _row_number(row: pd.Series, fallback: int | None = None) -> int | None:
    for field in ("logical_match_number", "bracket_match_number", "match_number"):
        number = pd.to_numeric(row.get(field), errors="coerce")
        if pd.notna(number):
            return int(number)
    return fallback


def build_bracket_matches(source: pd.DataFrame) -> dict[int, BracketMatch]:
    rows: dict[int, pd.Series] = {}
    if isinstance(source, pd.DataFrame) and not source.empty:
        for index, row in source.iterrows():
            number = _row_number(row, int(index) if isinstance(index, int) else None)
            if number in STAGE_BY_MATCH:
                rows[number] = row

    matches: dict[int, BracketMatch] = {}
    for number in sorted(STAGE_BY_MATCH):
        row = rows.get(number, pd.Series(dtype=object))
        home_team = _clean_team(row.get("home_team"))
        away_team = _clean_team(row.get("away_team"))
        if home_team == "TBD" and number >= 89:
            home_team = _placeholder_team(number, 0)
        if away_team == "TBD" and number >= 89:
            away_team = _placeholder_team(number, 1)

        home_score = _optional_int(row.get("home_score", row.get("home_score_full_time")))
        away_score = _optional_int(row.get("away_score", row.get("away_score_full_time")))
        home_penalties = _optional_int(row.get("home_penalties", row.get("home_score_penalties")))
        away_penalties = _optional_int(row.get("away_penalties", row.get("away_score_penalties")))
        kickoff = _kickoff(row.get("utc_date", row.get("kickoff_utc")))
        advancing_team = _clean_team(row.get("advancing_team"))
        status = _normalise_status(
            row.get("status"),
            kickoff,
            home_score,
            away_score,
            advancing_team,
        )
        advancing_team = _infer_winner(
            status,
            home_team,
            away_team,
            home_score,
            away_score,
            advancing_team,
            home_penalties,
            away_penalties,
        )
        matches[number] = BracketMatch(
            number=number,
            stage=_stage_for_number(number, row.get("stage")),
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            status=status,
            kickoff=kickoff,
            advancing_team=advancing_team,
            decision_method=str(row.get("decision_method") or "").strip().lower(),
            home_penalties=home_penalties,
            away_penalties=away_penalties,
        )
    return matches


def _flag_html(team: str) -> str:
    code = TEAM_FLAG_CODES.get(team)
    if not code:
        return '<span class="flag-placeholder" aria-hidden="true"></span>'
    url = f"{FLAG_BASE_URL}/{code}.svg"
    return (
        f'<img class="team-flag" src="{escape(url)}" '
        f'alt="{escape(team)} flag" loading="lazy">'
    )


def _score(score: int | None) -> str:
    return "" if score is None else str(score)


def _status_text(match: BracketMatch) -> str:
    if match.is_live:
        return "Live"
    if match.is_finished:
        if match.decision_method == "penalties":
            return "Finished on penalties"
        if match.decision_method == "extra_time":
            return "Finished after extra time"
        return "Full time"
    if match.status == "POSTPONED":
        return "Postponed"
    if match.status == "CANCELLED":
        return "Cancelled"
    if match.kickoff is not None:
        return match.kickoff.strftime("%d %b · %H:%M UTC")
    return "Waiting for teams"


def _card_class(match: BracketMatch) -> str:
    if match.is_live:
        return "match-card live"
    if match.is_finished:
        return "match-card finished"
    return "match-card upcoming"


def _team_row(match: BracketMatch, team: str, score: int | None, penalties: int | None) -> str:
    is_winner = match.advancing_team == team and team != "TBD"
    winner_class = " winner" if is_winner else ""
    score_text = _score(score)
    return f'''
        <div class="team-row{winner_class}">
            {_flag_html(team)}
            <span class="team-name" title="{escape(team)}">{escape(team)}</span>
            <span class="team-score">{escape(score_text)}</span>
        </div>
    '''


def _card_html(match: BracketMatch, x: float, centre_y: float, extra_class: str = "") -> str:
    top = centre_y - CARD_HEIGHT / 2
    class_name = f"{_card_class(match)} {extra_class}".strip()
    return f'''
    <article class="{class_name}" style="left:{x}px; top:{top}px" aria-label="{escape(match.stage)} match {match.number}">
        <div class="match-meta">
            <span>M{match.number}</span>
            <span class="match-status">{escape(_status_text(match))}</span>
        </div>
        {_team_row(match, match.home_team, match.home_score, match.home_penalties)}
        {_team_row(match, match.away_team, match.away_score, match.away_penalties)}
    </article>
    '''


def _elbow_path(source_x: float, source_y: float, target_x: float, target_y: float) -> str:
    midpoint = (source_x + target_x) / 2
    return f"M {source_x} {source_y} H {midpoint} V {target_y} H {target_x}"


def _connector_paths() -> str:
    paths: list[str] = []

    def add_left(source_column: str, target_column: str, source_rows: list[float], target_rows: list[float]) -> None:
        source_x = COLUMN_X[source_column] + CARD_WIDTH
        target_x = COLUMN_X[target_column]
        for index, source_y in enumerate(source_rows):
            target_y = target_rows[index // 2]
            paths.append(
                f'<path d="{_elbow_path(source_x, source_y, target_x, target_y)}" />'
            )

    def add_right(source_column: str, target_column: str, source_rows: list[float], target_rows: list[float]) -> None:
        source_x = COLUMN_X[source_column]
        target_x = COLUMN_X[target_column] + CARD_WIDTH
        for index, source_y in enumerate(source_rows):
            target_y = target_rows[index // 2]
            paths.append(
                f'<path d="{_elbow_path(source_x, source_y, target_x, target_y)}" />'
            )

    add_left("left_r32", "left_r16", ROW_CENTRES["r32"], ROW_CENTRES["r16"])
    add_left("left_r16", "left_qf", ROW_CENTRES["r16"], ROW_CENTRES["qf"])
    add_left("left_qf", "left_sf", ROW_CENTRES["qf"], ROW_CENTRES["sf"])
    add_left("left_sf", "final", ROW_CENTRES["sf"], ROW_CENTRES["final"])

    add_right("right_r32", "right_r16", ROW_CENTRES["r32"], ROW_CENTRES["r16"])
    add_right("right_r16", "right_qf", ROW_CENTRES["r16"], ROW_CENTRES["qf"])
    add_right("right_qf", "right_sf", ROW_CENTRES["qf"], ROW_CENTRES["sf"])
    add_right("right_sf", "final", ROW_CENTRES["sf"], ROW_CENTRES["final"])

    third_centre_x = COLUMN_X["final"] + CARD_WIDTH / 2
    third_top_y = ROW_CENTRES["third"][0] - CARD_HEIGHT / 2
    paths.append(
        f'<path class="third-place-path" d="M {COLUMN_X["left_sf"] + CARD_WIDTH / 2} '
        f'{ROW_CENTRES["sf"][0] + CARD_HEIGHT / 2} V {third_top_y - 26} H {third_centre_x} V {third_top_y}" />'
    )
    paths.append(
        f'<path class="third-place-path" d="M {COLUMN_X["right_sf"] + CARD_WIDTH / 2} '
        f'{ROW_CENTRES["sf"][0] + CARD_HEIGHT / 2} V {third_top_y - 26} H {third_centre_x} V {third_top_y}" />'
    )
    return "".join(paths)


def _stage_labels() -> str:
    labels = [
        (COLUMN_X["left_r32"], "Round of 32"),
        (COLUMN_X["left_r16"], "Round of 16"),
        (COLUMN_X["left_qf"], "Quarter-finals"),
        (COLUMN_X["left_sf"], "Semi-finals"),
        (COLUMN_X["final"], "Final"),
        (COLUMN_X["right_sf"], "Semi-finals"),
        (COLUMN_X["right_qf"], "Quarter-finals"),
        (COLUMN_X["right_r16"], "Round of 16"),
        (COLUMN_X["right_r32"], "Round of 32"),
    ]
    return "".join(
        f'<div class="stage-label" style="left:{x}px">{escape(label)}</div>'
        for x, label in labels
    )


def _cards(matches: dict[int, BracketMatch]) -> str:
    cards: list[str] = []
    for column, numbers in LEFT_COLUMNS.items():
        x = COLUMN_X[f"left_{column}"]
        for number, centre_y in zip(numbers, ROW_CENTRES[column]):
            cards.append(_card_html(matches[number], x, centre_y))
    for column, numbers in RIGHT_COLUMNS.items():
        x = COLUMN_X[f"right_{column}"]
        for number, centre_y in zip(numbers, ROW_CENTRES[column]):
            cards.append(_card_html(matches[number], x, centre_y))
    cards.append(_card_html(matches[104], COLUMN_X["final"], ROW_CENTRES["final"][0], "final-card"))
    cards.append(_card_html(matches[103], COLUMN_X["final"], ROW_CENTRES["third"][0], "third-card"))
    return "".join(cards)


def bracket_html(source: pd.DataFrame) -> str:
    matches = build_bracket_matches(source)
    return f'''
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {{
  --bg: #0f1426;
  --surface: #171d33;
  --surface-2: #1d2540;
  --border: #303a5c;
  --text: #f3f5fb;
  --muted: #aeb7cc;
  --primary: #7c83ff;
  --green: #38c793;
  --red: #ff6b7d;
  --line: #445171;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: transparent; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Arial, sans-serif; }}
.bracket-shell {{
  background: linear-gradient(180deg, #11172b 0%, #0c1120 100%);
  border: 1px solid #26304e;
  border-radius: 16px;
  overflow: hidden;
  color: var(--text);
}}
.bracket-toolbar {{
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  padding: 16px 18px;
  border-bottom: 1px solid #26304e;
  background: rgba(20, 27, 49, .94);
}}
.bracket-toolbar strong {{ font-size: 15px; }}
.bracket-toolbar span {{ color: var(--muted); font-size: 12px; }}
.bracket-scroll {{ overflow-x: auto; overflow-y: hidden; -webkit-overflow-scrolling: touch; }}
.bracket-canvas {{ position: relative; width: {CANVAS_WIDTH}px; height: {CANVAS_HEIGHT}px; min-width: {CANVAS_WIDTH}px; }}
.stage-label {{
  position: absolute;
  top: 32px;
  width: {CARD_WIDTH}px;
  color: #dce2f2;
  text-align: center;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: .08em;
  text-transform: uppercase;
}}
.connectors {{ position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }}
.connectors path {{ fill: none; stroke: var(--line); stroke-width: 2; vector-effect: non-scaling-stroke; }}
.connectors .third-place-path {{ stroke-dasharray: 7 7; opacity: .7; }}
.match-card {{
  position: absolute;
  width: {CARD_WIDTH}px;
  height: {CARD_HEIGHT}px;
  border: 1px solid var(--border);
  border-radius: 11px;
  background: linear-gradient(180deg, var(--surface-2), var(--surface));
  box-shadow: 0 13px 30px rgba(0,0,0,.22);
  overflow: hidden;
  z-index: 2;
}}
.match-card.finished {{ border-color: rgba(56,199,147,.36); }}
.match-card.live {{ border-color: rgba(255,107,125,.78); box-shadow: 0 0 0 3px rgba(255,107,125,.10), 0 13px 30px rgba(0,0,0,.24); }}
.match-card.final-card {{ border-color: rgba(124,131,255,.9); box-shadow: 0 0 0 4px rgba(124,131,255,.12), 0 18px 36px rgba(0,0,0,.3); }}
.match-card.third-card {{ border-style: dashed; }}
.match-meta {{
  height: 24px;
  padding: 0 9px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(255,255,255,.07);
  color: var(--muted);
  font-size: 9px;
  font-weight: 750;
  text-transform: uppercase;
  letter-spacing: .05em;
}}
.match-status {{ max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: right; }}
.live .match-status {{ color: #ff9aa7; }}
.team-row {{
  height: 33px;
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  align-items: center;
  gap: 7px;
  padding: 0 9px;
  color: #dfe5f2;
  font-size: 12px;
}}
.team-row + .team-row {{ border-top: 1px solid rgba(255,255,255,.045); }}
.team-row.winner {{ background: rgba(56,199,147,.09); color: white; font-weight: 800; }}
.team-flag, .flag-placeholder {{ width: 22px; height: 16px; border-radius: 3px; object-fit: cover; display: block; box-shadow: 0 0 0 1px rgba(255,255,255,.14); background: #2a3454; }}
.flag-placeholder {{ position: relative; }}
.flag-placeholder::after {{ content: ""; position: absolute; inset: 4px; border-radius: 50%; border: 1px solid #66718f; }}
.team-name {{ min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.team-score {{ min-width: 22px; text-align: right; color: white; font-weight: 850; font-variant-numeric: tabular-nums; }}
.bracket-footer {{
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 11px 16px;
  border-top: 1px solid #26304e;
  color: var(--muted);
  background: #11172b;
  font-size: 11px;
}}
.bracket-footer a {{ color: #b9beff; text-decoration: none; }}
@media (max-width: 720px) {{
  .bracket-toolbar {{ align-items: flex-start; flex-direction: column; }}
  .bracket-footer {{ flex-direction: column; }}
}}
@media (prefers-reduced-motion: reduce) {{ * {{ scroll-behavior: auto !important; }} }}
</style>
</head>
<body>
<div class="bracket-shell">
  <div class="bracket-toolbar">
    <strong>Official knockout bracket</strong>
    <span>Swipe or scroll sideways to inspect every round</span>
  </div>
  <div class="bracket-scroll" role="region" aria-label="World Cup knockout bracket" tabindex="0">
    <div class="bracket-canvas">
      {_stage_labels()}
      <svg class="connectors" viewBox="0 0 {CANVAS_WIDTH} {CANVAS_HEIGHT}" aria-hidden="true">{_connector_paths()}</svg>
      {_cards(matches)}
    </div>
  </div>
  <div class="bracket-footer">
    <span>Solid lines show winner progression. Dashed lines lead to the third-place match.</span>
    <span>Flags from <a href="https://github.com/lipis/flag-icons" target="_blank" rel="noreferrer">flag-icons</a> · MIT licence</span>
  </div>
</div>
</body>
</html>
'''


def render_bracket_tree(source: pd.DataFrame) -> None:
    components.html(bracket_html(source), height=1285, scrolling=False)
