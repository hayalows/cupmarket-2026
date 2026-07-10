from __future__ import annotations

from pathlib import Path

PATH = Path("features/tournament_path_data.py")
OLD = '''    if candidates.empty:
        return pd.Series(dtype=object)

    if "utc_date" in candidates.columns:
'''
NEW = '''    if candidates.empty:
        # Older or partial snapshots may contain completed Round-of-32 rows
        # without the official next-round fixture row. Preserve the original
        # projected Round-of-16 builder as a compatibility fallback.
        slots = round_of_16_build(progress)
        if slots.empty:
            return pd.Series(dtype=object)
        for _, slot in slots.iterrows():
            known = [
                value.strip()
                for value in str(slot.get("known_teams", "")).split(",")
                if value.strip()
            ]
            if str(team) in known:
                return slot
        return pd.Series(dtype=object)

    if "utc_date" in candidates.columns:
'''

text = PATH.read_text(encoding="utf-8")
count = text.count(OLD)
if count != 1:
    raise RuntimeError(f"Expected one next-fixture fallback anchor; found {count}.")
PATH.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
print("Preserved projected Round-of-16 compatibility fallback.")
