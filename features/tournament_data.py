"""Compatibility gateway for every page that reads official CupMarket outputs.

All callers now use the commit-pinned loader in ``tournament_data_v2``. Keeping
this module preserves existing imports while removing the old local-only path.
"""

from features.tournament_data_v2 import *  # noqa: F401,F403
