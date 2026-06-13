from __future__ import annotations

import numpy as np
import pandas as pd

from features.live_group_data import FINISHED, LIVE, group_records, match_result
from features.thirds import rank_thirds
from backend.group_scenarios import _rank_group


def match_minute(match: dict) -> int:
    value = pd.to_numeric(match.get("minute"), errors="coerce")
    if pd.notna(value):
        return int(np.clip(value, 0, 90))
    kickoff = match.get("utc_date")
    if pd.notna(kickoff):
        elapsed = (pd.Timestamp.now(tz="UTC") - kickoff).total_seconds() / 60
        return int(np.clip(elapsed, 0, 90))
    return 45
