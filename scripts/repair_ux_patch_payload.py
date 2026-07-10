from pathlib import Path

path = Path("scripts/apply_ux_ia_refresh.py")
text = path.read_text(encoding="utf-8")
old = 'def decode(value: str) -> str:\n    return base64.b64decode(value.encode("ascii")).decode("utf-8")\n'
new = 'def decode(value: str) -> str:\n    padding = "=" * (-len(value) % 4)\n    return base64.b64decode((value + padding).encode("ascii")).decode("utf-8")\n'
if old not in text:
    raise RuntimeError("UX payload decoder anchor was not found.")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("UX payload decoder padding repaired.")
