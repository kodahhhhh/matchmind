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

Generated: `2026-10-03T23:40:39.963391+00:00`.

**No reliable evidence that MatchMind beats these markets.** The primary Pinnacle closing-odds test loses money and has worse probability scores than the market. Polymarket paper P&L is positive, but all ROI intervals include zero, the cohort is selected, and historical fills are not proven.

### Coverage

- Football-data: 306/306 Bundesliga 2015/16 rows join, zero unmatched catalogue rows, all final scores agree. Evaluation: 153 matches. 2023/24: 34/34 catalogue matches join; 272 CSV rows intentionally have no corresponding catalogue match. No incomplete-league betting result.
- Polymarket: 97 candidate event/match pairs across 80 demo matches; 64 regulation-market events survive contract/clock checks; 14 pass both-half alignment and settlement checks.
- Discovery combines all 187 dated post-2015/16 demo match searches, tournament searches and paginated date-bounded archives. One broad USA/Bolivia query hits the ten-page safety cap; archive and tournament passes supplement it. This is discovered public coverage, not proof that no other historical contracts existed.
- Archive pagination uses 100 rows: Gamma silently caps larger limits. The full 2015/16 archive date range returns zero events, covering the 306 early-season demo matches including reconstructed undated ones.
- Kalshi: zero matching demo markets. Current historical-date query returns eight unrelated Robinhood contracts. Eight relevant historical football series return 3,081 contracts, none before September 2024. The historical endpoint does not support date filters: unsupported parameters were found to be ignored, so the audit uses its documented series filter and exhausts cursors instead.

| Discovered competition | Matches |
| --- | ---: |
| Copa America | 26 |
| FIFA World Cup | 6 |
| UEFA Euro | 48 |

| Kalshi archived series | Contracts | Earliest close |
| --- | ---: | --- |
| KXWCGAME | 312 | 2026-06-11T21:07:29Z |
| KXUEFAGAME | 0 | none |
| KXCOPAAMERICA | 0 | none |
| KXUEFAEURO | 0 | none |
| KXBUNDESLIGAGAME | 933 | 2025-08-23T14:52:49.123422Z |
| KXMLSGAME | 1770 | 2025-05-29T02:23:07.119103Z |
| KXWC | 0 | none |
| KXMENWORLDCUP | 66 | 2025-12-05T16:39:09.846503Z |

### Betting results

Pinnacle units and Polymarket dollars are separate. ROI = P&L / total staked, not bankroll growth. Confidence intervals are match-cluster bootstrap percentiles. Drawdown uses settled weekly/daily balances.

| Strategy | Matches | Bets | Staked | P&L | ROI | ROI 95% CI | Hit rate | Max drawdown | Final bankroll |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| pinnacle-closing-flat | 153 | 203 | 203.00 | -8.60 | -4.24% | [-31.88%, 29.28%] | 26.11% | 30.83 | 991.40 |
| pinnacle-closing-kelly | 153 | 203 | 2959.43 | -401.03 | -13.55% | [-38.98%, 17.21%] | 26.11% | 604.71 | 598.97 |
| pinnacle-opening-flat | 153 | 203 | 203.00 | -10.77 | -5.31% | [-31.66%, 25.89%] | 26.11% | 31.54 | 989.23 |
| pinnacle-opening-kelly | 153 | 179 | 3282.70 | -271.61 | -8.27% | [-35.04%, 22.74%] | 26.26% | 638.93 | 728.39 |
| polymarket-0c | 14 | 42 | 4200.00 | +2370.28 | 56.44% | [-5.09%, 117.76%] | 54.76% | 146.15 | 12370.28 |
| polymarket-1c | 14 | 42 | 4200.00 | +2190.85 | 52.16% | [-7.00%, 110.78%] | 54.76% | 148.48 | 12190.85 |
| polymarket-2c | 14 | 42 | 4200.00 | +2163.04 | 51.50% | [-4.02%, 106.49%] | 57.14% | 150.75 | 12163.04 |

**Opening rows are payout sensitivities, not executable backtests.** They use the closing-selected cohort. Opening Kelly stakes additionally drop selected outcomes with nonpositive opening edge; that does not turn them into a valid opening-time strategy.

| Pinnacle strategy | Mean quote CLV (odds/closing odds - 1) |
| --- | ---: |
| pinnacle-closing-flat | 0.0000% |
| pinnacle-closing-kelly | 0.0000% |
| pinnacle-opening-flat | 0.2389% |
| pinnacle-opening-kelly | 1.5578% |

Frozen tuning selection: `{'decay': 0.95, 'prior': 8.0, 'xg_weight': 1.0, 'log_loss': 1.0352481460081682}`; edge threshold `0.0`. Tuning candidates and scores are saved in `prematch_selection.json`; no evaluation result selected them.

### Model validation

| Split | Matches | Minute rows |
| --- | ---: | ---: |
| train | 1876 | 172592 |
| calibration | 132 | 12144 |
| validation | 259 | 23828 |
| backtest | 147 | 13524 |

The 397 upstream matches contain 850,897 regulation SPADL actions for the historical VAEP fit. They are excluded from all result-model partitions. The remaining 113 corpus matches have unusable dates or occur after the validation cutoff outside the held-out tournaments, and are excluded. No all-corpus final model is substituted into backtest predictions.

The `international` feature is the literal metadata predicate `country == "International"`; continent-labelled tournaments do not receive that flag. There are no identity, odds or terminal-score features. No game-state forecast is used because its final fit includes demo matches.

| Evaluation | Predictor | Brier | Log loss |
| --- | --- | ---: | ---: |
| Pinnacle evaluation, all 153 matches | model | 0.592742 | 0.995752 |
| Pinnacle evaluation, all 153 matches | market | 0.573955 | 0.967149 |
| 259 held-out 2020–2022 training-corpus matches | model | 0.457439 | 0.775768 |
| 259 held-out 2020–2022 training-corpus matches | baseline | 0.456493 | 0.772346 |

The richer in-play model does **not** improve on its minute/score baseline on the untouched validation split. Temperature calibration fits only the separate 132-match calibration partition: model = 1.074960, baseline = 1.106086.

| Market-clock minute | Matches | Model Brier | Market Brier | Model log loss | Market log loss |
| --- | ---: | ---: | ---: | ---: | ---: |
| 15 | 14 | 0.621732 | 0.639074 | 1.035759 | 1.016482 |
| 30 | 14 | 0.577464 | 0.700035 | 0.975960 | 1.130360 |
| 45 | 14 | 0.581174 | 0.492893 | 0.964061 | 0.834078 |
| 60 | 14 | 0.627034 | 0.458205 | 0.975710 | 0.766568 |
| 75 | 14 | 0.524252 | 0.569814 | 0.799035 | 0.899100 |

Market-clock scoring uses the same conservative three-minute model-information lag as trading. These scores measure probability accuracy; the small checkpoint sample does not establish calibration.

### Per-match Polymarket paper P&L and alignment

Offsets are seconds added to `kickoff_utc + displayed_minute*60`. The second-half offset includes stoppage and halftime. Negative first-half offsets reveal timestamp ambiguity; the three-minute feature lag and goal embargo reduce its impact but cannot validate an executable historical fill. Market volume is lifetime event volume, not available depth at entry.

| Match | Volume | Half 1 offset | Half 2 offset | Bets | P&L 0¢ | P&L +1¢ | P&L +2¢ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Slovenia – Denmark (sb:3930162) | 6584.93 | +86 | +996 | 3 | -100.00 | -103.92 | -107.69 |
| Croatia – Albania (sb:3930167) | 53477.20 | +47 | +1159 | 3 | +707.12 | +652.85 | +604.57 |
| Germany – Hungary (sb:3930168) | 184065.10 | +19 | +1183 | 3 | -300.00 | -300.00 | -300.00 |
| Slovakia – Ukraine (sb:3938640) | 164795.60 | +187 | +1195 | 3 | -130.51 | -133.33 | -136.07 |
| Georgia – Czech Republic (sb:3938642) | 12733.05 | +222 | +1375 | 3 | +542.39 | +501.00 | +463.89 |
| Belgium – Romania (sb:3930175) | 301828.33 | -11 | +1081 | 3 | -100.00 | -103.92 | +84.62 |
| Switzerland – Germany (sb:3930176) | 75729.00 | +71 | +1316 | 3 | +854.77 | +789.61 | +731.59 |
| Netherlands – Austria (sb:3930180) | 128255.56 | +133 | +1171 | 3 | +306.30 | +293.21 | +280.71 |
| Georgia – Portugal (sb:3938644) | 100072.58 | -87 | +1249 | 3 | +248.02 | +294.17 | +282.63 |
| Switzerland – Italy (sb:3940878) | 13917.96 | +102 | +1295 | 3 | +439.69 | +420.84 | +402.98 |
| England – Slovakia (sb:3941017) | 58461.89 | +99 | +1349 | 3 | +22.58 | +12.50 | +3.03 |
| Romania – Netherlands (sb:3941021) | 26951.30 | +175 | +1239 | 3 | -300.00 | -300.00 | -300.00 |
| Austria – Turkey (sb:3941022) | 149466.85 | -56 | +1151 | 3 | +326.07 | +316.33 | +303.53 |
| Netherlands – England (sb:3942819) | 51153.29 | +148 | +1202 | 3 | -146.15 | -148.48 | -150.75 |

Every aligned match here is from Euro 2024. None of the 19 eligible Copa events passes both-half alignment. World Cup matches are excluded before price execution because usable UTC clocks or compatible regulation-only contracts are absent.

| Exclusion at alignment stage | Matches |
| --- | ---: |
| No usable goal in period 1 to verify the clock | 26 |
| No clear goal-direction price jump in period 1 | 7 |
| No usable goal in period 2 to verify the clock | 7 |
| No clear goal-direction price jump in period 2 | 2 |
| Inconsistent goal offsets in period 1 | 6 |
| Inconsistent goal offsets in period 2 | 2 |

### Auditable artifacts

- `backtest.json`: complete strategy summaries, every bet and all bankroll curves; schema-valid fixture copy in `backend/tests/golden/backtest_example.json`.
- `market_sb_*.json`: 80 discovered-match API artifacts, including unaligned empty series for excluded markets. An aligned full response is copied to `backend/tests/golden/market_example.json`.
- `bookmaker_coverage.json`: explicit unmatched CSV/catalogue rows; `bookmaker_1516.json` and `bookmaker_2324.json`: validated joins.
- `polymarket_search_audit.json`, `polymarket_supplemental_audit.json`, `polymarket_archive_audit.json`: request coverage and bounded-search limits.
- `polymarket_resolution_audit.json`: every candidate market question, full resolution description, volume, clock interpretation and exclusion.
- `polymarket_alignment.json`: every candidate offset, matched goal jump, within-period consistency result and rejection reason.
- `polymarket_diagnostics.json`: checkpoint scores and per-match P&L for every cost assumption; `kalshi_coverage.json`: archive evidence.
- `data/models/backtest_*.json`: upstream cutoffs, training IDs, data sizes and held-out validation metrics.

### Limits and integration boundary

This is a retrospective research pipeline built today with old observations, not a forecast recorded before those games. Training and feature cutoffs prevent outcome leakage, but neither market archive coverage nor trade executability can be reconstructed perfectly. Tournament availability, goal-based alignment and liquidity checks select a nonrepresentative cohort. The bootstrap does not repair selection bias or account for all model uncertainty. No positive historical profit claim should omit these qualifications.

The frozen 2015 upstream models are deliberately old and trained on a selected corpus. Cross-era and club-to-international shifts are material. The full 2023/24 league is unavailable. The model loses to the market in aggregate Brier and log loss, so positive paper P&L in a small subgroup is not evidence of general superiority.

No shared API source or running port-8000 service is changed. The orchestrator must register the new router and copy fixtures. Tests of the owned package and real artifact endpoints are recorded below. The inherited counterfactual fixture mismatch is outside W10 ownership and must be resolved by the counterfactual workstream.

### Verification

- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed (71 Python files).
- `uv run pytest`: 63 passed, 1 failed; all 16 W10 tests pass.
- Sole failure: `tests/test_contract.py::test_counterfactual_contract_and_quantiles`. The existing response adds horizon/anchor/series fields absent from its fixture. The counterfactual source, test and fixture have zero diff from base commit `66ea23c`; W10 does not edit another agent's files.
- Live :8030: both golden responses exactly match; 80 market responses validate; unknown match returns 404.
- 1154 series points across 14 aligned matches match the shared :8000 timeline index, period, minute and label.
- Port 8030 was stopped after acceptance; the shared port 8000 was only read, never restarted. No training workers remain.
- No frontend files changed, so no screenshot requirement applies.

Regenerate documentation/examples with `uv run python -m matchmind.backtest.report`. Verify HTTP endpoints while the dedicated test server is running with `uv run python -m matchmind.backtest.verify`.
