# W13 running log

## Needs owner

- Wyscout/Figshare is blocked (403); supply CC BY 4.0 local files if desired.
  No alternate mirror or blocker bypass is being used.
- FotMob prohibits systematic/regular automation. Provider permission is needed
  for the requested daily feed; only the already cached spike is parsed.
- Impect forbids commercial use and redistribution; football-data.co.uk excludes
  commercial/training bots. Neither will be expanded into a product feed.
- Understat has no open data licence located: publication rights need review.
- Orchestrator/API ownership: catalogue discovery is demo-filtered and metrics
  assume full StatsBomb-shaped events. Production exposure and lite endpoint
  gating need coordinated changes; W13 will not modify those shared files.

## 2026-10-05 — start

- Read AGENTS.md, PLAN.md, model documentation, DB documentation and source code.
- This task changes PLAN's StatsBomb-only restriction under AGENTS §3/§11.
- Branch `ws/W13-sources`; clean initial worktree. Root has 61 GB free before downloads.
- SPADL storage: home attacks +x each period. DB raw storage: acting team attacks +x;
  API metrics consume StatsBomb-shaped `extra`, catalogue is file-based, demo-filtered.
- Existing model training/backfill CLIs are StatsBomb-specific and write model artifacts;
  W13 will reuse pure feature/inference code with read-only model artifacts instead.
- Next: cached source probes and dataset licence evidence, then conversion and staging.

### Spike outcomes and adjusted implementation

- StatsBomb upstream commit equals local manifest: no new competitions/matches.
- FotMob current `/api/data/` routes are public and reachable, no full on-ball
  stream. Sample is `fm:5795459` (Fulham–Manchester United, 2026-09-20).
- Understat current AJAX routes work with documented jQuery representation
  headers. Plain cached 404s are preserved; successful JSON uses distinct keys.
- Source matrix records all requested candidates plus Impect, Dynasty, OpenFootball.
- Dynasty archive contains 136 matches. Initial strict eligibility accepts 38:
  both teams with >=100 passes, reviewed rosters/directions, coherent period
  clocks and at least 35 minutes/half, observed goals matching the score. Other
  files remain quarantined with reasons. `isHome` is venue, not side identity.
- Official Understat renderer proves Y is bottom-left; conversion is `Y*68`.
- Initial accepted Dynasty sample: 745 SPADL actions, 23 own-model xG rows,
  745 VAEP rows and 307 xT rows; inference ran against read-only current models.
- Implementation exports SPADL with the same standard 18 columns to
  `data/sources/dynasty/spadl/`, scored rows to `scored/`, normalized raw metadata
  to `normalized/`; all data remains gitignored. Youth model transfer unvalidated.

### Conversion and staging verification

- Tightened period bounds and corrected free-kick shot/short-corner/cross mappings.
  Retained observed recovery/block/duel/foul-won annotations without inventing
  SPADL equivalents. Final strict gate currently accepts **37**, quarantines 99;
  one previously accepted match's generated files moved to `dynasty/quarantine/`.
- Accepted Dynasty dates: 2024-02-27 through 2024-10-17. Totals: 35,538 raw
  annotations, 33,734 normalized events, 30,402 SPADL actions; 866 own xG rows,
  30,402 VAEP rows, 14,065 valued xT moves. Per-match attacking shot-x medians
  range 80.282–94.014 metres. All 18 SPADL columns match the StatsBomb export.
- Staging loader rejects every parsed database name except `matchpulse_staging`.
  New full timestamps use observed elapsed period time; displayed minute/second
  remain nominal match-clock values. Reloads are transactional/idempotent.
- Loaded 20 full matches (17,582 normalized DB events) and verified 40 lite
  entries retained across sample reloads as the historical download progressed.
  Lite payloads are separate JSONB rows, with no invented actions or sequences.
- Worktree API on localhost:8013 used an isolated `sources/verification-runtime`
  catalogue with only staged source entries temporarily demo-enabled. All 20
  full matches passed match-meta/timeline/replay-event Pydantic checks and pitch
  bounds; all 40 lite entries returned the expected current-API 503 limitation.
  Main catalogue and production API were unchanged. Report: `sources/api_sample_report.json`.
- Commands passed: `uv run ruff check . && uv run ruff format --check .` (122
  Python files formatted); `uv run python -m compileall -q matchpulse/sources
  matchpulse/db/load_sources.py`; staging `uv run --group models pytest
  tests/test_sources* -q` (**23 passed**), including real duplicate-load checks.
- Applicable existing contract selection passed **13 tests, 7 deselected**.
  First run exposed staging's missing commentary `facts` migration; applied the
  existing migration to staging and reran successfully. Azure-backed search,
  game-state/counterfactual coverage remain outside this source sample's verified
  capabilities. Exact StatsBomb reference event/orientation fixture remains valid.
- Understat bulk refresh continues sequentially; final counts, identity bridge,
  offline parser rebuild and API-process cleanup will be recorded below.
