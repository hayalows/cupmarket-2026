from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

FINISHED = {"FINISHED", "AWARDED"}
LIVE = {"IN_PLAY", "PAUSED"}
UPCOMING = {"TIMED", "SCHEDULED"}
DEFAULT_XG = 1.25
