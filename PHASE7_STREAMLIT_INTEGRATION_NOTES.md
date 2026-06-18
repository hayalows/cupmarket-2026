# Phase 7 Streamlit integration

Phase 7 exposes the backend work from Phases 2 through 6 without changing pricing, Elo, simulations or automation logic.

## New Tournament Path page

The new page answers four user questions in order:

1. Where is my country now?
2. Is its path projected, partly confirmed or official?
3. Who can it face next?
4. What match event changed its CupMarket value?

It combines:

- current CupMarket price and tournament probabilities
- projected or confirmed Round-of-32 opponents
- exact Phase 5 bracket information
- Phase 6 knockout results, extra time, penalties and advancing teams
- Phase 3 event-level market movement
- official price history

## Progressive states

The page works before and after the new output files exist.

- No path file: a clear waiting state is shown.
- Group stage active: opponent paths are labelled projected.
- Slot fixed: the country slot is shown while the opponent remains pending.
- Bracket locked: the official opponent is shown.
- Knockout stage active: completed, live and upcoming knockout matches are summarised.
- Eliminated: the country receives an explicit eliminated state.

Missing files never produce a blank or broken page.

## Navigation

Tournament Path is available from:

- the specialist sidebar
- the Tournament Pulse page
- Market Story, while preserving the selected country

## Official data loading

The new UI files use the same commit-pinned GitHub loader as the existing market pages. The following outputs were added to the allow-list:

- Round-of-32 path status
- opponent probabilities
- official bracket lock
- knockout progress
- latest market movement
- team snapshots
- bracket and opponent metadata

This keeps related official outputs tied to a published GitHub state while retaining the deployed local fallback.

## UX safeguards

- One new page instead of several new navigation items
- plain-language fixture states
- explanation of conditional opponent probabilities
- mobile-friendly Streamlit containers and tables
- empty states for every future-dependent section
- official source caption and snapshot reference
- no automatic score refresh on the analysis-heavy page
