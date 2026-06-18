# Phase 4 Matchday 3 opponent probabilities

Phase 4 adds a separate group-stage-only Monte Carlo pass after the main CupMarket publication.
It reuses the current model's group ranking rules and Round-of-32 slot constraints, then counts which opponents each team faces across the simulations.

New outputs:

- `data/round_32_opponent_probabilities_latest.csv`
- `data/round_32_path_status_latest.csv`
- `data/round_32_opponent_probabilities_metadata.json`

The opponent file contains unconditional matchup probability and probability conditional on qualification.
The path-status file contains each team's most likely opponent, qualification probability, group-position probabilities, fixture status, confirmed slot when available, and whether the group is complete.

Fixture statuses are deliberately conservative:

- `projected`: the team's group is not complete.
- `slot_confirmed`: the team's position and slot are fixed, but the opponent group is unfinished.
- `confirmed`: both sides of a fixed winner/runner-up pairing are settled.
- `slot_confirmed_opponent_pending`: the team won its group, but its best-third opponent remains provisional.
- `third_place_ranking_pending`: the team finished third and must wait for cross-group ranking and allocation.
- `eliminated`: the team finished fourth.

Third-place allocations remain labelled provisional because the current model still uses `provisional_constraint_assignment` rather than a final official allocation table.

The feature is controlled by `ENABLE_OPPONENT_PROBABILITIES`. Its simulation count defaults to the main model's simulation count and can be changed with `OPPONENT_PROBABILITY_SIMULATIONS`.

Failures are isolated from the live market update and do not alter existing Streamlit inputs.
