import numpy as np
import pandas as pd


def minute_now(match):
    value=pd.to_numeric(match.get("minute"),errors="coerce")
    if pd.notna(value):
        return int(np.clip(value,0,90))
    return 45
