# Official update safety rule

The live pages may continue to show current scores and provisional qualification analysis while matches are active.

The official Elo ratings, tournament probabilities, and country prices must not update while any group-stage match has status `IN_PLAY` or `PAUSED`.

When that happens, the scheduled backend run records a safe deferral and exits before the official pipeline starts. The normal 15-minute schedule retries automatically.
