from pathlib import Path

path = Path("app.py")
text = path.read_text(encoding="utf-8")
marker = 'QUALIFICATION_TOOLS_VERSION = "1.0"'

if marker not in text:
    anchors = [
        (
            "import streamlit as st\n",
            "import streamlit as st\n\n"
            "from features.match_ui import combine_prediction_sources, render_match_centre\n"
            "from features.qualification_ui import render_qualification_lab\n",
        ),
        (
            'PREDICTIONS_PATH = DATA_DIR / "world_cup_live_predictions_latest.csv"\n'
            'MATCH_SNAPSHOT_PATH = DATA_DIR / "world_cup_2026_matches_latest.csv"\n',
            'PREDICTIONS_PATH = DATA_DIR / "world_cup_live_predictions_latest.csv"\n'
            'PREDICTION_LEDGER_PATH = APP_ROOT / "backend" / "state" / "world_cup_prediction_ledger.csv"\n'
            'MATCH_SNAPSHOT_PATH = DATA_DIR / "world_cup_2026_matches_latest.csv"\n',
        ),
        (
            "WORKFLOW_STALE_MINUTES = 45\n",
            'WORKFLOW_STALE_MINUTES = 45\nQUALIFICATION_TOOLS_VERSION = "1.0"\n',
        ),
        (
            '''        "Team Explorer": (
            "Team Explorer",
            "Inspect a country's path, price and tournament outlook.",
        ),
        "Group Tables": (
''',
            '''        "Team Explorer": (
            "Team Explorer",
            "Inspect a country's path, price and tournament outlook.",
        ),
        "Qualification Lab": (
            "Qualification Lab",
            "See what a win, draw or loss means for every country's group-stage path.",
        ),
        "Group Tables": (
''',
        ),
        (
            '''predictions = read_csv(PREDICTIONS_PATH)
price_history = load_price_history()
''',
            '''predictions = read_csv(PREDICTIONS_PATH)
prediction_ledger = read_csv(PREDICTION_LEDGER_PATH)
all_prediction_outputs = combine_prediction_sources(predictions, prediction_ledger)
price_history = load_price_history()
''',
        ),
        (
            '    "Team Explorer": "◎  Team Explorer",\n    "Group Tables": "▤  Group Tables",\n',
            '    "Team Explorer": "◎  Team Explorer",\n    "Qualification Lab": "◇  Qualification Lab",\n    "Group Tables": "▤  Group Tables",\n',
        ),
    ]
    for old, new in anchors:
        if text.count(old) != 1:
            raise RuntimeError(f"Expected one anchor, found {text.count(old)}")
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")

print("Core group-stage tools patch applied.")
