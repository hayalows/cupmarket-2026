# CupMarket live-feed audit — 14 June 2026

## Incident

A World Cup match had kicked off, but the public application continued to show the fixture as scheduled.

## Root causes and weaknesses found

1. The saved GitHub match file is a safe fallback, not a live feed. It can remain `TIMED` during an active match.
2. The live Streamlit pages loaded new data only when the script reran. Expiry of a data cache did not automatically update an already-open screen.
3. Several manual refresh controls cleared the whole Streamlit data cache instead of only the football-feed cache.
4. The fallback experience did not clearly distinguish a missing Streamlit secret, rejected token, API rate limit, provider delay, network fault and general provider outage.
5. The application did not explicitly detect the case where kickoff had passed but the provider still returned `TIMED` or `SCHEDULED`.

## Remediation applied

- Added automatic 45-second fragment refreshes to Tournament Pulse, Match Hub, Live Match Room, Qualification Lab and Live Group Centre.
- Reduced the live football-feed cache TTL to 45 seconds.
- Added a function that clears only the football-feed cache.
- Added safe HTTP and network error classification without exposing the API token.
- Added visible token, source, feed-state and request diagnostics.
- Added detection for a kickoff window whose provider status is still scheduled.
- Kept official Elo ratings, simulations and market prices locked until full time.
- Added regression tests for live status, current score, clock data and stale scheduled status.

## Deployment requirement

The deployed Streamlit app must contain `FOOTBALL_DATA_TOKEN` under **App settings → Secrets**. This is separate from the GitHub Actions secret. After saving or replacing the Streamlit secret, reboot the deployed application once.
