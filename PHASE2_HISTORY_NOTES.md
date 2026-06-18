# Phase 2 tournament history layer

Phase 2 adds append-only analytical records after a successful CupMarket publication.
It does not change Streamlit pages, prices, Elo calculations, tournament simulations, or current output file contracts.

New files are written under `data/history/` only when at least one new finished match is processed:

- `tournament_baseline.csv`
- `team_snapshots.csv`
- `elo_events.csv`
- `match_impacts.csv`
- `bracket_snapshots.csv`

The baseline uses the earliest valid file already stored in `data/market_history/` so the system preserves the earliest available opening state rather than treating the latest price as the opening price.

History writes are idempotent. Re-running the archive for the same completed update does not add duplicate rows.

The runner calls the history store only after the normal update and price-movement restoration complete. Archive failures are reported as warnings and do not block the live market publication.

Set `ENABLE_HISTORY_ARCHIVE=false` to disable history collection without changing the main pipeline.
