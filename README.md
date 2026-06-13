# CupMarket 2026

A Streamlit dashboard for World Cup match tracking, tournament probabilities, and virtual country prices.

## Live app

The Streamlit app uses `app.py` as its main file.

## Data flow

- Live scores and match status come from football-data.org.
- The trained Phase 3 goal models are stored in `backend/state/models/`.
- `backend/update_pipeline.py` updates live Elo, rolling form, future match probabilities, tournament simulations, and CupMarket prices.
- `.github/workflows/update-cupmarket.yml` checks for new completed group-stage matches every 15 minutes.
- A manual workflow run forces a full 20,000-simulation refresh.
- Updated files are committed into `data/`, and Streamlit reads the new commit automatically.

## Production health monitoring

The Model Health page reports the latest workflow status, the last successful and failed updates, the number of newly processed matches, and whether the model is behind the live API.

The app caches GitHub Actions status for five minutes. When automation fails, the workflow opens or updates a GitHub issue. A later successful run closes the alert.

## Required secrets

Create `FOOTBALL_DATA_TOKEN` in both places:

1. Streamlit Community Cloud secrets, for near-live scores in the app.
2. GitHub repository Actions secrets, for the automated backend.

Never commit the token to this repository.

## Required GitHub Actions permission

In the repository, open:

`Settings → Actions → General → Workflow permissions`

Select **Read and write permissions** so the workflow can commit refreshed files.

## Current automation scope

Automation v1 processes completed group-stage matches and simulates the remaining tournament. Before the Round of 32 begins, the backend must be upgraded to use the exact knockout bracket and completed knockout results.
