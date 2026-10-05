# W13 source operations

Run from this worktree's `backend/`. Dependencies: `uv sync --group models`.
The supplied `.env` points `DATA_DIR` to `/home/ubuntu/hackathon/data`; current
models are read only. Generated data stays in ignored `raw/` and `sources/`.

## Full-event imports

```sh
uv run --group models python -m matchpulse.sources.acquire
nice -n 10 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --group models python -m matchpulse.sources.pipeline import-dynasty
```

The acquisition uses the cached Apache-2.0 archive and attribution documents.
Inspect `sources/dynasty_report.json` for rejection reasons and model counts.
Stricter imports move stale accepted outputs to `dynasty/quarantine/`. W14 must
use only files listed by `catalogue_dynasty.json` / `quality_report.json`.
`dynasty/spadl/` matches the StatsBomb 18-column schema; `scored/` adds actual
model values; `normalized/` retains rosters and raw source annotations.

Wyscout's offline socceraction converter is tested with a synthetic event.
Figshare refused the dataset, so a complete Wyscout importer/load is unverified;
licensed local files remain an owner follow-up. Youth model transfer, inferred
possessions and video-derived clocks require validation before promotion.

## Daily finished-match refresh

```sh
nice -n 10 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --group models python -m matchpulse.sources.pipeline refresh
```

Defaults: all five Understat leagues, 2026 and 2025. Override `--seasons` and
`--leagues`; `--limit 20` bounds newly imported matches. Discovery uses an immutable
UTC collection-date URL, `?mp_snapshot=YYYY-MM-DD`. The parameter names our snapshot;
the provider does not filter by it. Only unknown `isResult=true` fixtures fetch
detail. Same-day reruns use cached discovery and skip imported matches; later
same-day results appear in the next daily snapshot. Successful imports persist
individually, so interrupted jobs resume. Finished detail URLs are never refetched;
provider corrections need a separately designed revision policy.

Understat publication/commercial rights remain unresolved: this is a private
staging feed. FotMob bulk/daily collection is excluded by its terms. Refusal state
is never automatically reset. All requests share a lock and per-host timing;
there is no alternate-host source bypass.

Upgrade parser/model features offline, then report identities and coverage:

```sh
nice -n 10 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --group models python -m matchpulse.sources.pipeline rebuild-understat
uv run --group models python -m matchpulse.sources.identities
uv run --group models python -m matchpulse.sources.report
uv run --group models python -m matchpulse.sources.pipeline inventory
```

The rebuild makes no HTTP calls. Identity bridges require exact known aliases
plus historical StatsBomb roster membership; ambiguity remains unmatched.
`quality_report.json` records counts, action coverage, coordinate bounds, missing
clock precision and duplicate/score-conflict checks using existing club aliases.

## Staging and API verification

The new loader refuses every database except `matchpulse_staging`. Never use the
existing loader/backfill defaults, which resolve production DB/model locations.

```sh
env DATABASE_URL=postgresql://matchmind:matchmind@localhost:5432/matchpulse_staging \
  uv run --group models python -m matchpulse.db.load_sources init
env DATABASE_URL=postgresql://matchmind:matchmind@localhost:5432/matchpulse_staging \
  uv run --group models python -m matchpulse.db.load_sources load --full-limit 20 --lite-limit 20
env DATABASE_URL=postgresql://matchmind:matchmind@localhost:5432/matchpulse_staging \
  uv run --group models python -m matchpulse.db.load_sources refresh
```

Full reloads transactionally replace only the selected staged source match's
rows. Lite upserts separate JSONB payloads with no fake events/sequences. Existing
other sample IDs remain. If stricter parsing quarantines a staged match, remove
that specific match's staged dependents before comparison; the loader does not
prune unrelated experiments automatically.

Prepare a temporary source-visible catalogue and run the worktree API on 8013:

```sh
env DATABASE_URL=postgresql://matchmind:matchmind@localhost:5432/matchpulse_staging \
  uv run --group models python -m matchpulse.sources.verify prepare
env DATABASE_URL=postgresql://matchmind:matchmind@localhost:5432/matchpulse_staging \
  DATA_DIR=/home/ubuntu/hackathon/data/sources/verification-runtime \
  nice -n 10 uv run --group models uvicorn matchpulse.api.main:app --host 127.0.0.1 --port 8013
```

In another terminal:

```sh
env DATABASE_URL=postgresql://matchmind:matchmind@localhost:5432/matchpulse_staging \
  uv run --group models python -m matchpulse.sources.verify probe
env DATABASE_URL=postgresql://matchmind:matchmind@localhost:5432/matchpulse_staging \
  uv run --group models pytest tests/test_sources* -q
uv run ruff check . && uv run ruff format --check .
```

Stop the owned server afterward. The probe validates all staged full GET schemas
and pitch bounds, and reports current lite 503s explicitly. A successful probe is
not a working lite API. See `CONTRACT_PROPOSAL.md` for shared integration changes.
Main catalogue, fixtures, schema, `.env` and live service remain unchanged.

The applicable existing contract selection requires separately loading the local
StatsBomb reference `sb:3869685` with actual current-model values:

```sh
env DATABASE_URL=postgresql://matchmind:matchmind@localhost:5432/matchpulse_staging \
  DATA_DIR=/home/ubuntu/hackathon/data/sources/verification-runtime \
  uv run --group models pytest tests/test_contract.py -q \
  -k 'real_get_contract and not search or events_and_orientation_exactly_match_fixture or timeline_labels_and_periods or event_filters_and_errors or fixture_sse_variants'
```

This excludes Azure search and unavailable game-state/what-if coverage. It
complements source tests; another source/match isn't expected to equal a
StatsBomb fixture. W13 loaded/backfilled that reference directly in staging;
existing backfill commands were not run because they write model artifacts.
