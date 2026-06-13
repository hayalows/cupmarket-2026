# Live score pages

The Match Intelligence and Qualification Lab pages use the Streamlit `FOOTBALL_DATA_TOKEN` to request current World Cup match states from football-data.org.

- Score data is cached for 60 seconds.
- If the API or token is unavailable, the pages fall back to the latest saved GitHub match snapshot.
- Match probabilities remain the latest published model outputs.
- The interface clearly reports when a finished result is visible in the live feed but is still waiting for the model workflow.
- Qualification standings are recalculated from the current score source.
