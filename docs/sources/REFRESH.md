# Source operations

Run these commands from `~/hackathon-W13-sources/backend`. They use the central
configuration for DATA_DIR, whose existing value is `~/hackathon/data`. Every
load command refuses a database name other than `matchpulse_staging`. Do not edit
the worktree `.env` to point at production. Existing trained models are read only.

## Daily FotMob refresh

```sh
nice -n 10 env DATABASE_URL=postgresql://matchmind:matchmind@localhost:5432/matchpulse_staging OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --group models python -m matchpulse.sources.fotmob refresh --load
```

The default is this season and last, top five leagues plus Champions League.
Only new finished match details are fetched; discovery is cached once per day
for the active season and permanently for completed seasons. Match details are
immutable. The command loads existing offline exports if needed and reconciles
Understat enrichment after refreshing. Interrupting it is safe; rerun to resume.
Use `--limit 20` for a sample or `--seasons 2026 2025 --leagues 42` for CL only.
It makes sequential public JSON requests with at least one second per host,
records refusals and never deletes or retries a complete cached response.

Understat's existing refresh remains available for fallback shots and PPDA/deep:

```sh
nice -n 10 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --group models python -m matchpulse.sources.pipeline refresh
nice -n 10 env DATABASE_URL=postgresql://matchmind:matchmind@localhost:5432/matchpulse_staging OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --group models python -m matchpulse.db.load_sources load --full-limit 0 --lite-limit 10000
nice -n 10 env DATABASE_URL=postgresql://matchmind:matchmind@localhost:5432/matchpulse_staging uv run python -m matchpulse.sources.reconcile --load
```

## Full streams

WhoScored is blocked on EC2. The owner must run the home fetcher described in
[WHOSCORED_LOCAL.md](WHOSCORED_LOCAL.md). It transfers complete captures into
`data/raw/whoscored/incoming/`. The offline server importer supports polling:

```sh
nice -n 10 env DATABASE_URL=postgresql://matchmind:matchmind@localhost:5432/matchpulse_staging OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --group models python -m matchpulse.sources.import_full whoscored --load --watch 60
```

Omit `--watch 60` for a single scan. No watcher has been left running at handoff.
Completed exports are skipped, staged loads are transactional, and incomplete
streams are quarantined. This command never requests WhoScored from EC2. After
new captures are imported, update source aliases and identity evidence:

```sh
DATABASE_URL=postgresql://matchmind:matchmind@localhost:5432/matchpulse_staging uv run python -m matchpulse.sources.reconcile --load
nice -n 10 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --group models python -m matchpulse.sources.identities
```

All Wyscout archives are already present. Reimport or resume entirely offline:

```sh
nice -n 10 env DATABASE_URL=postgresql://matchmind:matchmind@localhost:5432/matchpulse_staging OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --group models python -m matchpulse.sources.import_full wyscout --load
```

Manual-download fallback and the expected file list are in
[WYSCOUT_MANUAL.md](WYSCOUT_MANUAL.md). No owner Wyscout download is currently
needed. Standard 18-column SPADL exports for W14 are under
`data/sources/wyscout/spadl/` and `data/sources/whoscored/spadl/`; scored and
normalized companions preserve source IDs and inferred-action provenance.

## Catalogue and review

Per-source `data/sources/catalogue_<source>.json` files retain provenance. The
orchestrator can merge **catalogue_canonical.json** as the source-only preferred
list, or apply `reconciliation_report.json` when merging individual catalogues.
Do not merge both lists independently. Priority is StatsBomb, other full streams,
FotMob, then Understat. Loading a full stream suppresses its duplicate lite card.
Ten Understat/FotMob date or score disagreements remain visible for review;
`round2_final_inventory.json` lists both records. These are not confirmed extra
fixtures. Original source IDs remain in raw/exports and alias reports; API routes
resolve the preferred loaded discovery IDs.

Loaded source cards appear in this branch's API when `DATA_DIR/sources` exists;
catalogue and match caches refresh every five minutes. This is a staging feature,
not a production promotion. Optional capabilities and lite behavior are documented
in [CONTRACT_PROPOSAL.md](CONTRACT_PROPOSAL.md).

## Budget and checks

The combined raw cache at handoff is 22,508,897,883 bytes, below the 40 GiB limit.
The home fetcher's default 10 GiB budget fits within the remaining allowance.
Check `du -sb ~/hackathon/data/raw` before another bulk source and coordinate any
increase. No raw data or model artifacts are committed.

```sh
DATABASE_URL=postgresql://matchmind:matchmind@localhost:5432/matchpulse_staging uv run --group models --with playwright==1.58.0 --with json5 pytest tests/test_sources*.py -q
uv run ruff check . && uv run ruff format --check .
```

Final API probes and source quality reports are under `data/sources/`. See
[LOG.md](LOG.md) and [COVERAGE.md](COVERAGE.md) for counts and exact evidence.
