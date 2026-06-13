# CupMarket Phase 7 Automation

This package adds an automated backend to the existing Streamlit repository.

## What it does

- Checks football-data.org every 15 minutes.
- Does not run the expensive simulation when no new group-stage match has finished.
- When a new match finishes, it processes that match once.
- Updates live Elo and rolling team form.
- Generates new future-match probabilities.
- Runs 20,000 tournament simulations.
- Updates country prices and price history.
- Commits the new files to GitHub.
- Streamlit reads the new commit automatically.

## Required GitHub secret

Create this Actions secret:

FOOTBALL_DATA_TOKEN

The value is your private football-data.org token.

This is separate from the secret already stored in Streamlit.

## Required repository permission

Settings → Actions → General → Workflow permissions → Read and write permissions.

## First test

Open Actions → Update CupMarket data → Run workflow.

A manual run forces a full 20,000-simulation update even when no new match has finished.

## Current limitation

Automation v1 handles completed group-stage matches. Before the knockout stage begins, the backend must be upgraded to ingest the exact Round-of-32 bracket and completed knockout results.
