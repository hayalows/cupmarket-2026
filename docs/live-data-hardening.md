# CupMarket live data hardening

## One source of match truth

All live pages now use `features/live_match_data.py`. The temporary reliability wrappers have been removed.

## Result correction policy

- A confirmed final result cannot move backwards to live or scheduled.
- A newer official final record may correct an older final score or winner.
- An older final record cannot overwrite a newer official result.
- An impossible live status is shown as awaiting confirmation rather than treated as final.

## Refresh policy

- Active or expected-live match windows: check every 45 seconds.
- No match activity: check every five minutes.
- Manual refresh clears only the football-feed cache.

## User communication

Short public messages explain whether scores are delayed, unavailable, or being confirmed. Technical provider details remain inside the diagnostics section.

## Validation

GitHub Actions compiles the app, smoke-tests every page, and runs deterministic unit tests for result reconciliation, corrections, live-state quarantine, refresh policy, and group-table behaviour.
