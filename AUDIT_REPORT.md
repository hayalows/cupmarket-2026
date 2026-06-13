# CupMarket Repository Audit

Date: 2026-06-13
Branch audited: `codex/cupmarket-audit`
Source repository: `hayalows/cupmarket-2026`

## Scope

This audit reviewed the full repository structure, Streamlit application,
backend simulation pipeline, machine-learning artifact loading, generated data
files, Python dependencies, and GitHub Actions deployment configuration.

## Repository Structure

- `app.py`: Single-file Streamlit dashboard.
- `backend/update_pipeline.py`: Automated football-data.org ingestion,
  live-state updates, prediction generation, tournament simulation, and output
  writers.
- `backend/state/`: Committed model inputs, ledgers, team maps, live Elo, and
  trained `joblib` model artifacts.
- `data/`: Committed dashboard outputs and one market-history snapshot.
- `.github/workflows/update-cupmarket.yml`: Scheduled/manual data update job.
- `requirements.txt`: Streamlit app dependencies.
- `backend/requirements.txt`: Backend/model dependencies.

## What Was Run

- Cloned the repository from GitHub and created `codex/cupmarket-audit` from
  `main`.
- Installed app and backend dependencies in a temporary virtual environment
  outside the repository.
- Ran `python -m py_compile app.py backend/update_pipeline.py`.
- Started the Streamlit app locally on `http://127.0.0.1:8510`.
- Opened the app in a browser and verified the Overview page rendered from the
  saved snapshot.
- Exercised every Streamlit page with `streamlit.testing.v1.AppTest`.
- Parsed every committed CSV and JSON data artifact.
- Loaded backend state and model artifacts with the pinned backend dependency
  versions.
- Ran a small offline backend simulation path against the saved match snapshot
  without calling the live football API.
- Ran `python -m unittest discover -v`.
- Attempted `python -m pytest`; `pytest` is not declared or installed.

## Findings

### High: Forced or overlapping live-match backend runs can fail

`backend/update_pipeline.py` generated predictions only for `TIMED` and
`SCHEDULED` group matches, but the tournament simulator required predictions
for every non-finished group match. The committed match snapshot currently
contains an `IN_PLAY` group match, so a forced run, or any run while one match is
live and another newly finished match triggers simulation, could fail with:

`ValueError: No live prediction found for unplayed match 537345: United States vs Paraguay.`

The fix treats `IN_PLAY` and `PAUSED` group matches as non-finished matches that
still need model predictions until final scores are available.

### Medium: Backend module was not importable without a token

`backend/update_pipeline.py` raised immediately at module import time when
`FOOTBALL_DATA_TOKEN` was missing. That was appropriate for a script execution
that needs the API, but it prevented tests, tooling, and offline validation from
importing pure helper functions.

The fix raises the missing-token error only when the backend attempts to fetch
live API data.

### Medium: Streamlit used a deprecated width parameter

The app rendered, but Streamlit 1.58 emitted warnings for every
`use_container_width=True` call:

`Please replace use_container_width with width.`

The warning states that `use_container_width` will be removed after
2025-12-31. The fix replaces it with `width="stretch"`.

### Low: No committed test suite

The repository had no `tests/` directory or test runner configuration.
`python -m unittest discover -v` ran zero tests, and `pytest` is not installed.

The fix adds focused standard-library unittest coverage and runs it in the
existing GitHub Actions validation step.

### Low: Duplicate API parsing helpers

`nested_get` and football-data.org match parsing logic exist in both `app.py`
and `backend/update_pipeline.py`. This is not currently breaking the app, but
it increases the chance that the dashboard and backend drift in how they
interpret the API payload.

### Low: Workflow is hardcoded to push `main`

The scheduled workflow is intended to update `main`, and it has
`contents: write`, which is required for that behavior. However, the commit step
uses hardcoded `git pull --rebase origin main` and `git push origin main`.
Manual workflow runs from a non-main ref may behave unexpectedly or fail.

## Security Notes

- No API token or Streamlit secrets file is committed.
- `.gitignore` excludes `.env`, `.streamlit/secrets.toml`, `__pycache__/`,
  `*.pyc`, and `.pytest_cache/`.
- The backend loads committed `joblib` model artifacts. `joblib.load` uses
  pickle semantics and should only load artifacts from trusted commits.
- The workflow does not run on `pull_request`, which reduces the risk of
  executing model artifacts from untrusted pull requests automatically.

## Generated Data Review

All committed CSV and JSON files parsed successfully:

- `data/cupmarket_prices_latest.csv`: 48 rows, 28 columns.
- `data/current_group_tables.csv`: 48 rows, 11 columns.
- `data/tournament_probabilities_latest.csv`: 48 rows, 23 columns.
- `data/world_cup_2026_matches_latest.csv`: 104 rows, 14 columns.
- `data/world_cup_live_predictions_latest.csv`: 68 rows, 29 columns.
- Backend state CSVs parsed successfully.
- Backend model files are present and load with the pinned backend dependency
  versions.

The `world_cup_live_predictions_latest.csv` row count reflects the live-match
prediction gap described above.

## Verification After Fixes

- `python -m py_compile app.py backend/update_pipeline.py tests/test_update_pipeline.py`
- `python -m unittest discover -v`
- `python -m unittest discover -s tests -v`
- Streamlit AppTest execution for every app page.
- Browser reload of `http://127.0.0.1:8510` with no exception text or browser
  console errors.
- Offline backend smoke simulation with `N_SIMULATIONS=20`, producing 69 live
  predictions, 48 probability rows, 48 price rows, champion total `1.0`, and
  Round of 32 total `32.0`.

