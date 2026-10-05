# W14: models v2, make every model measurably better

You're the W14 models agent for MatchPulse, a football analytics app built on StatsBomb open data (2,924 men's matches, about 6M SPADL actions) with its own models. The hackathon is over, and the owner wants every model made **better and better, measurably, on honest held-out data**, iterating for days.

You're working in `~/hackathon-W14-models` on branch `ws/W14-models`. Read `AGENTS.md` (especially §3, §5 and §11 production safety) and `PLAN.md`, then **`backend/matchpulse/models/MODELS.md`, `INTEGRATION.md`** and `backend/matchpulse/backtest/BACKTEST.md`. Each model's current validation is in `data/models/<name>.json`. `backend/.env` is in place and `uv sync` has been run.

## The models (current artifacts in `data/models/`)

1. **xG** (`models/xg.py`). Feeds almost everything, so improvements here pay off everywhere.
2. **VAEP** scores / concedes (`models/vaep.py`). Per-action impact and player ratings.
3. **xT** (`models/xt.py`)
4. **Game-state** quantile models (`gamestate*.py`): xG for/against and possession share, p10/p50/p90, over 15-minute windows.
5. **Goals / what-if** (`models/goals.py`): goals in the next 15 minutes and rest of match, from actual-goals targets. Powers the What-if screen.
6. **Pass options** (`models/pass_options.py`): StatsBomb 360 "what if he'd passed instead".
7. **Player ratings / squad strength** (`players/`, `models/squad.py`, `models/player_ratings.py`).
8. **Backtest pre-match** models (`backtest/prematch.py`, `squad_*.py`). Currently worse than the market (Brier 0.585 vs market 0.574).
9. **Backtest in-play** models (`backtest/inplay.py`). **Currently worse than the naive baseline** (Brier 0.4574 vs 0.4565; the squad variant is 0.488). These are the most obvious targets.

## Rules

* **Honest validation is the whole point.** Folds are grouped by match, time-aware where the deployment is time-ordered (backtests: train strictly before test), with no leakage of upstream models fitted on held-out matches (MODELS.md explains the existing fold-rebuild discipline, so keep it). Before claiming a win, re-run the **current** model on the **same** split and compare like for like. Report confidence intervals or a paired bootstrap when the gain is small. Never tune on the final test set.
* **No network calls** in `models/` (AGENTS.md §3). Pure functions over DataFrames and saved files.
* **Never overwrite `data/models/*`.** The live site reads them. Save each candidate to `data/models/candidates/<name>/` with the usual sibling JSON (training date, data size, validation metrics, plus `baseline_metrics` from the current model on the same split). Keep artifact formats and the public function signatures the API uses (`INTEGRATION.md`), so promotion is a file swap plus a backfill. If an interface has to change, document it in `docs/models/PROMOTION.md`.
* Don't run the backfill against the `matchmind` DB. Write `docs/models/PROMOTION.md` with exact promotion steps (copy candidate → run backfill → which tables change); the orchestrator runs it.
* Counterfactual and what-if outputs are always labelled as modelled, never as what "would have" happened.
* The box is shared with the live site and two other agents: `nice -n 10`, at most 8 threads (`n_jobs`, `OMP_NUM_THREADS`, LightGBM `num_threads`), peak RAM under 12 GB, and stream or chunk the 6M-action tables if needed.

## How to work

1. **Baseline harness first.** Write one reproducible evaluation entry point (e.g. `uv run python -m matchpulse.models.evaluate <name>`) that scores the current artifact and a candidate on a fixed, saved split with the right metrics per model: log loss, Brier, ECE/calibration curve for probabilistic models, pinball loss + interval coverage for quantile models, ranking sanity checks for VAEP/xT (MODELS.md has the player sanity checks), and Brier/log loss vs market and vs naive baseline for backtests. Record every model's baseline in `docs/models/LOG.md`.
2. **Then iterate model by model**, highest impact first: in-play backtest (beat the baseline, then the market), xG, goals/what-if, VAEP, game-state, pre-match, pass options, player ratings, xT. Ideas to try, not orders: calibration (isotonic/temperature, per-segment), better features (shot context, freeze-frame features with a no-360 fallback, game-state and score effects, player/team strength without leakage), monotonic constraints, hyperparameter search with grouped CV, ensembling, distributional models for goals (Poisson / bivariate / Dixon-Coles style) versus the current approach, and time-decay weighting for backtests.
3. **More data:** the W13 data-sources agent is ingesting extra full-event matches (probably the Wyscout public dataset, ~1,900 matches) into SPADL under `data/sources/<source>/`. Watch `~/hackathon-W13-sources/docs/sources/LOG.md`. When it lands, test whether training on StatsBomb + the new data helps, evaluated on StatsBomb held-out folds (event definitions differ between providers, so check carefully for a source effect).
4. After each real, validated improvement: commit (code + `docs/models/LOG.md` + an updated MODELS.md section), and keep going. A negative result is still worth a line in the LOG. Stop working on a model when you hit clearly diminishing returns, and move to the next.

## Verification
`uv run ruff check . && uv run ruff format --check .` and `uv run pytest tests/test_models_* tests/test_whatif.py tests/test_backtest.py` pass, and every candidate has a sibling JSON with candidate-vs-current metrics on the same split. End each session with the AGENTS.md handoff: a table of model × metric × current × candidate × CI, and which candidates you recommend promoting.

This is a multi-day effort. Keep going without waiting for check-ins, and commit in small steps on `ws/W14-models` (don't push or merge). Anything that really needs the owner goes at the top of `docs/models/LOG.md` under "Needs owner".
