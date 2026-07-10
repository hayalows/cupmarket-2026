"""Run one Streamlit page in an isolated AppTest process."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("page")
    parser.add_argument("--analytics-performance", action="store_true")
    args = parser.parse_args()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    page = (ROOT / args.page).resolve()
    st.page_link = lambda *unused_args, **unused_kwargs: None
    st.switch_page = lambda *unused_args, **unused_kwargs: None
    app = AppTest.from_file(str(page), default_timeout=60)
    app.run()
    if args.analytics_performance:
        app.session_state["cupmarket_analytics_view"] = "Performance"
        app.run()
    if len(app.exception):
        raise SystemExit("\n".join(str(item) for item in app.exception))
    print(f"Rendered {page} without Streamlit exceptions.")


if __name__ == "__main__":
    main()
