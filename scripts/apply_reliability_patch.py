from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label}; found {count}.")
    return text.replace(old, new, 1)


def replace_top_level_function(text: str, name: str, replacement: str) -> str:
    pattern = re.compile(
        rf"^def {re.escape(name)}\(.*?(?=^def |\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    updated, count = pattern.subn(replacement.rstrip() + "\n\n", text, count=1)
    if count != 1:
        raise RuntimeError(f"Could not replace top-level function {name}; found {count}.")
    return updated


def patch_tournament_path_data() -> None:
    path = "features/tournament_path_data.py"
    text = read(path)
    text = replace_once(
        text,
        "from features.official_data import load_latest_csv, load_latest_json\n",
        "from features.official_bundle import load_consistent_official_bundle\n"
        "from features.official_data import load_latest_csv, load_latest_json\n",
        "official bundle import",
    )
    text = replace_once(
        text,
        'PATH_STATUS_PATH = DATA_DIR / "round_32_path_status_latest.csv"\n',
        'GROUP_TABLES_PATH = DATA_DIR / "current_group_tables.csv"\n'
        'PATH_STATUS_PATH = DATA_DIR / "round_32_path_status_latest.csv"\n',
        "group tables path",
    )

    next_fixture_function = '''def team_next_knockout_slot(progress: pd.DataFrame, team: str) -> pd.Series:
    """Return the selected country's next active or upcoming knockout fixture.

    The previous implementation only rebuilt Round-of-16 slots. This version reads
    the official knockout progress table directly, so it remains correct in the
    quarter-finals, semi-finals and final as the tournament advances.
    """
    required = {"home_team", "away_team", "status"}
    if progress.empty or not required.issubset(progress.columns):
        return pd.Series(dtype=object)

    rows = progress.copy()
    home = rows["home_team"].map(clean_team)
    away = rows["away_team"].map(clean_team)
    status = rows["status"].astype(str).str.upper()
    candidates = rows.loc[
        (home.eq(str(team)) | away.eq(str(team)))
        & ~status.isin({"FINISHED", "AWARDED", "CANCELLED"})
    ].copy()
    if candidates.empty:
        return pd.Series(dtype=object)

    if "utc_date" in candidates.columns:
        candidates["utc_date"] = pd.to_datetime(
            candidates["utc_date"], errors="coerce", utc=True
        )
        candidates = candidates.sort_values("utc_date", na_position="last")

    row = candidates.iloc[0]
    home_team = clean_team(row.get("home_team"))
    away_team = clean_team(row.get("away_team"))
    fixture = f"{home_team} vs {away_team}"
    if home_team == "TBD" or away_team == "TBD":
        fixture = f"{team} vs opponent pending"

    match_number = pd.to_numeric(
        row.get("logical_match_number", row.get("match_number")), errors="coerce"
    )
    return pd.Series(
        {
            "match_number": int(match_number) if pd.notna(match_number) else None,
            "stage": str(row.get("stage") or ""),
            "stage_label": stage_label(row.get("stage")),
            "fixture": fixture,
            "state": str(row.get("status") or "Pending").replace("_", " ").title(),
            "known_teams": ", ".join(
                value for value in (home_team, away_team) if value != "TBD"
            ),
            "kickoff_utc": row.get("utc_date"),
        }
    )
'''
    text = replace_top_level_function(text, "team_next_knockout_slot", next_fixture_function)

    load_function = '''def load_tournament_path_data() -> dict[str, Any]:
    """Load one consistent publication generation for every country-path view."""
    bundle = load_consistent_official_bundle(
        csv_paths={
            "prices": DATA_DIR / "cupmarket_prices_latest.csv",
            "predictions": DATA_DIR / "world_cup_live_predictions_latest.csv",
            "group_tables": GROUP_TABLES_PATH,
            "path_status": PATH_STATUS_PATH,
            "opponents": OPPONENTS_PATH,
            "bracket": BRACKET_PATH,
            "progress": KNOCKOUT_PROGRESS_PATH,
            "movements": MARKET_MOVEMENT_PATH,
            "movement_history": MARKET_MOVEMENT_HISTORY_PATH,
            "snapshots": TEAM_SNAPSHOTS_PATH,
            "adaptive_ratings": ADAPTIVE_RATINGS_PATH,
        },
        json_paths={
            "bracket_state": BRACKET_STATE_PATH,
            "opponent_metadata": OPPONENT_METADATA_PATH,
            "publication_manifest": PUBLICATION_MANIFEST_PATH,
        },
    )

    prices = bundle.get("prices", pd.DataFrame())
    snapshots = bundle.get("snapshots", pd.DataFrame())
    if snapshots.empty:
        history = prices.copy()
    elif prices.empty:
        history = snapshots.copy()
    else:
        history = pd.concat([snapshots, prices], ignore_index=True, sort=False)
        required = {"team", "cupmarket_price", "generated_at_utc"}
        if required.issubset(history.columns):
            history["generated_at_utc"] = pd.to_datetime(
                history["generated_at_utc"], errors="coerce", utc=True
            )
            history = (
                history.dropna(subset=list(required))
                .drop_duplicates(["team", "generated_at_utc"], keep="last")
                .sort_values(["generated_at_utc", "team"])
                .reset_index(drop=True)
            )

    return {
        "prices": prices,
        "predictions": bundle.get("predictions", pd.DataFrame()),
        "history": history,
        "group_tables": bundle.get("group_tables", pd.DataFrame()),
        "path_status": bundle.get("path_status", pd.DataFrame()),
        "opponents": bundle.get("opponents", pd.DataFrame()),
        "bracket": bundle.get("bracket", pd.DataFrame()),
        "bracket_state": bundle.get("bracket_state", {}),
        "opponent_metadata": bundle.get("opponent_metadata", {}),
        "progress": bundle.get("progress", pd.DataFrame()),
        "movements": bundle.get("movements", pd.DataFrame()),
        "movement_history": bundle.get("movement_history", pd.DataFrame()),
        "snapshots": snapshots,
        "adaptive_ratings": bundle.get("adaptive_ratings", pd.DataFrame()),
        "publication_manifest": bundle.get("publication_manifest", {}),
    }
'''
    text = replace_top_level_function(text, "load_tournament_path_data", load_function)
    write(path, text)


def patch_tournament_path_page() -> None:
    path = "features/tournament_path_page.py"
    text = read(path)
    render_function = '''def _render_next_knockout_slot(progress: pd.DataFrame, team: str) -> None:
    slot = team_next_knockout_slot(progress, team)
    if slot.empty:
        return
    kickoff = pd.to_datetime(slot.get("kickoff_utc"), errors="coerce", utc=True)
    kickoff_text = "Time pending" if pd.isna(kickoff) else kickoff.strftime("%d %b %Y - %H:%M UTC")
    stage = str(slot.get("stage_label") or "Knockout match")
    fixture = str(slot.get("fixture") or f"{team} vs opponent pending")
    match_number = slot.get("match_number")
    match_text = f"match {int(match_number)}" if pd.notna(match_number) else "fixture"

    st.markdown("### Next knockout match")
    st.success(f"**{team}'s next {stage.lower()} {match_text}:** {fixture}.")
    columns = st.columns(3)
    columns[0].metric("Stage", stage)
    columns[1].metric("State", slot.get("state", "Pending"))
    columns[2].metric("Kickoff", kickoff_text)
'''
    text = replace_top_level_function(text, "_render_next_knockout_slot", render_function)

    marker = "def render_tournament_path_page() -> None:\n    _render_country_page_v2()"
    position = text.find(marker)
    if position == -1:
        raise RuntimeError("Could not find the active tournament path page entry point.")
    text = text[:position] + marker + "\n"
    write(path, text)


def patch_adaptive_gate() -> None:
    path = "features/adaptive_ratings.py"
    text = read(path)
    text = replace_once(
        text,
        '    if str(row.get("guardrail_decision") or "").lower() == "rollback":\n'
        '        return 0.0\n',
        '    guardrail_decision = str(\n'
        '        row.get("guardrail_decision") or "collecting_evidence"\n'
        '    ).lower()\n'
        '    if guardrail_decision not in {"monitor", "trusted"}:\n'
        '        return 0.0\n',
        "adaptive evidence gate",
    )
    write(path, text)


def patch_prediction_metadata_gate() -> None:
    path = "backend/update_pipeline.py"
    text = read(path)
    pattern = re.compile(
        r"    adaptive_guardrail_active = bool\(.*?\n    \)\n    adaptive_enabled = bool\(.*?\n    \)\n\n    def current_state",
        flags=re.DOTALL,
    )
    replacement = '''    guardrail_decisions = set()
    if (
        adaptive_rating_frame is not None
        and not adaptive_rating_frame.empty
        and "guardrail_decision" in adaptive_rating_frame.columns
    ):
        guardrail_decisions = set(
            adaptive_rating_frame["guardrail_decision"]
            .astype(str)
            .str.lower()
            .dropna()
        )
    adaptive_enabled = bool(
        adaptive_rating_frame is not None
        and not adaptive_rating_frame.empty
        and guardrail_decisions
        and guardrail_decisions.issubset({"monitor", "trusted"})
    )
    adaptive_guardrail_active = not adaptive_enabled

    def current_state'''
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"Could not replace adaptive metadata gate; found {count}.")
    write(path, text)


def patch_model_health_copy() -> None:
    path = "features/model_health.py"
    text = read(path)
    text = replace_once(
        text,
        '    second[0].metric("Model", str(publication.get("model_version") or "Unavailable"))\n',
        '    second[0].metric(\n'
        '        "Tournament market model",\n'
        '        str(publication.get("model_version") or "Unavailable"),\n'
        '    )\n',
        "market model label",
    )
    text = replace_once(
        text,
        '    second[2].metric("Adaptive guardrail", adaptive_decision)\n',
        '    second[2].metric("Adaptive match layer", adaptive_decision)\n',
        "adaptive layer label",
    )
    text = replace_once(
        text,
        '    second[3].metric("Archive", str(archive.get("status") or "collecting").title())\n',
        '    second[3].metric("Archive", str(archive.get("status") or "collecting").title())\n'
        '    st.caption(\n'
        '        "Tournament prices use the market simulation model. Adaptive match nudges "\n'
        '        "remain paused until the comparison guardrail reaches Monitor or Trusted."\n'
        '    )\n',
        "model separation caption",
    )
    text = replace_once(
        text,
        '    elif adaptive:\n'
        '        st.info(str(adaptive.get("message") or "Adaptive comparison is collecting evidence."))\n',
        '    elif adaptive:\n'
        '        if str(adaptive.get("decision") or "") == "collecting_evidence":\n'
        '            st.info(\n'
        '                "Adaptive match adjustments are paused while the comparison "\n'
        '                "sample is still being collected. Baseline forecasts remain active."\n'
        '            )\n'
        '        else:\n'
        '            st.info(\n'
        '                str(\n'
        '                    adaptive.get("message")\n'
        '                    or "Adaptive comparison remains inside its published guardrail."\n'
        '                )\n'
        '            )\n',
        "adaptive health message",
    )
    write(path, text)


def patch_official_data_allowlist() -> None:
    path = "features/official_data.py"
    text = read(path)
    text = replace_once(
        text,
        '    "market_movements_latest.csv": "data/market_movements_latest.csv",\n',
        '    "market_movements_latest.csv": "data/market_movements_latest.csv",\n'
        '    "market_movements.csv": "data/history/market_movements.csv",\n',
        "market movement history allowlist",
    )
    write(path, text)


def patch_analysis_lab() -> None:
    path = "pages/11_Tournament_Insights.py"
    text = read(path)
    old = '''tables = pd.read_csv(DATA_DIR / "current_group_tables.csv")
movements_path = DATA_DIR / "market_movements_latest.csv"
movements = pd.read_csv(movements_path) if movements_path.exists() else pd.DataFrame()
movement_history_path = DATA_DIR / "history" / "market_movements.csv"
movement_history = (
    pd.read_csv(movement_history_path)
    if movement_history_path.exists()
    else movements
)
'''
    new = '''tables = path_data.get("group_tables", pd.DataFrame())
movements = path_data.get("movements", pd.DataFrame())
movement_history = path_data.get("movement_history", pd.DataFrame())
if movement_history.empty:
    movement_history = movements
'''
    text = replace_once(text, old, new, "Analysis Lab consistent data load")
    write(path, text)


def add_tests() -> None:
    write(
        "tests/test_reliability_patch.py",
        '''from __future__ import annotations

import unittest

import pandas as pd

from features.adaptive_ratings import adaptive_rating_adjustment
from features.tournament_path_data import team_next_knockout_slot


class ReliabilityPatchTests(unittest.TestCase):
    def test_next_fixture_tracks_current_knockout_stage(self):
        progress = pd.DataFrame(
            [
                {
                    "logical_match_number": 90,
                    "stage": "LAST_16",
                    "utc_date": "2026-07-04T21:00:00Z",
                    "status": "FINISHED",
                    "home_team": "Paraguay",
                    "away_team": "France",
                },
                {
                    "logical_match_number": 97,
                    "stage": "QUARTER_FINALS",
                    "utc_date": "2026-07-09T20:00:00Z",
                    "status": "FINISHED",
                    "home_team": "France",
                    "away_team": "Morocco",
                },
                {
                    "logical_match_number": 101,
                    "stage": "SEMI_FINALS",
                    "utc_date": "2026-07-14T19:00:00Z",
                    "status": "TIMED",
                    "home_team": "France",
                    "away_team": None,
                },
            ]
        )
        slot = team_next_knockout_slot(progress, "France")
        self.assertEqual(slot["match_number"], 101)
        self.assertEqual(slot["stage_label"], "Semi-finals")
        self.assertEqual(slot["fixture"], "France vs opponent pending")

    def test_eliminated_country_has_no_next_fixture(self):
        progress = pd.DataFrame(
            [
                {
                    "logical_match_number": 97,
                    "stage": "QUARTER_FINALS",
                    "utc_date": "2026-07-09T20:00:00Z",
                    "status": "FINISHED",
                    "home_team": "France",
                    "away_team": "Morocco",
                }
            ]
        )
        self.assertTrue(team_next_knockout_slot(progress, "Morocco").empty)

    def test_adaptive_adjustment_waits_for_evidence(self):
        collecting = pd.DataFrame(
            [
                {
                    "team": "France",
                    "rating_change": 100.0,
                    "confidence_level": "High",
                    "overreaction_risk": "Stable signal",
                    "guardrail_decision": "collecting_evidence",
                }
            ]
        )
        trusted = collecting.copy()
        trusted.loc[0, "guardrail_decision"] = "trusted"
        self.assertEqual(adaptive_rating_adjustment("France", collecting, "SEMI_FINALS"), 0.0)
        self.assertGreater(adaptive_rating_adjustment("France", trusted, "SEMI_FINALS"), 0.0)


if __name__ == "__main__":
    unittest.main()
''',
    )


def remove_legacy_patchers() -> None:
    for relative in (
        ".github/workflows/apply-health-ui.yml",
        ".github/workflows/apply-product-ui.yml",
        ".github/workflows/apply-live-qualification.yml",
        "scripts/apply_health_patch.py",
        "scripts/apply_product_ui_patch.py",
        "scripts/apply_live_qualification_patch.py",
    ):
        target = ROOT / relative
        if target.exists():
            target.unlink()


def main() -> None:
    patch_tournament_path_data()
    patch_tournament_path_page()
    patch_adaptive_gate()
    patch_prediction_metadata_gate()
    patch_model_health_copy()
    patch_official_data_allowlist()
    patch_analysis_lab()
    add_tests()
    remove_legacy_patchers()
    print("CupMarket reliability patch applied.")


if __name__ == "__main__":
    main()
