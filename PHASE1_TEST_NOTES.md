# Phase 1 safety coverage

This phase adds validation and tests without changing CupMarket prices, simulations, live data processing, or Streamlit pages.

Checks include:

- required published files and columns
- 48-team consistency across prices, probabilities, and group tables
- groups A-L with four teams and positions 1-4
- valid group-table arithmetic
- probability values within 0-1
- tournament stage totals of 32, 16, 8, 4, 2, and 1
- settlement probabilities summing to 1 for every team
- unique market ranks 1-48
- CupMarket prices within settlement bounds
- duplicate match IDs
- publication timestamps
- Python compilation and full unit-test discovery in GitHub Actions

The new quality workflow has read-only repository permissions and does not use the football API token. It cannot publish market data.
