from __future__ import annotations

from features.live_match_data import load_matches
from features.match_hub_v2 import inject_styles, render_match_hub
from features.tournament_data_v2 import DATA_DIR, load_static_data


def load_match_hub_data() -> dict:
    matches, source = load_matches(
        DATA_DIR / "world_cup_2026_matches_latest.csv"
    )
    return {
        "matches": matches,
        "source": source,
        "static": load_static_data(),
    }
