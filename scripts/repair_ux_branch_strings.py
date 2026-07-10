from pathlib import Path

path = Path("scripts/apply_ux_ia_branch.py")
text = path.read_text(encoding="utf-8")

old_sub = '    updated, count = pattern.subn(replacement.rstrip() + "\\n\\n", text, count=1)\n'
new_sub = '    updated, count = pattern.subn(lambda _: replacement.rstrip() + "\\n\\n", text, count=1)\n'
if old_sub not in text:
    raise RuntimeError("Literal function-replacement anchor was not found.")
text = text.replace(old_sub, new_sub, 1)

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
print("UX patch now preserves literal generated strings.")
