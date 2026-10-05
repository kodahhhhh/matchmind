# W14 promotion procedure (orchestrator only)

Goals v1 is recommended for orchestrator review; xG is inconclusive and in-play
v1 is rejected. No candidate has been promoted. W14 has not changed production
models, served artifacts, the database, or services. Promotion requires review
of same-split comparisons, paired intervals and downstream effects.

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

`models/candidates/goals-v1/` has `goals_goals_next15.txt`,
`goals_goals_rest.txt`, and `goals.json`. The baseline is faithfully refitted on
identical existing outer-fold windows; no all-corpus predictions enter validation.
The boosters use the existing FEATURES and `rates()`/`outlook()` signatures.

Only after the candidate qualifies for promotion:

```sh
export DATA_DIR=/home/ubuntu/hackathon/data
cp "$DATA_DIR/models/candidates/goals-v1/"goals_goals_*.txt "$DATA_DIR/models/"
cp "$DATA_DIR/models/candidates/goals-v1/goals.json" "$DATA_DIR/models/goals.json"
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
