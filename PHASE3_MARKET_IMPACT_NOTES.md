# Phase 3 market movement and match impact

Phase 3 separates event-driven market impact from the existing latest-price columns.

New outputs:

- `data/history/market_movements.csv` keeps all archived event movements.
- `data/market_movements_latest.csv` contains the latest completed event for future UI use.

The primary before-price comes from the latest archived team snapshot before the current update. The existing `previous_price` column is used only as a fallback when no prior archived snapshot exists.

Each record includes:

- price before, price after, absolute change and percentage change
- Elo before, Elo after and change
- Round-of-32 probability before, after and change
- championship probability before, after and change
- triggering match IDs and readable score labels
- direct, same-group or other relationship to the event
- the source used for the before value
- single-match or multi-match-batch attribution status

When one workflow processes several completed matches, the movement is labelled `match_batch`. The system does not falsely assign the combined movement to one match. Exact individual attribution is available only when one new match triggered the update.

The new archive is idempotent and feature-flagged with `ENABLE_MARKET_IMPACT_ARCHIVE`. Failures remain isolated from live publication and Streamlit continues reading its existing files unchanged.
