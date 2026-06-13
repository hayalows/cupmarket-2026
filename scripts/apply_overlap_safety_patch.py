from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_PATH = ROOT / "backend" / "update_pipeline.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "update-cupmarket.yml"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Could not find expected {label} block.")
    return text.replace(old, new, 1)


def patch_pipeline() -> None:
    text = PIPELINE_PATH.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '''FORCE_RUN = os.environ.get("FORCE_RUN", "false").lower() in {
    "1", "true", "yes", "on"
}
RANDOM_SEED = int(
''',
        '''FORCE_RUN = os.environ.get("FORCE_RUN", "false").lower() in {
    "1", "true", "yes", "on"
}
PREDICTABLE_MATCH_STATUSES = {"TIMED", "SCHEDULED", "IN_PLAY", "PAUSED"}
ACTIVE_GROUP_MATCH_STATUSES = {"IN_PLAY", "PAUSED"}
RANDOM_SEED = int(
''',
        "status constants",
    )

    text = replace_once(
        text,
        '''if not TOKEN:
    raise RuntimeError(
        "FOOTBALL_DATA_TOKEN is missing from GitHub Actions secrets."
    )

MODEL_VERSION = "phase7_automated_group_stage_v1"
''',
        '''MODEL_VERSION = "phase7_automated_group_stage_v1"
''',
        "module-level token validation",
    )

    text = replace_once(
        text,
        '''def fetch_world_cup_matches() -> tuple[pd.DataFrame, dict]:
    response = requests.get(
''',
        '''def fetch_world_cup_matches() -> tuple[pd.DataFrame, dict]:
    if not TOKEN:
        raise RuntimeError(
            "FOOTBALL_DATA_TOKEN is missing from GitHub Actions secrets."
        )

    response = requests.get(
''',
        "fetch token validation",
    )

    helper_marker = '''def fetch_world_cup_matches() -> tuple[pd.DataFrame, dict]:
'''
    helper_code = '''def active_group_matches(world_cup: pd.DataFrame) -> pd.DataFrame:
    """Return active group-stage matches that block official publication."""
    required = {"match_id", "stage", "status", "home_team", "away_team"}
    missing = required - set(world_cup.columns)
    if missing:
        raise ValueError(
            "Cannot evaluate the official-update safety gate; missing columns: "
            + ", ".join(sorted(missing))
        )

    active = world_cup[
        (world_cup["stage"] == "GROUP_STAGE")
        & world_cup["status"].isin(ACTIVE_GROUP_MATCH_STATUSES)
    ].copy()

    sort_columns = [
        column for column in ["utc_date", "match_id"] if column in active.columns
    ]
    if sort_columns:
        active = active.sort_values(sort_columns)
    return active.reset_index(drop=True)


def active_group_match_summary(active_matches: pd.DataFrame) -> list[dict]:
    """Create a JSON-safe explanation of why publication was deferred."""
    rows = []
    for match in active_matches.itertuples(index=False):
        kickoff = pd.to_datetime(
            getattr(match, "utc_date", None), errors="coerce", utc=True
        )
        last_updated = pd.to_datetime(
            getattr(match, "last_updated", None), errors="coerce", utc=True
        )
        rows.append(
            {
                "match_id": int(match.match_id),
                "group": getattr(match, "group", None),
                "status": str(match.status),
                "home_team": str(match.home_team),
                "away_team": str(match.away_team),
                "kickoff_utc": kickoff.isoformat() if pd.notna(kickoff) else None,
                "last_updated_utc": (
                    last_updated.isoformat() if pd.notna(last_updated) else None
                ),
            }
        )
    return rows


'''
    if helper_code not in text:
        if helper_marker not in text:
            raise RuntimeError("Could not find fetch function marker.")
        text = text.replace(helper_marker, helper_code + helper_marker, 1)

    text = text.replace(
        'world_cup["status"].isin(["TIMED", "SCHEDULED"])',
        'world_cup["status"].isin(PREDICTABLE_MATCH_STATUSES)',
    )

    text = replace_once(
        text,
        '''    print("New finished group matches:", len(new_finished_matches))

    if new_finished_matches.empty and not FORCE_RUN:
''',
        '''    print("New finished group matches:", len(new_finished_matches))

    active_matches = active_group_matches(world_cup)
    if not active_matches.empty:
        summary = {
            "status": "deferred_active_group_matches",
            "checked_at_utc": started_at.isoformat(),
            "new_finished_matches_waiting": int(len(new_finished_matches)),
            "active_group_match_count": int(len(active_matches)),
            "active_group_matches": active_group_match_summary(active_matches),
            "number_of_simulations": N_SIMULATIONS,
            "api": api_metadata,
            "message": (
                "Official ratings, tournament probabilities and country prices "
                "were not changed because at least one group-stage match is still "
                "active. The next scheduled run will retry automatically."
            ),
        }
        atomic_to_json(summary, RUN_SUMMARY_PATH)
        print(
            "Official update deferred; active group matches:",
            len(active_matches),
        )
        return

    if new_finished_matches.empty and not FORCE_RUN:
''',
        "official publication safety gate",
    )

    PIPELINE_PATH.write_text(text, encoding="utf-8")


def patch_workflow() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''          test -f backend/run_update_pipeline.py
''',
        '''          test -f backend/run_update_pipeline.py
          test -f tests/test_update_overlap_guard.py
''',
        "test-file validation",
    )
    text = replace_once(
        text,
        '''          python -m py_compile backend/run_update_pipeline.py

      - name: Run CupMarket update pipeline
''',
        '''          python -m py_compile backend/run_update_pipeline.py
          python -m py_compile tests/test_update_overlap_guard.py
          python -m unittest tests.test_update_overlap_guard -v

      - name: Run CupMarket update pipeline
''',
        "backend safety test execution",
    )
    WORKFLOW_PATH.write_text(text, encoding="utf-8")


def main() -> None:
    patch_pipeline()
    patch_workflow()
    print("Applied CupMarket overlapping-live-match safety patch.")


if __name__ == "__main__":
    main()
