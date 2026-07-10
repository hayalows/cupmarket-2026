# CupMarket 2026

A Streamlit app for World Cup match tracking, knockout paths, tournament probabilities, model evaluation, and virtual country prices.

## Live app

The Streamlit app uses `app.py` as its launcher and opens Overview by default.

## Product structure

Each visible page has one main responsibility:

- **Overview** — current round, latest results, upcoming fixtures, and market leaders.
- **Countries** — one selected country's status, path, price movement, and fixtures.
- **Matches** — live scores, upcoming fixtures, completed results, and forecast review.
- **Bracket** — confirmed fixtures and projected knockout slots.
- **Simulator** — sandbox result scenarios that never change official data.
- **Analysis** — forecast performance, adaptive research, and model evidence.
- **System Health** — data freshness, workflow state, publication status, and guardrails.
- **Archive** — permanent tournament history, market replay, and final model verdict.

The built-in Streamlit page list is hidden so users see one consistent navigation system.

## Data flow

- Live scores and match status come from football-data.org.
- The trained Phase 3 goal models are stored in `backend/state/models/`.
- `backend/update_pipeline.py` updates live Elo, rolling form, future match probabilities, knockout settlement, tournament simulations, adaptive signals, and CupMarket prices.
- `.github/workflows/update-cupmarket.yml` checks for newly completed official matches and missing official prediction rows.
- A manual workflow run forces a full 20,000-simulation refresh.
- Updated files are committed into `data/`, and Streamlit reads the new commit automatically.

## System health

System Health reports the latest published market time, score-check time, update-workflow state, data source, simulation model, adaptive guardrail, and archive state.

## Required secrets

Create `FOOTBALL_DATA_TOKEN` in both Streamlit Community Cloud secrets and GitHub Actions secrets. Never commit the token.

## Required GitHub Actions permission

Open `Settings → Actions → General → Workflow permissions` and select **Read and write permissions**.

## Current automation scope

CupMarket supports the completed group-stage record and the active knockout flow. Knockout fixtures use saved pre-match forecasts, settlement ledgers, advancement probabilities, live knockout projections, extra time, penalties, and stage-aware UI labels.
