from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path, old, new):
    text = path.read_text(encoding="utf-8")
    if old in text:
        path.write_text(text.replace(old, new), encoding="utf-8")


def main():
    replace(ROOT / "app.py", 'icon="◇"', 'icon="🧭"')
    replace(ROOT / "app.py", 'icon="◉"', 'icon="📊"')

    product_ui = ROOT / "features" / "product_ui.py"
    replace(product_ui, 'icon="◇"', 'icon="🧭"')
    replace(product_ui, 'icon="◉"', 'icon="📊"')
    replace(product_ui, ',\n            disabled=active_page == "match"', '')
    replace(product_ui, ',\n            disabled=active_page == "qualification"', '')
    replace(product_ui, ',\n            disabled=active_page == "group"', '')

    product_patch = ROOT / "scripts" / "apply_product_experience_refresh.py"
    replace(product_patch, 'icon=\\"◇\\"', 'icon=\\"🧭\\"')
    replace(product_patch, 'icon=\\"◉\\"', 'icon=\\"📊\\"')

    config = ROOT / ".streamlit" / "config.toml"
    text = config.read_text(encoding="utf-8")
    if "[client]" not in text:
        text = text.rstrip() + "\n\n[client]\nshowSidebarNavigation = false\n"
        config.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
