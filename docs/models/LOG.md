# W14 models v2 log

## Needs owner

None at initialization. Production promotion remains orchestrator-owned.

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

### Goals v1 — recommend promotion after orchestrator review

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
