# Live data hardening plan

This change follows the project's senior engineering and UX standard.

It consolidates live match state into one service, removes hidden runtime patching, defines how newer official result corrections are handled, enforces deterministic unit tests in GitHub Actions, uses fast refresh only around match activity, simplifies public warnings, clarifies navigation labels, and pins tested dependency versions.

The trained model, Elo logic, simulations, settlement values, and country-price formula are unchanged.
