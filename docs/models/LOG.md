# W14 models v2 log

## Needs owner

**Recommend orchestrator review of `goals-v2` only.** It improves both goal-rate
targets and block-result proper scores after repairing indirect upstream leakage.
Never promote `goals-v1` or `gamestate-v1`: their original validation was invalid.
Production promotion remains orchestrator-owned; exact steps are in PROMOTION.md.

Optional data need: W13 stopped Wyscout/Figshare after HTTP 403. A licensed local
copy could broaden event coverage; no blocking evasion or W14 fetching is planned.
W13 has supplied 37 accepted Dynasty youth matches for a separate transfer test.

## Protocol — 2026-10-05

- Worktree: `ws/W14-models`. All experimental files go below configured
  `DATA_DIR/models/candidates/`; existing artifacts and the DB stay read-only.
- First capture every incumbent model card, clearly separating historical reports
  from newly reproduced metrics. Saved splits and input hashes must precede fits.
- In-play: retain the existing pre-2018 classifier training partition and frozen
  pre-August-2015 upstream xG/VAEP. Use 2018 to choose recipes, 2019 for calibration,
  and 2020–2022-10-31 once for evaluation. Tournaments are secondary external
  evaluation, never selection. Bootstrap entire matches, not minute rows.
- xG: grouped nested selection only; incumbent fold artifacts are legitimate
  held-out comparators. Never score the final all-corpus fit as held out.
- Goals/game-state must retain fold-rebuilt upstream windows. Pass completion
  requires rebuilding features: the original trainer saved no held-out artifact.
- Player ratings and xT are derived estimators, without independent supervised
  targets. Report downstream validation and ranking checks, not invented accuracy.
- Training: `nice -n 10`, at most 8 threads, under 12 GB RAM. No network, backfill,
  shared service restart, or serving ports.

## Initial inspection

Read AGENTS.md, PLAN.md, models/MODELS.md, models/INTEGRATION.md and
backtest/BACKTEST.md. Configured data root is `/home/ubuntu/hackathon/data`.
The worktree started clean. Existing trainers default to production paths and
some request 16 workers, so W14 does not invoke their training entry points.
Disk free: 61 GB. W13 source log was not present at initial inspection.

Baseline inventory and fresh reproduction results will be appended below.

### Baseline inventory (historical cards, not rerun)

All cards and hashes are pinned in `candidates/baseline-v1/inventory.json`.

| Model | Metric | Incumbent |
|---|---|---:|
| xG | Log loss / Brier | 0.262877 / 0.075142 |
| VAEP scores | AUC / Brier | 0.819528 / 0.009392 |
| VAEP concedes | AUC / Brier | 0.805927 / 0.002111 |
| Game-state xG for | p10/p50/p90 loss; coverage | 0.021610 / 0.087025 / 0.063922; 0.878692 |
| Game-state xG against | p10/p50/p90 loss; coverage | 0.021610 / 0.087014 / 0.063910; 0.879106 |
| Game-state possession | p10/p50/p90 loss; coverage | 0.019245 / 0.044327 / 0.019237; 0.797842 |
| Goals next 15 | Poisson deviance / score Brier | 0.701116 / 0.154566 |
| Goals rest | Poisson deviance | 0.968718 |
| Goals block result | Brier / log loss | 0.406829 / 0.697896 |
| Pass completion | Brier / log loss | 0.064949 / 0.211769 |
| Pre-match retained squad | Brier / log loss | 0.584927 / 0.985647 |
| Pre-match market | Brier / log loss | 0.573955 / 0.967149 |
| In-play incumbent | Brier / log loss | 0.457439 / 0.775768 |
| In-play score baseline | Brier / log loss | 0.456493 / 0.772346 |
| In-play rejected squad | Brier / log loss | 0.487824 / 0.866299 |
| xT | Descriptive grid / OOF rated moves | 12×8 / 4,440,132 |
| Player ratings | Historical sanity: Messi VAEP/90, observed minutes | 0.832024 / 51,805.08 |

xT and player ratings have no independent supervised accuracy target; squad
strength is judged through the downstream pre-match/in-play evaluations.

### Fresh baseline replay and first in-play experiment

`evaluate inplay` reproduced both incumbent scores exactly on 259 validation
matches / 23,828 minute rows. `evaluate xg` re-predicted the five held-out boosters
on 73,598 non-shootout shots. All output is in `candidates/baseline-v1/`.

`inplay-v1`: six recipes fixed before evaluation; select on 99 matches in 2018,
calibrate temperature on 33 matches in 2019. All classifiers fit 1,876 pre-2018
matches; upstream xG/VAEP remains the original disjoint pre-August-2015 fit.
Selected `full7` (7 leaves, 180 trees, stronger regularization). Validation:

| Metric | Current | Candidate | Candidate-current 95% match-bootstrap CI |
|---|---:|---:|---|
| Brier | 0.457439147 | 0.457472817 | [-0.003606969, 0.003860941] |
| Log loss | 0.775767733 | 0.776516256 | [-0.006042828, 0.007996173] |

Negative result; do not promote. The selected recipe still loses to the score-only
baseline. Do not tune again on this test result. Future in-play development needs
rolling development folds and new untouched source data for confirmation.

### xG result

`xg-v1`: six frozen recipes; each outer match fold uses the next fold for inner
selection and the other three for fitting. Refit the chosen recipe on four folds,
then score the untouched outer fold against its incumbent saved booster. The
production recipe is fixed from outer-0 inner selection, never outer scores.
All five compatible fold boosters and all-corpus booster are candidate-local.

W13 log now exists; source probing/conversion has begun, no new corpus ready yet.

Point gain only: xG log loss 0.262877 → 0.262712, Brier 0.075142 → 0.075133.
Both 95% intervals include zero. Candidate held for new-data confirmation.

### Goals v1 — withdrawn, superseded by corrected v2

**These numbers are not honest held-out evidence: see the audit below.**

Frozen stronger-regularization recipe: 500 trees, 7 leaves, minimum child 500,
L2 20. Refit the original 250-tree/15-leaf model and candidate on identical
original fold-rebuilt windows. The fresh incumbent deviance exactly reproduces
its saved card. No test tuning or production cache rebuilding.

| Metric | Current | Candidate | Candidate-current 95% match-bootstrap CI |
|---|---:|---:|---|
| Next-15 Poisson deviance | 0.701116104 | 0.700206952 | [-0.001362269, -0.000459031] |
| Rest Poisson deviance | 0.968717669 | 0.964634601 | [-0.005431471, -0.002781265] |
| Block-result Brier | 0.406828520 | 0.405779039 | [-0.001524948, -0.000591461] |
| Block-result log loss | 0.697895629 | 0.695921114 | [-0.002833992, -0.001130789] |

The existing outcome helper truncates Poisson counts at 12. Strict probability
validation exposed a small missing tail: maximum 0.00002894 current, 0.00005075
candidate. For block-result scores only, normalize both distributions identically;
report omitted mass in the candidate card. Production helper is unchanged. The
initial reporting step failed closed on this issue; the run resumed from saved
fold boosters without changing the recipe or test data.

Artifacts: `candidates/goals-v1/goals_goals_next15.txt`,
`goals_goals_rest.txt`, `goals.json`, saved targets, all fold boosters and aligned
predictions. Final booster feature order and positive finite rates checked on
100 saved rows. No DB backfill required for goals-only promotion.

Verification: full backend Ruff lint/format passed; requested suite passed
53 tests before final reporting additions. Final validation rerun follows.

Final first-batch checks: `uv run --group models ruff check .` and
`ruff format --check .` passed (112 files). Requested pytest selection passed
55 tests, with four existing multimethod deprecation warnings. All production
model cards remain byte-identical to the initial inventory.

### Second batch in progress

- VAEP: fixed 210-round, 15-leaf recipe, minimum leaf 500, L2 10, max-bin 63.
  Original fold boosters are rerun on identical actions. The new LightGBM
  Sequence reads parquet in bounded batches with a two-match cache; it passes a
  dense-versus-streamed equivalence test and excludes shootouts from fitting.
  Observed RSS during the first fold is under 2 GB. No dense 6M×568 copy is made.
- Game-state next: frozen 360-tree / seven-leaf raw quantiles on existing rebuilt
  windows. Primary p50 comparison is exactly comparable to the current median.
  Outer-band raw metrics are explicitly separate from the archived calibrated
  metrics; do not silently reuse calibration fitted on outer test information.
- Pre-match next: expanded shrinkage grid, selected only on weeks 6–17 with the
  original strictly earlier-round correction fits. Weeks 18–34 never select.
- Pass completion next: fixed 600-tree / 15-leaf recipe, refit incumbent on the
  same raw 360 features and five match folds. No no-360 extrapolation claim.
- Baseline archived game-state and current retained pre-match predictions have
  now been rescored through the common CLI, with fresh ECE/calibration outputs.
- Market replay correction: UI time-series files omit checkpoints lacking a
  timeline display row. The evaluator now reads the cached historical prices
  and original alignment audit directly, preserving all aligned matches and
  the exact three-minute lag. No market requests or new alignment fitting.

### Upstream leakage repair and goals v2

The old outer-fold lineup ratings dropped held-out match rows, but their retained
VAEP values came from global OOF estimators that had trained on the held-out fold.
This indirectly leaked outer outcomes into goals and game-state predictors.
`outer_player_ratings` now revalues only training matches with that outer fold's
saved VAEP estimators, then aggregates ratings. Held-out matches never enter the
VAEP fit or the rating sums. Training rows also exclude their own match from the
shrinkage prior. Runtime production ratings remain unchanged.

`corrected_windows` saved repaired features only under
`candidates/corrected-windows-v1/`, with input/output hashes. All production-window
features are exactly unchanged. Mean absolute outer lineup-feature corrections
range from 0.0124 to 0.0204. Both current and candidate goals recipes were refitted
on these identical corrected folds. The candidate recipe was unchanged after the
audit; no tuning used the repaired evaluation. Old cards are marked invalid.

| Metric | Current refit | goals-v2 | Candidate-current 95% match-bootstrap CI |
|---|---:|---:|---|
| Next-15 Poisson deviance | 0.701315058 | 0.700359508 | [-0.001398762, -0.000499137] |
| Rest Poisson deviance | 0.968990570 | 0.965366605 | [-0.004933028, -0.002319564] |
| Block-result Brier | 0.406972838 | 0.406048708 | [-0.001382730, -0.000465010] |
| Block-result log loss delta | — | -0.001728104 | [-0.002570399, -0.000884958] |

Recommend **goals-v2**, conditional on orchestrator review. Baseline means the
current recipe refitted on corrected held-out folds, not the invalid old card.
Candidate JSON includes both sets of metrics and paired intervals. Production
booster formats and feature order remain unchanged; goals-only promotion changes
no database tables. All forecasts and what-if differences remain modelled.

### Second-batch completed comparisons

| Model / metric | Current | Candidate | Delta 95% match-bootstrap CI | Decision |
|---|---:|---:|---|---|
| Game-state v2 xG-for p50 pinball | 0.086999116 | 0.086995360 | [-0.000038159, 0.000032971] | Hold |
| Game-state v2 xG-against p50 pinball | 0.086993786 | 0.086994737 | [-0.000034757, 0.000036903] | Hold |
| Game-state v2 possession p50 pinball | 0.044341264 | 0.044282429 | [-0.000104324, -0.000012014] | Component gain only |
| Pre-match Brier | 0.584927386 | 0.585350714 | [-0.007516398, 0.008925891] | Reject |
| Pass completion Brier | 0.064949284 | 0.064962979 | [-0.000056290, 0.000082062] | Hold |
| Pass completion log loss | 0.211768824 | 0.211692788 | [-0.000275216, 0.000125081] | Hold |
| xT transition log loss | 2.791217246 | 2.789601571 | [-0.001820409, -0.001424650] | Mixed |
| xT transition Brier | 0.883531233 | 0.883574557 | [0.000038818, 0.000047797] | Hold |

Game-state v2 uses corrected upstream ratings for both refits. Raw quantile bands
are compared to incumbent raw bands; historical calibrated metrics are explicitly
marked invalid, never reused as a fair comparator. Possession improves at all
three quantiles; p10–p90 coverage is 0.790866 → 0.791045. xG-for/against p10 losses
worsen, so the entire bundle is not recommended. A separately calibrated,
predeclared possession-only candidate needs its own clean comparison.

Pre-match preserves strict earlier-round fitting and selects penalty 30 only on
weeks 6–17; weeks 18–34 remain evaluation. Fresh current predictions reproduce the
retained model to 1.11e-16. Candidate loses to current and market (Brier 0.573955).
Pass completion refits both recipes on identical five match folds (293 matches,
260,025 360 passes); neither mixed change is conclusive.

xT tests a fixed lateral-symmetry count pool. A new 99-class next-action likelihood
covers 96 destination cells plus failed moves, missed shots and goals. Sufficient
counts permit proper scores and match-weighted paired bootstraps without a dense
action-class matrix. Reconstructed incumbent grids match to 5.55e-17. The candidate
improves log loss but worsens Brier, so no promotion. Player per-90 Spearman is
0.999923 and top-20 overlap is 20/20; these are sanity checks, not player-quality
validation. Compatible 8×12 grids and OOF action values remain candidate-local.

Second-batch verification: full backend Ruff lint and format passed (122 files).
Requested pytest selection passed 62 tests (four existing multimethod warnings).
The regression suite covers fold-safe rating construction, own-match prior
exclusion, streaming/dense VAEP equivalence, weighted match bootstraps, market lag,
xT count/grid reconstruction and source-feature missingness.

### W13 transfer experiment

`xg-dynasty-v1` fixes unit weight and the incumbent xG recipe before fitting.
29 source training matches contribute 686 shots; eight identity-hash-selected
matches / 180 shots remain untouched. Unknown contextual fields stay missing.
StatsBomb five-fold log loss is 0.262876736 → 0.262875325, delta CI
[-0.000204884, 0.000204743]: no measurable adult improvement. Source-holdout Brier
is 0.195516 → 0.106022 (CI [-0.158513, -0.024587]); log loss 0.578152 → 0.346898
(CI [-0.386207, -0.085917]). Only eight youth matches support those intervals;
provider semantics and population shift limit transfer. Hold global promotion.

### VAEP probability comparison

Fixed recipe completed all five folds and final fits over 5,962,491 actions.
Fresh incumbent fold predictions reproduce the saved current scores.

| Target / metric | Current | Candidate | Delta 95% match-bootstrap CI |
|---|---:|---:|---|
| Scores Brier | 0.009392051 | 0.009390090 | [-0.000004355, 0.000000625] |
| Scores log loss | 0.048025873 | 0.048006806 | [-0.000030620, -0.000006909] |
| Concedes Brier | 0.002110814 | 0.002106693 | [-0.000005722, -0.000002479] |
| Concedes log loss | 0.013347199 | 0.013330712 | [-0.000025826, -0.000006742] |

Both log losses improve; scores Brier is inconclusive. Action-value/player sanity
checks are running. Hold production promotion until ranking and dependent-model
validation are complete. This is a predictive probability gain, not evidence that
all derived player rankings are more accurate.
