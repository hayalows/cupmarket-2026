from __future__ import annotations

import features.match_hub_v2 as base
from features.reliable_live_match_data import load_matches

# The existing Match Hub keeps its UI and logic; only its score loader is replaced
# with the monotonic, reconciled loader.
base.load_matches = load_matches

inject_styles = base.inject_styles
render_match_hub = base.render_match_hub
