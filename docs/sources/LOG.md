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

### Bootstrap complete — final results

| Source / tier | Competition | 2025/26 | 2026/27 |
|---|---|---:|---:|
| Understat / lite | Premier League | 380 | 50 |
| Understat / lite | La Liga | 380 | 69 |
| Understat / lite | Bundesliga | 306 | 36 |
| Understat / lite | Serie A | 380 | 50 |
| Understat / lite | Ligue 1 | 306 | 45 |

- **2,002 Understat matches**, including 250 current-season finished matches;
  available finished dates 2025-08-15 through **2026-09-20**. This source snapshot
  does not establish finished coverage after September 20, despite collection
  being October 5. No Champions League shot feed was acquired.
- Offline rebuilt every imported payload, **zero HTTP requests**. 51,244 shots,
  51,086 own-model xG values; 158 own-goal annotations intentionally have no xG.
  Every shot lacks verified period/second; no exact replay clock is invented.
  All coordinates within 105×68. All 2,002 matches retain exact-date/team/side
  provider PPDA/deep aggregates separately from our metrics and provider xG.
  Raw roster attributes and fixture provenance are retained.
- Real second refresh: **0 new, 2,002 skipped**; raw cache names/mtime and host
  policy bytes unchanged, proving no fresh requests. Default season selection
  now rolls over with the current UTC July-start season. Reports:
  `sources/understat_bootstrap_report.json`, `refresh_idempotence_report.json`.
- Full source remains **37 Dynasty matches / 30,402 SPADL actions**. Mean 821.676
  actions/match, range 499–1,062; StatsBomb reference is 2,924 matches /
  5,962,767 actions, mean 2,039.25. Coverage/domain differs substantially.
  Attacking shot-x median 89.789 metres. 861 source starts and 469 endpoints
  clipped at boundaries, mostly throw-ins/corners; raw start x range 1–501,
  y -1–337 against native 497×328. Unclipped raw annotations remain preserved.
- Cross-source date/team dedupe using existing club aliases found **0** duplicate
  or score-conflicting new matches. Dedupe also handles reversed home/away
  designation at neutral fixtures, still preferring StatsBomb by team-linked score.
- Identity evidence: 127 source teams, **76** unique StatsBomb bridges; 3,790
  source players, **296** exact-alias + historical-team bridges. Other identities
  remain unmatched; source-local IDs are never guessed into canonical IDs.
  `sources/identity_map.json` and `quality_report.json` are the integration outputs.
- Final staging source tests: **23 passed**; applicable contracts again **13
  passed, 7 deselected**. Reloaded all 40 retained lite sample payloads after the
  offline rebuild and refreshed existing staging continuous aggregates.
- Shared API still needs capability dispatch, lite shapes, catalogue integration,
  nullable missing context, and removal/explicit labelling of legacy VAEP proxy
  fallback for unscored full rows. W14 needs source-aware game-state/player-profile
  IO and transfer validation. Production exposure is not claimed.
- No push or merge. Main catalogue, production DB, model artifacts and service
  were not modified. Final cleanup and commit references follow.

### Cleanup / handoff readiness

- Final staging: 20 full matches, 40 lite; 17,582 full events with 475 xG,
  15,863 VAEP and 7,383 xT model rows. Refreshed 3,041 full minute-metric rows;
  lite has **0 fake events and 0 minute-metric rows**. All 60 staged source
  entries were probed again; 20 full GET sets passed, 40 lite GET sets returned
  documented 503s. `sources/staging_report.json` retains these counts.
- Final Ruff checks and compilation passed (123 Python files). Owned 8013 API
  stopped with clean shutdown; `ss` shows no listener. Bootstrap/rebuild jobs
  finished; no W13 scraper/training/server process remains. Final root free
  space is 161 GB; host free space changed during shared-box activity.
- Commits before final evidence update: `aae18b0` (cache/refusal spike),
  `01c6177` (adapters/inference/proposal), `1e8852f` (staging/safety/verification).
  Final evidence update adds neutral-venue dedupe, rolling refresh defaults,
  quality clipping provenance and this completed log. Nothing was pushed/merged.
- Next is orchestrator integration/rights review and W14 transfer validation;
  no background collection or production change is pending from W13.
