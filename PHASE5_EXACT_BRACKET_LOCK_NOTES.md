# Phase 5 exact Round-of-32 bracket lock

Phase 5 replaces projected opponent paths with official fixtures only after the following conditions are all true:

1. All 72 group-stage matches are finished and have full-time scores.
2. The official football API contains exactly 16 Round-of-32 fixtures.
3. Every Round-of-32 fixture has two resolved team names.
4. The bracket contains exactly 32 unique teams.
5. Every knockout team appears in the final group tables.

The lock uses the populated official API fixtures as the source of truth. It does not guess the final best-third allocation.

New outputs:

- `data/official_round_32_bracket_locked.csv`
- `data/official_round_32_bracket_lock.json`

After locking, Phase 4 projection files are replaced with confirmed values:

- each qualified team has one opponent at 100%
- each confirmed path is labelled `confirmed`
- the other 16 teams are labelled `eliminated`
- bracket mode becomes `official_api_locked`

The bracket lock is immutable. Re-running with the same fixtures is idempotent. A later API response that conflicts with the saved lock raises an error instead of silently rewriting the tournament bracket.

The automation runs the lock as a separate step after the normal model update. This allows it to detect official fixtures on a later API refresh even when no new match finished during that run.

Use `ENABLE_EXACT_BRACKET_LOCK=false` to disable the lock step without changing the live model pipeline.
