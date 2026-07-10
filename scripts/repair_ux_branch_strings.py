from pathlib import Path

path = Path("scripts/apply_ux_ia_branch.py")
text = path.read_text(encoding="utf-8")
phrases = [
    "**Projected path** means future results can still change the opponent.",
    "**Slot confirmed** means the country's bracket position is fixed, but the opponent is not final.",
    "**Fixture confirmed** means both countries are known.",
]
for phrase in phrases:
    old = f'"{phrase}\\n\\n"'
    new = f'"{phrase}\\\\n\\\\n"'
    if old not in text:
        raise RuntimeError(f"Country definitions string was not found: {phrase}")
    text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("Generated Country definitions strings escaped.")
