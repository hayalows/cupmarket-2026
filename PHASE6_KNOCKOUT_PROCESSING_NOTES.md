# Phase 6 knockout-stage processing

Phase 6 activates only after the exact Round-of-32 bracket from Phase 5 has been locked.

It adds a post-group processor that runs after the existing group-stage pipeline on every scheduled update.

## Official result processing

The processor ingests completed matches from:

- Round of 32
- Round of 16
- Quarter-finals
- Semi-finals
- Third-place match
- Final

Each completed match is processed once through the existing match ledger.

The official API winner determines which team advances. Full-time scores update the live team form and Elo state.

## Extra time and penalties

Regular-time and extra-time winners receive the normal Elo win or loss result.

A penalty shootout is treated as a draw for Elo because the teams were level through open play. The official shootout winner still advances in the tournament bracket.

Penalty goals are stored separately and are never added to the football score used for Elo or team form.

## Progressive simulations

The simulation starts from the immutable Round-of-32 bracket.

For every knockout fixture:

- a finished official result is fixed in every simulation
- an unfinished fixture is simulated with the existing Poisson goal models
- extra time is simulated when the score is level
- penalties are simulated only when extra time remains level

This means completed knockout matches are never re-simulated.

As the tournament progresses, eliminated teams automatically receive zero probability of reaching later rounds. After the final, the official champion receives a 100% championship probability.

## New outputs

- `data/knockout_progress_latest.csv`
- expanded knockout score fields in `data/world_cup_2026_matches_latest.csv`
- knockout advancement probabilities in `data/world_cup_live_predictions_latest.csv`
- knockout-aware tournament probabilities and CupMarket prices
- `backend/state/knockout_pipeline_state.json`

## Safety rules

- Official prices are not changed while a knockout match is actively in play.
- Repeated runs cannot process the same result twice.
- Official participants are validated against the locked bracket path.
- A conflict between an official result and the bracket path stops publication.
- Input fingerprints prevent unnecessary 20,000-simulation reruns.
- Phase 2 history and Phase 3 market-impact archives are updated after a knockout result is published.
