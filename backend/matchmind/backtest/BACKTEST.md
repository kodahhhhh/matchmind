# W10 market backtest

This task explicitly reassigns the PLAN.md W10 frontend slot to market research.
Only the new backtest package, new route module and W10 tests are owned here.
The main API registration and frontend belong to the orchestrator.

## Frozen protocol (before evaluation profits are calculated)

- Use the complete 306-match Bundesliga 2015/16 season; validate team names,
  home/away, final scores, chronological nine-match rounds and available source
  round metadata. Missing dates come from the odds CSV, never synthetic DB dates.
- An upstream model that excludes a match but includes future seasons is not a
  historical forecast. Regenerate our xG and VAEP with separate models trained
  only on the 397 dated matches before 2015-08-01. The existing shuffled OOF app
  artifacts are read-only and are not substituted for causal feature provenance.
  Every rating / result-training / calibration / validation / backtest match is
  outside this upstream fit. This is stricter than random-match cross-fitting.
- Poisson team attack/defence ratings shrink toward historical league rates.
  Priors start at 1.5 home / 1.2 away goals, then update from preceding rounds.
  Each complete round is predicted atomically before any of its results enter
  ratings. Grid: decay {0.85, 0.95}, prior games {3, 8}, xG weight {0.5, 1.0}.
  Select minimum log loss on weeks 6–17; select an edge threshold from
  {0, .05, .10, .20} by maximum flat-stake profit on that same tuning partition.
  Weeks 1–5 warm up; weeks 18–34 are untouched evaluation.
- Pinnacle decisions use closing odds. Flat stakes are one unit; quarter-Kelly
  stakes use (p*odds-1)/(odds-1)/4, capped at 5% of start-of-round bankroll.
  Reserve all round stakes before settlement, with a total bankroll cap.
  Start with 1,000 units. No within-round reinvestment.
- Opening prices lack collection timestamps. A close-selected bet cannot be
  retroactively executed at the opening price. Opening rows are **payout
  sensitivity only**, explicitly excluded from claims of historical earnings.
  Closing-price CLV is zero by construction; sensitivity CLV is open/close-1.
- In-play features: minute, period, both scores and score difference, red cards,
  cumulative xG, recent five-minute xG/VAEP rates, international-match flag.
  Only actions strictly before the minute boundary are included. Regulation
  labels count goals and own goals in periods 1–2; ignore extra time/shootouts.
- Result-model training: post-upstream matches before 2018, including the fully
  dated 2015/16 Bundesliga reconstruction. Temperature calibration: 2018–19,
  held out from classifier fitting. Validation: 2020 to 2022-10-31. Every World
  Cup 2022, Euro 2024 and Copa América 2024 match is held out from all these fits.
  Same classifier parameters and separate calibration for the minute/score
  baseline. No tournament performance is used to choose the model.
- Polymarket protocol: fixed 10 percentage-point probability edge, actual YES
  or actual NO token history, $100 cash per bet, one position per outcome market,
  hold to resolution, no entries after 85 minutes, no fees assumed. Run costs
  of 0, +1 and +2 cents with the same fixed threshold. Slippage may change which
  first signal qualifies. Historical prices are trades, not executable asks.
- Match by teams and date; read each market's resolution description. Exclude
  qualification, trophy, extra-time and ambiguous knockout contracts. Group
  matches cannot go to extra time. Check the source's resolved outcome against
  regulation labels and fail closed on discrepancies.
- Do not assume StatsBomb kickoff timezone. Cross-check candidate interpretations
  against independent UTC market start metadata. Euro/Copa catalogue clocks in
  this dataset generally already match UTC, contradicting a universal local-time
  assumption. Require score-direction price jumps in **both** halves. Fit
  halftime separately, permitting at most 120 seconds' dispersion between goal
  offsets within each half. Missing/ambiguous alignment drops the whole match.
  Goal-based alignment is retrospective data QA, never optimization of profits.
  Use the latest corroborating jump offset and exclude entries within three
  minutes of every regulation goal. Goal-free halves fail this strict audit.
- Use model information deliberately lagged three match-clock minutes to absorb
  minute-sampling and alignment uncertainty; no entries in the first three
  minutes of either half. This conservative rule is fixed before P&L evaluation.
- Prices are strictly backward as-of with a 90-second staleness limit; no forward
  interpolation. Use the same period/minute -> index map as the real timeline.
- Multiclass Brier sums three squared errors (range 0–2); log loss is natural log.
  Score every Pinnacle evaluation match, including those without a bet.
  In-play score both model and normalized market probabilities at 15/30/45/60/75;
  45 means first-half boundary. Trading uses unnormalized individual token prices.
- ROI intervals: deterministic seed 2026, 5,000 match-cluster bootstrap draws,
  including zero-bet evaluation matches and keeping correlated same-match bets
  together. Kelly intervals condition on realized stakes, not retrained/reoptimized
  bankroll paths. Equity/drawdown are settled weekly/daily, not mark-to-market.
- No test-set tuning, no live trades, no mutation of provider accounts or shared DB.

## Reproduction and integration

```sh
cd backend
uv sync --group models
export DATA_DIR=/home/ubuntu/hackathon/data
uv run python -m matchmind.backtest fetch
uv run python -m matchmind.backtest train
uv run python -m matchmind.backtest run
# Or: uv run python -m matchmind.backtest all
```

All raw HTTP responses, including failures, are cached once under
`data/raw/markets/{football-data,polymarket,kalshi}/`, keyed by full request URL.
The client sleeps at least 260ms between request starts. Existing responses are
never re-fetched. Processed results live in `data/processed/backtest/`; W10 models
have the `data/models/backtest_` prefix and sibling JSON provenance/metrics.
All data/model artifacts remain gitignored. Model dependencies already existed;
no dependency or lockfile edits are needed.

The dedicated acceptance app is `matchmind.api.routes.backtest:app` on port 8030.
The orchestrator must register `matchmind.api.routes.backtest.router` with `/api`
in the shared app. Routes only read precomputed JSON. They never fit models or
make source requests. Copy `backend/tests/golden/{backtest,market}_example.json`
to fixtures when integrating; response models live in `backtest/contracts.py`
to avoid editing the shared schemas module during parallel work.

## Measured results

Pending pipeline completion. This section will be populated from saved artifacts,
without altering the protocol in response to evaluation performance.
