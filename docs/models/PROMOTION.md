# W14 promotion procedure (orchestrator only)

**Recommend `goals-v2` for full-data goals and `xg-shot-v1` for Understat lite.**
Never promote `goals-v1` or `gamestate-v1`:
their original windows leaked held-out information through player ratings. V2
rebuilds ratings using only upstream models that exclude each outer fold and
refits both competitors. Other candidates remain held or rejected.
No candidate has been promoted. W14 has not changed production models, served
artifacts, the database or services. The orchestrator performs promotion.

## Artifacts and replay

From `backend/`, always load the models dependency group and bound threads:

```sh
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
nice -n 10 uv run --group models python -m matchpulse.models.evaluate inventory
nice -n 10 uv run --group models python -m matchpulse.models.evaluate inplay
nice -n 10 uv run --group models python -m matchpulse.models.evaluate xg
nice -n 10 uv run --group models python -m matchpulse.models.evaluate inplay --run inplay-v1 --candidate /home/ubuntu/hackathon/data/models/candidates/inplay-v1/backtest_inplay.joblib
nice -n 10 uv run --group models python -m matchpulse.models.evaluate xg --run xg-v1-replay --candidate /home/ubuntu/hackathon/data/models/candidates/xg-v1
```

The manifests pin input hashes and match splits; changed inputs require a new run
name. The experiment CLIs refuse to overwrite completed candidates. These are
local files, never committed data. Archive production artifacts before copying.
Keep the previous versions together for rollback; a model-only rollback cannot
undo previously backfilled event values.

## xG — not recommended yet

Candidate `models/candidates/xg-v1/` contains `xg.txt`, five `xg_fold_N.txt`,
`xg.json` and `shots.parquet`. File formats, FEATURES and inference signatures
are unchanged. The JSON records nested selection, baseline metrics and paired CIs.

After approval, orchestrator commands from the main `backend/` checkout:

```sh
export DATA_DIR=/home/ubuntu/hackathon/data
cp "$DATA_DIR/models/candidates/xg-v1/xg.txt" "$DATA_DIR/models/xg.txt"
cp "$DATA_DIR/models/candidates/xg-v1/"xg_fold_*.txt "$DATA_DIR/models/"
cp "$DATA_DIR/models/candidates/xg-v1/xg.json" "$DATA_DIR/models/xg.json"
cp "$DATA_DIR/models/candidates/xg-v1/shots.parquet" "$DATA_DIR/processed/xg/shots.parquet"
nice -n 10 uv run --group models python -m matchpulse.models.backfill
nice -n 10 uv run python -m matchpulse.db.load refresh
```

The backfill joins OOF shot xG by match + raw UUID and updates `events.xg`.
Its implementation also writes `vaep`, `vaep_off`, `vaep_def`, `xt` from their
unchanged processed artifacts; verify those values remain identical. Refresh
updates the minute continuous aggregates (`minute_metrics`). It does not rebuild
`sequences`, player ratings or `gamestate_windows`.

**Do not stop at that swap.** Game-state and goals artifacts depend on xG windows.
Rebuild all production/outer-fold windows in a separate staging DATA_DIR with the
candidate xG and original other dependencies; revalidate downstream models before
promoting their outputs as a compatible set. Existing training CLIs write directly
to DATA_DIR and may request 16 workers, so do not run them against main unchanged.
The backtest upstream xG is a separate pre-2015 historical fit and must stay frozen.
The pass-options xG helpers read the fold boosters; cached boosters need process
reload by the orchestrator after a coordinated promotion.

## Goals / what-if

`models/candidates/goals-v2/` has `goals_goals_next15.txt`,
`goals_goals_rest.txt`, and `goals.json`. The baseline is faithfully refitted on
identical corrected outer-fold windows; no held-out match enters an upstream
VAEP estimator or rating aggregate. Full-data boosters retain production features.
The boosters use the existing FEATURES and `rates()`/`outlook()` signatures.

After reviewing goals-v2 metrics and archiving the three existing files:

```sh
export DATA_DIR=/home/ubuntu/hackathon/data
cp "$DATA_DIR/models/candidates/goals-v2/"goals_goals_*.txt "$DATA_DIR/models/"
cp "$DATA_DIR/models/candidates/goals-v2/goals.json" "$DATA_DIR/models/goals.json"
```

No database backfill or table change is needed for goals alone: API inference
loads these goal-rate boosters on demand and caches them in-process. The
orchestrator must reload the API process to clear that cache. Validate modelled
factual/changed outlook responses after reload. Do not describe them as causal.

## In-play — reject v1

`inplay-v1/backtest_inplay.joblib` preserves the original bundle shape:
`model`/`baseline`, each with classifier, ordered features and temperature.
`inplay_predictions.parquet` is the excluded-tournament prediction set. This
candidate does not improve validation and must not be promoted.

For a future accepted candidate, copying the model alone will not change the
website: the routes serve precomputed JSON under `processed/backtest/w12/`.
Regenerate those outputs in staging using frozen cached market histories,
original lag/settlement rules and unchanged current pre-match predictions; update
all served comparison/version fields consistently. No DB table changes or event
backfill are needed. Do not run `backtest train` or `squads` as a promotion command:
those refit other models and can overwrite retained production choices.

## Remaining candidates — no promotion

`gamestate-v2` shows a possession-only improvement, but xG quantiles are mixed and
the comparison uses raw, uncalibrated bands. Do not copy the bundle over the live
calibrated model. `prematch-v1` loses to both current and market. `passes-v1` is
inconclusive. `xt-v1` improves transition log loss but worsens Brier. None needs
production backfill while held. VAEP/source-augmentation decisions are recorded
in LOG.md when their evaluations complete.

The code-level outer-rating repair affects future training only. Existing
production windows, live rating feature construction and model inference remain
unchanged. Rebuilding validation uses `python -m matchpulse.models.corrected_windows`
with a fresh run name if inputs changed; never run production window/training
entry points against main data as an experiment.

## Distributional in-play — hold for confirmation

`inplay-poisson-v1/backtest_inplay.joblib` preserves the outer bundle and existing
inference signatures, but contains the new serializable
`matchpulse.backtest.inplay_poisson.PoissonResult` class. Merge this module before
loading that joblib anywhere. It implements `predict_proba` and bounded-thread
`set_params` and delegates to the fitted Poisson-rate regressor. No network or
feature writes occur during prediction. Save/load through the common adapter
was exercised. The new `feature_frame` helper reads existing upstream artifacts;
its original cache-writing wrapper keeps the previous signature and behavior.

Fresh-cohort scores beat the naive baseline but not conclusively the incumbent;
market results are mixed. Do not promote now. Any later accepted in-play swap
also requires the staged served-JSON regeneration described above, not event or
DB backfill. Current API contract/fixtures are unchanged.

Additional fixed experiments through the common entry point (fresh run names):

```sh
nice -n 10 uv run --group models python -m matchpulse.models.evaluate inplay-poisson --fit --run inplay-poisson-reproduction
nice -n 10 uv run --group models python -m matchpulse.models.evaluate xg-dynasty --fit --run xg-dynasty-reproduction
```

The source run pins accepted catalogue/file hashes and tests a source holdout;
new W13 data requires a fresh run. VAEP remains on hold until its changed action
values, player totals and dependent windows are evaluated together. Its candidate
OOF values must never be mistaken for global-fit training values in outer folds.

## Round 2: xg-shot-v1 — recommend Understat lite only

This is a new artifact, not a swap for `xg.txt`. StatsBomb same-fold Brier loses
0.005025 versus full context, as expected. External Understat Brier improves
0.233350 → 0.081345 versus freshly replayed current lite inference (exact staged
prediction reproduction); the paired 95% difference interval is
[-0.154729, -0.149242]. Provider xG remains reference only. Calibration ECE is
0.011383 on 2,002 Understat matches. FotMob has only one cached match and is held
for broader validation. No production write has been performed.

After merging the W14 model interface and W13 loader/capability integration, the
orchestrator can install the separate artifact:

```sh
export DATA_DIR=/home/ubuntu/hackathon/data
cp "$DATA_DIR/models/candidates/xg-shot-v1/xg_shot.txt" "$DATA_DIR/models/xg_shot.txt"
cp "$DATA_DIR/models/candidates/xg-shot-v1/xg_shot.json" "$DATA_DIR/models/xg_shot.json"
```

W13 then re-scores existing lite JSON through `xg_shot.predict`, keeps provider_xg,
keeps own-goal xG null, and reloads the lite payloads using its guarded staging
loader first. W14 cannot supply a production DB loader command: W13 currently
only authorizes its loader for matchpulse_staging. The orchestrator must review
W13's exact production promotion path before any live DB load. This changes lite
payload shot xG and derived chance totals only; no SPADL/event/VAEP/xT backfill or
`minute_metrics` refresh is appropriate for lite data. Do not run the generic
StatsBomb `models.backfill` on lite matches. Forecast capability stays false until
verified shot periods and a separately validated lite outlook model are available.

## Round 2 held research artifacts

- `prematch-lite-v1`: recent daily rolling evaluation improves against legacy
  lite xG and league-frequency baseline, but loses to goals-only team ratings.
  No market odds or W12 squad parity; do not promote.
- `lite-goals-v1`: matched `xg_shot_historical.txt` + `lite_goals.joblib` (class
  `matchpulse.models.lite_goals.LiteOutlook`). Merge the class before deserializing.
  Inference and serialization were exercised; improvement over incumbent is
  inconclusive, and current Understat clocks are insufficient. Do not promote.
  The full-data `xg-shot-v1` model cannot replace this prototype's upstream without
  retraining the outlook and repeating chronological validation.
- WhoScored xG/VAEP/xT: no candidate exists while the event corpus is unavailable.
  No current model is certified for that provider by these lite tests.

Safe recommendation now: separate **xg-shot-v1 for Understat lite xG and chance
summaries**, plus the already recommended goals-v2 for the existing full-data
pipeline. FotMob, lite outlook, recent pre-match and WhoScored remain held.


Round-2 reproduction (from backend, same thread environment as above):

```sh
nice -n 10 uv run --group models python -m matchpulse.models.evaluate xg-shot --fit --run xg-shot-reproduction
nice -n 10 uv run --group models python -m matchpulse.models.evaluate prematch-lite --fit --run prematch-lite-reproduction
nice -n 10 uv run --group models python -m matchpulse.models.evaluate lite-goals --fit --run lite-goals-reproduction
```

The last two consume the explicitly pinned round-1/shot-v1 inputs described in
their manifests; a new shot model is not silently substituted. Inputs are local
files only; these commands cannot fetch data or write to the database.
