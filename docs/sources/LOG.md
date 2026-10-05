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
