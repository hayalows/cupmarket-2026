# Live score upgrade checklist

- Match Intelligence reads the live football-data.org feed when the Streamlit token is available.
- Qualification Lab rebuilds the current group table from the same score feed.
- Both pages fall back to the saved GitHub snapshot when the live request fails.
- Published model probabilities remain unchanged until the automated workflow completes.
- The pages show how many finished group matches are visible but not yet reflected in the published model.
