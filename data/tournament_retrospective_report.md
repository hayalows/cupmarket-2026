# CupMarket 2026 Tournament Retrospective

**Champion:** Spain  
**Archive:** `cupmarket-2026-final`  
**Generated:** 2026-08-01T05:00:22.683944+00:00  
**Source commit:** `4bcdde1`

## Executive summary

- The completed tournament contained **104 matches** and **302 counted goals** across 100 matches with reliable goal scores.
- The goal-scored matches averaged **3.02 goals**, with 5 extra-time matches and 4 penalty shootouts.
- The strongest descriptive performers were **Argentina, Spain, France, England, Mexico**; this ranking rewards progress, group performance, Elo and goal difference after the event.
- The primary pre-match scorecard covered **100 matches** at 66.0% accuracy, Brier 0.507, and log loss 0.866.

## Tournament record

Home wins: **50**. Draws or penalty-regulation ties: **24**. Away wins: **30**.
The largest recorded score margin was **Germany 7-1 Curaçao**.

## Teams that performed well

| Team | Finish | Group points | Group GD | Goals | Final market | Performance index |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Argentina | Runner-up | 9 | 7 | 19 | 96.55 | 95.06 |
| Spain | Champion | 7 | 5 | 14 | 119.08 | 90.18 |
| France | Fourth place | 9 | 8 | 20 | 80.53 | 86.96 |
| England | Third place | 7 | 4 | 20 | 81.11 | 81.38 |
| Mexico | Round of 16 | 9 | 6 | 10 | 44.98 | 67.51 |
| Switzerland | Quarter-final | 7 | 4 | 10 | 63.54 | 63.30 |
| Morocco | Quarter-final | 7 | 3 | 9 | 62.64 | 62.76 |
| Brazil | Round of 16 | 7 | 6 | 10 | 44.36 | 61.43 |

## Model verdict

The baseline scorecard covered **28 matches**. The adaptive comparison covered **28 matches**.
Adaptive versus baseline Brier delta: **+0.0021**. Log-loss delta: **+0.0017**.
A positive delta is worse. Adaptive nudges therefore did not beat the saved baseline in this sample, although the regression remained inside the published rollback guardrail.

## Correlations

These are descriptive associations, not causal claims. Market correlations are partly expected because settlement values incorporate tournament outcomes.

| Relationship | Sample | Pearson | Spearman |
| --- | ---: | ---: | ---: |
| Opening market price vs group-stage points | 48 | +0.753 | +0.753 |
| Opening market price vs descriptive performance index | 48 | +0.853 | +0.809 |
| Final market price vs descriptive performance index | 48 | +0.917 | +0.976 |
| Group-stage goals scored vs points | 48 | +0.727 | +0.738 |
| Group-stage goal difference vs points | 48 | +0.902 | +0.900 |
| Final Elo vs group-stage goal difference | 48 | +0.804 | +0.812 |

## Model surprises and market movement

The archive retains the lowest-probability actual outcomes and the largest event-attributed market changes so the tournament can be replayed without hindsight edits.

## Method and limitations

### Lowest-probability actual outcomes

| Match | Stage | Model call | Actual | Actual probability |
| --- | --- | --- | --- | ---: |
| Spain vs Cape Verde Islands | GROUP_STAGE | HOME_WIN | DRAW (0-0) | 9.0% |
| Ecuador vs Curaçao | GROUP_STAGE | HOME_WIN | DRAW (0-0) | 11.0% |
| England vs Ghana | GROUP_STAGE | HOME_WIN | DRAW (0-0) | 14.2% |
| South Africa vs South Korea | GROUP_STAGE | AWAY_WIN | HOME_WIN (1-0) | 18.1% |
| Ghana vs Panama | GROUP_STAGE | AWAY_WIN | HOME_WIN (1-0) | 18.3% |

### Largest recorded market moves

| Team | Price move | Move % | Event |
| --- | ---: | ---: | --- |
| Spain | +25.17 | +27.6% | Spain 1-0 Argentina |
| Germany | -23.69 | -61.2% | Germany 5-6 Paraguay |
| Ecuador | +18.31 | +181.8% | Ecuador 2-1 Germany | Curaçao 0-2 Ivory Coast |
| Iran | -17.57 | -77.8% | Colombia 0-0 Portugal | Congo DR 3-1 Uzbekistan | Jordan 1-3 Argentina | Algeria 3-3 Austria |
| Switzerland | +17.09 | +43.1% | Switzerland 4-3 Colombia |
| Morocco | +15.22 | +57.2% | Netherlands 3-4 Morocco |
| Ecuador | -15.14 | -58.8% | Ecuador 0-0 Curaçao | Tunisia 0-4 Japan |
| Norway | +14.32 | +34.5% | Brazil 1-2 Norway |

- Penalty-shootout score fields are shootout tallies in the official feed, so they are excluded from goal totals.
- The descriptive performance index ranks the completed tournament; it is not a forward-looking forecast.
- Correlation is association, not causal evidence, and market values include settlement logic tied to tournament outcomes.
- Adaptive versus baseline scoring is limited to rows carrying both probability sets and should not be generalized beyond this tournament.
- The settled forecast file uses the latest eligible pre-kickoff forecast for each match; the raw append-only ledger remains preserved separately.
- This report is a final retrospective, not a retrained production model. Any future model should be evaluated on a new tournament or a frozen historical holdout.

## Reproducibility

The archive manifest records SHA-256 hashes for the published data, history ledgers, model metadata and retrospective outputs.
