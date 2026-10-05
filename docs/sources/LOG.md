# W13 running log

## Needs owner

- **Run the home-connection WhoScored fetcher:** EC2 returns Cloudflare 403 on
  competition, fixtures and match-centre pages, unchanged after 30 seconds in a
  genuine headed browser. See `WHOSCORED_LOCAL.md`. No recent full WhoScored
  streams can be claimed until captures arrive and pass the importer.
- Wyscout archives now downloaded successfully with genuine Chromium; no manual
  download needed. The article itself remained HTTP 202, but the public download
  host delivered all five files normally. No challenge solver was used.
- Round 2 supersedes round 1's terms/licence exclusions. The owner takes that
  responsibility. Source terms remain documented, without blocking ingestion.
- Frontend integration: minute-only shots expose null `period` when unknown,
  `second`, elapsed `t` and `duration_t`. Shot navigation should use list order
  and displayed minute; do not animate a continuous event replay for lite data.
- Review ten FotMob/Understat date or score disagreements before treating them
  as extra fixtures. The source records and richer FotMob payloads are retained;
  `sources/round2_final_inventory.json` lists both sides. Details are below.

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

## Round 2 — 2026-10-05

Owner changed external-data rules: terms/licences are now owner responsibility,
ordinary headed Chromium is authorized, and IP blocks should use an owner-run
home-connection fetcher. This explicitly changes PLAN's original source policy.
W13 also owns API changes and additive lite fixtures for this round. Production
DB/models/service restrictions remain. Initial raw cache is 19 GB, root free 160 GB;
raw budget is 40 GB total. Prior round's terms-based holds are superseded.

Next: headed WhoScored reachability, cached local fetch/import path if blocked,
Wyscout browser/manual path, FotMob bulk lite acquisition, and compatible lite API.

### Round 2 — acquisition and implementation in progress

- Wyscout full archive and metadata are cached under `raw/wyscout/incoming/`;
  expected JSON files extracted under `raw/wyscout/dataset/`. Original archives
  and receipt hashes retained. All conversion is offline.
- Full importer writes the standard SPADL parquet schema to
  `sources/wyscout/spadl/` for W14, scored parquet to `scored/`, normalized raw
  metadata to `normalized/`, and loads staging transactionally. Existing trained
  xG/VAEP/xT files are read only. Synthetic socceraction carries are explicitly
  marked inferred and do not claim native source event IDs.
- Wyscout own goals can be tagged on touches; normalized observed goals and
  pre-action VAEP score context now account for those. Strict score agreement
  quarantines incomplete or mismatched streams.
- FotMob sequential bulk refresh has started for six competitions and seasons
  2026/27 and 2025/26, newest first. Only finished fixtures are fetched; details
  are immutable and discovery is cached by day for the active season.
- New lite API dispatch reads `source_lite_matches`. Shots remain separate from
  full `events`/minute metrics in the database; API timeline full-event series
  are null. What-if, pass alternatives and analyst endpoints reject lite data.
- Source reconciliation prefers StatsBomb, then other full streams, then rich
  FotMob, then Understat. Understat PPDA/deep aggregates supplement overlapping
  FotMob payloads under separate provider provenance.

### Additional recent-full pilot: Impect

- Checked the official Impect V3 documentation and cached recent Bundesliga
  events/rosters. Appendix 1 proves centred 105×68 coordinates, positive y up;
  adjusted coordinates make both teams attack +x. Documented game-time periods
  start at 0, 10,000, etc.; they are not elapsed match seconds.
- Attempted a strict converter on recent cached matches. All eight inspected
  newest examples failed: seven had neutral pass outcomes without unambiguous
  receiver/contact evidence, one had an unlinked goal marker. Sample 123136 has
  52 neutral passes with no reported receiver; some can be resolved by observed
  opposition blocks/receipts, while foul interruptions leave outcome uncertain.
- No Impect match is published as model-ready full tier. Acquisition stopped;
  successful raw responses remain cached for W14. This is a data-semantics gate,
  **not** a terms/licence exclusion. W14 needs an explicit missing/neutral outcome
  convention before those actions can join the standard binary-result SPADL.
  `sources/impect_feasibility_report.json` records the pilot. No fabricated pass
  completion, foul location or own-goal touch was used to force acceptance.
- Wyscout bulk completed 1,850 matches initially; corrected scoreET's documented
  final-score convention recovered the two Euro extra-time matches, giving
  **1,852** accepted exports/staged matches. Four score mismatches remain
  quarantined. StatsBomb-preferred dated duplicates include every World Cup 2018
  match; none is added as a duplicate Wyscout card.
- All **20 unchanged StatsBomb contract tests passed** after loading the missing
  reconstructed reference match's cached raw events into staging. Production DB,
  model files and services remain untouched.

### Round 2 — final accepted coverage

Literal unicode in Wyscout team/player labels was repaired in generated exports
and staging metadata, with original raw records retained. The reviewed Korea
Republic/South Korea alias exposed ten further StatsBomb duplicates. Final
Wyscout acceptance is **1,842**, superseding the intermediate 1,852 above:
1,941 raw matches minus 95 StatsBomb duplicates and four quarantines.

| New/retained full source | Competition | Season | Accepted and staged |
|---|---|---|---:|
| Wyscout | Bundesliga | 2017/18 | 306 |
| Wyscout | La Liga | 2017/18 | 348 |
| Wyscout | Ligue 1 | 2017/18 | 380 |
| Wyscout | Premier League | 2017/18 | 379 |
| Wyscout | Serie A | 2017/18 | 378 |
| Wyscout | Euro | 2016 | 51 |
| Dynasty | Nigeria youth league | 2024 | 37 |
| WhoScored | Target top five + Champions League | 2023/24–current | 0 |

All 64 Wyscout World Cup 2018 matches prefer existing StatsBomb. The four score
mismatches are `wy:2499781`, `wy:2576181`, `wy:2576063`, `wy:2565863`; incomplete
goal evidence is not fabricated to force acceptance. Final exports plus the
unchanged 2,924 StatsBomb demo matches yield **4,803 available full matches**.
The complete **74 source/competition/season rows**, including every StatsBomb
season, are in [COVERAGE.md](COVERAGE.md). No new recent CL full stream is claimed.

FotMob bootstrap completed **2,209 finished lite matches**, all staged. This
includes **207 Champions League** matches: 189 in 2025/26 and 18 in 2026/27.
COVERAGE.md lists all twelve competition/season counts. The latest returned date
is **2026-09-20**, despite collection on October 5; this is returned coverage,
not a claim of complete coverage through today. FotMob provides 56,969 shot-map
records: 56,784 own-xG predictions and 185 own-goal markers without shot xG.

Understat retains **2,002** exports with 51,244 shots, 51,086 own-xG predictions
and 158 own-goal markers. **1,992** overlap FotMob after reviewed club aliases;
their PPDA/deep aggregates, available roster/minute context and source provenance
enrich the richer FotMob payload. Provider xG, ratings and momentum remain
separate from our model values. If a FotMob shot collection is absent, available
Understat fallback shots keep their original provenance and receive primary
FotMob event IDs; overlapping complete shot collections are not double-counted.

The source-only preferred catalogue has **4,098 entries**, including ten unresolved
possible duplicates. Nine disagree on dates: `us:29218`, `us:29720`, `us:29722`,
`us:29723`, `us:29724`, `us:29820`, `us:29821`, `us:29822`, `us:29824`; corresponding
FotMob dates differ by one or two days. `us:31948` reports PSG–Rennes 0–0 on
2026-08-23, whereas `fm:5803105` reports Rennes–PSG 2–2 that day. These records
remain visible and are not called ten confirmed additional matches. The ten
Understat records are also staged; with the retained 40-match sample, staging
has **50 Understat**, **2,209 FotMob**, **1,842 Wyscout**, **37 Dynasty**. Loaded
discovery prefers richer/full matches and advertises **7,022 cards**, including
the unchanged 2,924 StatsBomb baseline and the ten unresolved entries.

### Final data quality and model evidence

`sources/round2_quality_report.json` audits exports one file at a time:

| Source | Full matches | SPADL actions | Mean actions/match | Own xG rows | VAEP rows | Valued xT rows |
|---|---:|---:|---:|---:|---:|---:|
| StatsBomb reference | 2,924 | 5,962,767 | 2,039.25 | Existing models | Existing models | Existing models |
| Wyscout | 1,842 | 2,335,341 | 1,267.83 | 43,486 | 2,335,341 | 1,470,719 |
| Dynasty | 37 | 30,402 | 821.68 | 866 | 30,402 | 14,065 |

All new full exports have the exact **18-column StatsBomb SPADL order**, 105×68
metres and home attacking +x in storage. No full or lite coordinates are invalid.
Attacking-relative shot median x is 91.35 m for Wyscout and 89.79 m for Dynasty.
Wyscout contains **134,024 explicitly inferred converter carries**. Native source
event IDs and qualifiers are preserved separately from namespaced public IDs;
inferred actions do not claim native event IDs. W14 training parquets are under
`data/sources/wyscout/spadl/` and `data/sources/dynasty/spadl/`, with `scored/`
and `normalized/` companions. Nothing is written under `data/models/`.

FotMob y orientation was cross-checked against the cached Understat shot renderer
and matched sample shots: retained-y median error 0.256 m versus mirrored-y
13.046 m. `sources/fotmob_coordinate_crosscheck.json` retains the paired evidence.
Away shots rotate exactly once at the API boundary. Minute-only sources keep
precise seconds/elapsed time unknown instead of inventing a continuous clock.

Identity evidence reuses reviewed team aliases and exact player aliases within
observed historical team membership: **382 source teams, 265 mapped to StatsBomb;
11,705 source players, 1,894 mapped**. Ambiguous/unobserved identities remain
source-local. `sources/identity_map.json` records method and unmatched identities.
W14 transfer calibration, new-source game-state IO and canonical player-rating
support remain unvalidated. New full sources declare game_state/pass_options
false until those paths are supported; the existing StatsBomb paths are preserved.

### Final verification and operational handoff

- `uv run --group models --with playwright==1.58.0 --with json5 pytest
  tests/test_sources*.py -q`: **35 passed**. Cached provider parsers, SPADL/coordinate
  conventions, own goals, strict final-period evidence, dedupe, tier isolation,
  idempotent refresh, complete-cache replay/pacing and staging-only guards covered.
- Unchanged `tests/test_contract.py`: **20 passed**, against matchpulse_staging
  using an isolated original StatsBomb catalogue. New discovery is probed
  separately because the original test intentionally fixes the baseline count.
- Byte comparison with round-1 commit `0bace27`: reference StatsBomb meta, events,
  timeline, default sequences, players and turning-points responses are identical;
  all **2,924 existing match cards** are identical. Saved in
  `sources/byte_compatibility_report.json`.
- Actual worktree API on **8013**: **70 match GET sets** passed meta/timeline/replay
  event schemas and ID/coordinate checks: 20 Wyscout, 20 FotMob, 20 Dynasty and ten
  unresolved Understat. `sources/api_sample_report.json` retains endpoint evidence.
  Wyscout penalty sample `wy:1694426` shows 1–1 plus observed shootout 4–5.
- Added real lite response fixtures under `fixtures/matches/fm_5795459/`; original
  full fixtures and `tests/test_contract.py` were not modified. Optional tier,
  capabilities/provider fields and nullable unknown metrics are documented in
  CONTRACT_PROPOSAL.md. Lite unsupported analytic collections are empty and
  full-event model endpoints return 422 before invoking unavailable analytics.
- FotMob repeat refresh: **0 new, 2,209 skipped, 0 network responses**, raw cache
  byte-identical. Evidence: `sources/fotmob_idempotence_report.json`.
- Backend `uv run ruff check . && uv run ruff format --check .`: passed,
  **133 files** formatted. Standalone local fetcher Ruff checks passed separately.
- Raw cache is **22,508,897,883 bytes**, below the **40 GiB** ceiling; root free
  space **156 GB** at final inspection. The home fetcher's default 10 GiB budget
  fits this allowance. No push/merge, production DB/model/service writes or live
  server restarts. Refresh/run instructions are in REFRESH.md.
- Staging continuous aggregates refreshed after the full backfill:
  **334,013 Wyscout** and **5,535 Dynasty** minute-metric rows, with **zero lite
  minute-metric rows**. Staging holds 2,335,493 Wyscout normalized events and
  33,734 Dynasty normalized events; model-row counts agree with exported actions.
  `sources/round2_staging_metrics.json` records this final database evidence.
- Verification API shut down cleanly after the final probes. No W13 scraper,
  importer watcher, training job or dev server remains running at handoff.
- Round-2 implementation commits: `79237d5` (full-source imports/local capture),
  `9b73b9e` (label repair/resumability), `17d9db7` (FotMob/reconciliation/exports),
  `a9002f9` (lite API plus schemas and fixtures). Final documentation records the
  accepted coverage, unresolved pairs and operational commands. Nothing pushed
  or merged.

The owner needs the home WhoScored fetcher; no Wyscout manual download is needed.
SofaScore still reaches a CAPTCHA redirect and adds no demonstrated full stream.
Impect neutral/missing outcomes remain a W14 data-semantics request. Orchestrator
should merge the canonical source catalogue once, review the ten disagreements,
and promote API/data changes through its normal production process. W15 needs
nullable shot-clock/jersey handling and provider-labelled stat panels.
