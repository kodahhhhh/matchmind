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
  of 0, +1 and +2 cents on identical quoted-price signals, entry minutes and
  fixed cash stakes. These isolate cost without changing entry selection. Historical prices are trades, not executable asks.
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
  Use the latest corroborating jump offset and exclude entries for three
  minutes after an already-observed regulation goal. Future goals never
  suppress an entry. Goal-free halves fail this strict audit.
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

Generated: `2026-10-03T23:50:05.765019+00:00`.

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
| polymarket-0c | 14 | 42 | 4200.00 | +2552.65 | 60.78% | [-1.98%, 122.99%] | 54.76% | 146.15 | 12552.65 |
| polymarket-1c | 14 | 42 | 4200.00 | +2305.58 | 54.89% | [-4.89%, 113.58%] | 54.76% | 148.48 | 12305.58 |
| polymarket-2c | 14 | 42 | 4200.00 | +2080.04 | 49.52% | [-8.01%, 105.64%] | 54.76% | 150.75 | 12080.04 |

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
| Slovakia – Ukraine (sb:3938640) | 164795.60 | +187 | +1195 | 3 | -101.98 | -105.83 | -109.52 |
| Georgia – Czech Republic (sb:3938642) | 12733.05 | +222 | +1375 | 3 | +542.39 | +501.00 | +463.89 |
| Belgium – Romania (sb:3930175) | 301828.33 | -11 | +1081 | 3 | -100.00 | -103.92 | -107.69 |
| Switzerland – Germany (sb:3930176) | 75729.00 | +71 | +1316 | 3 | +854.77 | +789.61 | +731.59 |
| Netherlands – Austria (sb:3930180) | 128255.56 | +133 | +1171 | 3 | +460.15 | +440.20 | +421.31 |
| Georgia – Portugal (sb:3938644) | 100072.58 | -87 | +1249 | 3 | +248.02 | +237.93 | +228.21 |
| Switzerland – Italy (sb:3940878) | 13917.96 | +102 | +1295 | 3 | +439.69 | +420.84 | +402.98 |
| England – Slovakia (sb:3941017) | 58461.89 | +99 | +1349 | 3 | +22.58 | +12.50 | +3.03 |
| Romania – Netherlands (sb:3941021) | 26951.30 | +175 | +1239 | 3 | -300.00 | -300.00 | -300.00 |
| Austria – Turkey (sb:3941022) | 149466.85 | -56 | +1151 | 3 | +326.07 | +312.81 | +300.11 |
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
- `uv run pytest`: 65 passed, 1 failed; all 18 W10 tests pass.
- Sole failure: `tests/test_contract.py::test_counterfactual_contract_and_quantiles`. The existing response adds horizon/anchor/series fields absent from its fixture. The counterfactual source, test and fixture have zero diff from base commit `66ea23c`; W10 does not edit another agent's files.
- Live :8030: both golden responses exactly match; 80 market responses validate; unknown match returns 404.
- 1154 series points across 14 aligned matches match the shared :8000 timeline index, period, minute and label.
- Port 8030 was stopped after acceptance; the shared port 8000 was only read, never restarted. No training workers remain.
- No frontend files changed, so no screenshot requirement applies.

Regenerate documentation/examples with `uv run python -m matchmind.backtest.report`. Verify HTTP endpoints while the dedicated test server is running with `uv run python -m matchmind.backtest.verify`.

## W12 player-informed models


Generated from artifacts: `2026-10-04T01:59:05.842550+00:00`. W12 explicitly adds a player-model workstream to the older PLAN ownership table. W11 supplies identities; W12 never changes its files.

### Features and leakage boundaries

CC0 Transfermarkt players, player_valuations, games, game_lineups, appearances and clubs are cached under `data/raw/players/transfermarkt/`. Club joins use date, both clubs and explicit name aliases, never scores. Reconstructed Bundesliga dates come from the already-validated bookmaker join. International XIs come from StatsBomb and W11 identities with confidence ≥0.8; unmatched players stay missing.

Pre-match features are home-minus-away differences and mean levels of log(1 + total XI euros), mean log(1 + player euros), log bench value, age at match date, observed earlier international appearances, value of missing usual starters, inferred new-signing share and valuation coverage. Every valuation must be dated strictly before the match; same-day values are excluded. No present-day value, caps, current club or contract snapshot enters a model.

Usual starters started at least three of the team’s previous five observed games, all dated before this match. Clubs use TM lineup history; internationals use prior StatsBomb XIs. Observed caps are the larger of prior TM and SB international appearance counts, a conservative lower bound rather than lifetime caps. Signing share is an imperfect proxy: a player’s first earlier observed appearance at this club must be within 180 days, with an earlier different club observed; established players have at least 180 days at this club. Unknowns stay missing. This is unavailable for national-team selection.

The pre-match candidate is a regularized multinomial correction to the existing walk-forward rating logits. Value, value+age and all-feature sets, with L2 penalties 10 or 100, are scored only on weeks 6–17. Each tuning round fits only earlier rounds. The correction freezes after week 17 while the original ratings continue their established previous-round updates. Missing-value medians and scales use fitting rows only. The original threshold grid and tuning-profit rule are unchanged.

The in-play candidate keeps the incumbent LightGBM parameters and adds log on-pitch value difference plus coverage. Player membership changes only after an observed substitution or on-pitch red card; bench dismissals do not remove active players. All values remain frozen at kickoff. A strength difference is missing unless both sides have values for at least 80% of current players. Strict minute boundaries, the three-minute trading lag, chronological training/calibration/validation partitions, and all tournament exclusions are unchanged.

Candidate selection and retention are distinct. Feature/parameter selection uses tuning data only. Per the requested keep-the-better-model rule, replacement requires both held-out log loss and Brier to improve. The pre-match retention gate therefore uses weeks 18–34 once; it is a post-evaluation deployment decision, not an untouched evaluation of a preselected winner. In-play retention uses the existing 2020–2022 validation partition; tournament results never decide retention. No candidates were retuned after their held-out results.

Retained pre-match: **player-informed candidate**. Retained in-play: **original model**.

Selected pre-match feature set: `value`, L2 `100.0`. Candidate threshold `0.0`, original threshold `0.0`. W11 accepted identities: 5241; TM game joins: 2457/2924.

### Held-out probability scores (lower is better)

| Partition | Predictor | Log loss | Brier |
| --- | --- | --- | --- |
| Pinnacle, weeks 18–34 | before | 0.995752 | 0.592742 |
| Pinnacle, weeks 18–34 | candidate | 0.985647 | 0.584927 |
| Pinnacle, weeks 18–34 | retained | 0.985647 | 0.584927 |
| Pinnacle, weeks 18–34 | market | 0.967149 | 0.573955 |
| In-play validation | before | 0.775768 | 0.457439 |
| In-play validation | candidate | 0.866299 | 0.487824 |
| In-play validation | score_only_baseline | 0.772346 | 0.456493 |
| In-play validation | retained | 0.775768 | 0.457439 |
| All excluded tournament minute rows | before | 0.820001 | 0.485925 |
| All excluded tournament minute rows | candidate | 0.913713 | 0.527870 |
| All excluded tournament minute rows | score_only_baseline | 0.821761 | 0.486576 |
| All excluded tournament minute rows | retained | 0.820001 | 0.485925 |

### Polymarket checkpoint scores

Same aligned cohort and three-minute information lag. Market is normalized three-way historical trade prices; executable mid/ask quotes are unavailable.

| Minute | Matches | Predictor | Log loss | Brier |
| --- | --- | --- | --- | --- |
| 15 | 14 | before | 1.035759 | 0.621732 |
| 15 | 14 | candidate | 0.979784 | 0.609267 |
| 15 | 14 | retained | 1.035759 | 0.621732 |
| 15 | 14 | market | 1.016482 | 0.639074 |
| 30 | 14 | before | 0.975960 | 0.577464 |
| 30 | 14 | candidate | 0.912220 | 0.544694 |
| 30 | 14 | retained | 0.975960 | 0.577464 |
| 30 | 14 | market | 1.130360 | 0.700035 |
| 45 | 14 | before | 0.964061 | 0.581174 |
| 45 | 14 | candidate | 0.914988 | 0.549491 |
| 45 | 14 | retained | 0.964061 | 0.581174 |
| 45 | 14 | market | 0.834078 | 0.492893 |
| 60 | 14 | before | 0.975710 | 0.627034 |
| 60 | 14 | candidate | 0.882199 | 0.537691 |
| 60 | 14 | retained | 0.975710 | 0.627034 |
| 60 | 14 | market | 0.766568 | 0.458205 |
| 75 | 14 | before | 0.799035 | 0.524252 |
| 75 | 14 | candidate | 0.758837 | 0.468887 |
| 75 | 14 | retained | 0.799035 | 0.524252 |
| 75 | 14 | market | 0.899100 | 0.569814 |

### Before, candidate and retained backtests

Identical stake rules, threshold-selection partition, slippage scenarios, settlement and 5,000-draw seed-2026 match-cluster bootstrap. Zero-bet evaluation matches stay in the bootstrap. Candidate results remain visible even when the original is retained. Opening odds remain payout sensitivities, not executable strategies. Pinnacle units and Polymarket dollars are separate.

| Strategy | Version | Bets | P&L | ROI | ROI 95% CI | Brier |
| --- | --- | --- | --- | --- | --- | --- |
| pinnacle-closing-flat | before | 203 | -8.60 | -4.24% | [-31.88%, 29.28%] | 0.592742 |
| pinnacle-closing-flat | candidate | 187 | -10.29 | -5.50% | [-25.31%, 15.76%] | 0.584927 |
| pinnacle-closing-flat | retained | 187 | -10.29 | -5.50% | [-25.31%, 15.76%] | 0.584927 |
| pinnacle-closing-kelly | before | 203 | -401.03 | -13.55% | [-38.98%, 17.21%] | 0.592742 |
| pinnacle-closing-kelly | candidate | 187 | -280.98 | -8.88% | [-30.76%, 14.85%] | 0.584927 |
| pinnacle-closing-kelly | retained | 187 | -280.98 | -8.88% | [-30.76%, 14.85%] | 0.584927 |
| pinnacle-opening-flat | before | 203 | -10.77 | -5.31% | [-31.66%, 25.89%] | 0.592742 |
| pinnacle-opening-flat | candidate | 187 | -12.63 | -6.75% | [-25.91%, 14.23%] | 0.584927 |
| pinnacle-opening-flat | retained | 187 | -12.63 | -6.75% | [-25.91%, 14.23%] | 0.584927 |
| pinnacle-opening-kelly | before | 179 | -271.61 | -8.27% | [-35.04%, 22.74%] | 0.592742 |
| pinnacle-opening-kelly | candidate | 153 | -270.93 | -9.21% | [-35.68%, 19.32%] | 0.584927 |
| pinnacle-opening-kelly | retained | 153 | -270.93 | -9.21% | [-35.68%, 19.32%] | 0.584927 |
| polymarket-0c | before | 42 | +2552.65 | 60.78% | [-1.98%, 122.99%] | 0.586331 |
| polymarket-0c | candidate | 42 | +3189.64 | 75.94% | [14.35%, 138.56%] | 0.542006 |
| polymarket-0c | retained | 42 | +2552.65 | 60.78% | [-1.98%, 122.99%] | 0.586331 |
| polymarket-1c | before | 42 | +2305.58 | 54.89% | [-4.89%, 113.58%] | 0.586331 |
| polymarket-1c | candidate | 42 | +2913.19 | 69.36% | [11.02%, 128.09%] | 0.542006 |
| polymarket-1c | retained | 42 | +2305.58 | 54.89% | [-4.89%, 113.58%] | 0.586331 |
| polymarket-2c | before | 42 | +2080.04 | 49.52% | [-8.01%, 105.64%] | 0.586331 |
| polymarket-2c | candidate | 42 | +2660.70 | 63.35% | [7.96%, 118.92%] | 0.542006 |
| polymarket-2c | retained | 42 | +2080.04 | 49.52% | [-8.01%, 105.64%] | 0.586331 |

### Feature coverage

XI percentages use all 22 starting slots per match as denominator, including unmapped players. Live percentages additionally require a StatsBomb-to-TM identity for the starter. Entire historical competitions are shown so absent source eras cannot disappear from the denominator.

| Competition | Season | Matches | TM games | XI identities | Valued XI | Live valued XI |
| --- | --- | --- | --- | --- | --- | --- |
| 1. Bundesliga | 2015/2016 | 306 | 306 | 100.0% | 100.0% | 99.6% |
| 1. Bundesliga | 2023/2024 | 34 | 34 | 100.0% | 100.0% | 100.0% |
| African Cup of Nations | 2023 | 52 | 0 | 70.8% | 68.0% | 68.0% |
| Champions League | 1970/1971 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| Champions League | 1971/1972 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| Champions League | 1972/1973 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| Champions League | 1999/2000 | 1 | 0 | 13.6% | 0.0% | 0.0% |
| Champions League | 2003/2004 | 1 | 0 | 45.5% | 0.0% | 0.0% |
| Champions League | 2004/2005 | 1 | 0 | 31.8% | 31.8% | 31.8% |
| Champions League | 2006/2007 | 1 | 0 | 54.5% | 54.5% | 54.5% |
| Champions League | 2008/2009 | 1 | 0 | 77.3% | 77.3% | 77.3% |
| Champions League | 2009/2010 | 1 | 0 | 72.7% | 72.7% | 72.7% |
| Champions League | 2010/2011 | 1 | 0 | 86.4% | 86.4% | 86.4% |
| Champions League | 2011/2012 | 1 | 0 | 95.5% | 95.5% | 95.5% |
| Champions League | 2012/2013 | 1 | 1 | 100.0% | 100.0% | 100.0% |
| Champions League | 2013/2014 | 1 | 1 | 100.0% | 100.0% | 100.0% |
| Champions League | 2014/2015 | 1 | 1 | 100.0% | 100.0% | 100.0% |
| Champions League | 2015/2016 | 1 | 1 | 100.0% | 100.0% | 100.0% |
| Champions League | 2016/2017 | 1 | 1 | 100.0% | 100.0% | 100.0% |
| Champions League | 2017/2018 | 1 | 1 | 100.0% | 100.0% | 100.0% |
| Champions League | 2018/2019 | 1 | 1 | 100.0% | 100.0% | 100.0% |
| Copa America | 2024 | 32 | 32 | 95.3% | 94.3% | 94.3% |
| Copa del Rey | 1977/1978 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| Copa del Rey | 1982/1983 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| Copa del Rey | 1983/1984 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| FIFA U20 World Cup | 1979 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| FIFA World Cup | 1958 | 2 | 0 | 0.0% | 0.0% | 0.0% |
| FIFA World Cup | 1962 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| FIFA World Cup | 1970 | 6 | 0 | 0.0% | 0.0% | 0.0% |
| FIFA World Cup | 1974 | 6 | 0 | 0.0% | 0.0% | 0.0% |
| FIFA World Cup | 1986 | 3 | 0 | 0.0% | 0.0% | 0.0% |
| FIFA World Cup | 1990 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| FIFA World Cup | 2018 | 64 | 64 | 87.1% | 86.6% | 86.6% |
| FIFA World Cup | 2022 | 64 | 64 | 89.6% | 89.1% | 89.1% |
| Indian Super league | 2021/2022 | 115 | 0 | 29.0% | 19.9% | 19.9% |
| La Liga | 1973/1974 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| La Liga | 2004/2005 | 7 | 0 | 35.7% | 29.9% | 29.9% |
| La Liga | 2005/2006 | 17 | 0 | 40.1% | 36.9% | 36.9% |
| La Liga | 2006/2007 | 26 | 0 | 47.0% | 46.2% | 46.2% |
| La Liga | 2007/2008 | 28 | 0 | 56.3% | 53.7% | 53.7% |
| La Liga | 2008/2009 | 31 | 0 | 68.9% | 68.8% | 68.8% |
| La Liga | 2009/2010 | 35 | 0 | 78.2% | 77.5% | 77.5% |
| La Liga | 2010/2011 | 33 | 0 | 88.0% | 87.6% | 87.6% |
| La Liga | 2011/2012 | 37 | 0 | 92.4% | 91.6% | 91.6% |
| La Liga | 2012/2013 | 32 | 32 | 93.5% | 93.5% | 93.5% |
| La Liga | 2013/2014 | 31 | 31 | 100.0% | 99.7% | 99.7% |
| La Liga | 2014/2015 | 38 | 38 | 100.0% | 99.6% | 99.6% |
| La Liga | 2015/2016 | 380 | 380 | 100.0% | 99.5% | 99.5% |
| La Liga | 2016/2017 | 34 | 34 | 100.0% | 99.9% | 99.9% |
| La Liga | 2017/2018 | 36 | 36 | 100.0% | 100.0% | 100.0% |
| La Liga | 2018/2019 | 34 | 34 | 99.5% | 99.5% | 99.5% |
| La Liga | 2019/2020 | 33 | 33 | 100.0% | 100.0% | 99.9% |
| La Liga | 2020/2021 | 35 | 35 | 100.0% | 100.0% | 100.0% |
| Liga Profesional | 1981 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| Liga Profesional | 1997/1998 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| Ligue 1 | 2015/2016 | 377 | 377 | 100.0% | 99.5% | 99.5% |
| Ligue 1 | 2021/2022 | 26 | 26 | 100.0% | 100.0% | 100.0% |
| Ligue 1 | 2022/2023 | 32 | 32 | 100.0% | 99.9% | 99.9% |
| Major League Soccer | 2023 | 6 | 0 | 80.3% | 79.5% | 79.5% |
| North American League | 1977 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| Premier League | 2003/2004 | 38 | 0 | 23.1% | 0.0% | 0.0% |
| Premier League | 2015/2016 | 380 | 380 | 100.0% | 99.6% | 99.6% |
| Serie A | 1986/1987 | 1 | 0 | 0.0% | 0.0% | 0.0% |
| Serie A | 2015/2016 | 380 | 380 | 100.0% | 100.0% | 99.7% |
| UEFA Euro | 2020 | 51 | 51 | 92.0% | 91.6% | 91.6% |
| UEFA Euro | 2024 | 51 | 51 | 91.7% | 91.2% | 91.2% |
| UEFA Europa League | 1988/1989 | 3 | 0 | 0.0% | 0.0% | 0.0% |

### Limitations and integration

Valuations are noisy estimates, not player ability or transfer prices. Historical rows were downloaded today and may have been retrospectively revised; strict dates do not establish archived publication vintages. W11 matching confidence is a heuristic, not a calibrated probability. Incomplete identities and valuations can bias summed strengths downward. The 80% live coverage guard limits but does not eliminate this. Missing history is not evidence of no international experience or no absences. First observed club appearances are not verified signing dates. Current lifetime caps are deliberately excluded.

The game-state model and its API are unchanged; the optional quantile experiment was not run. No claim of improved pinball loss or coverage is made. The same small selected Polymarket cohort, retrospective goal alignment and unproven fills remain material limitations. No new profitability conclusion can rely on paper P&L alone.

The requested additive `comparison` and `model_versions` fields live in the strict backtest schema. All old fields and market response shapes remain. W12 writes served artifacts under `data/processed/backtest/w12/`; the new route prefers them. This prevents the old shared process from reading a payload its older strict schema rejects. The orchestrator must merge and reload the API to expose W12 on :8000. W12 does not restart it. The two authorized backend golden snapshots are regenerated; fixtures/ remains orchestrator-owned and needs the corresponding additive update.

Reproduce: `DATA_DIR=/home/ubuntu/hackathon/data uv run --group models python -m matchmind.backtest squads`, then `python -m matchmind.backtest.squad_report`. The immutable `w12_before/` snapshot preserves original scores, predictions, strategy results and model bundle. Candidate predictions, candidate backtests, complete join/coverage audits and model JSON cards remain beside it. Models and data are gitignored.

Verification is recorded in `data/processed/backtest/w12/verification.json`; run the full suite plus `pytest matchmind/backtest/test_squads.py`. Use :8050 for acceptance and stop it afterwards.

Executed acceptance: 101 passed, 4 dependency deprecation warnings; owned-file lint/format passed; 80 market responses and 1154 series points verified on :8050. 81 original served artifacts remain byte-identical. Acceptance server stopped; shared :8000 never restarted.
