# W13: more matches, recent matches, more sources

You're the W13 data-sources agent for MatchPulse, a football analytics app (StatsBomb events → SPADL → our own xG / VAEP / xT / game-state / what-if models → Postgres → FastAPI → React). The hackathon is over and the owner is now making the product as good as possible. Your job is to **get more matches, including recent ones, with as much of the same data as possible.**

You're working in `~/hackathon-W13-sources` on branch `ws/W13-sources`. Read `AGENTS.md` first (especially §3 "External data", §4 data conventions and §11 production safety), then `PLAN.md`, `backend/matchpulse/models/MODELS.md`, `backend/matchpulse/db/README.md` and `data/catalogue/` to learn how a StatsBomb match currently flows through the system. `backend/.env` is already in place and `uv sync` has been run.

## Background

* Today all 2,924 matches come from StatsBomb open data (already fully on disk). The original plan was to scrape WhoScored (Opta events) for World Cup 2026, but Cloudflare returned 403 to this EC2 box, so it was dropped.
* The owner now wants sources like **FotMob** so we get more matches and recent ones.
* The catch: almost every feature (pitch replays, sequences, VAEP impact, xT, game-state windows, what-if, pass options) needs a **full event stream**, meaning every on-ball action with x/y, type, outcome, player and time. FotMob-style sites mostly expose shot maps, lineups, ratings, team stats and momentum, not full event streams. Find out exactly what's available instead of assuming.

## Rules (these are the owner's, and they're non-negotiable)

* Polite fetching only: honest User-Agent, at least 1 s between requests per host, no parallel hammering, cache every raw response under `data/raw/<source>/` and never refetch a cached one.
* **Never evade blocking.** No Cloudflare/anti-bot solvers, CAPTCHA services, rotating or residential proxies, headless-browser fingerprint spoofing or replayed browser cookies. If a source returns 403/429 or a challenge page, record that in `SOURCES.md` and move on. Don't retry it with tricks. If a source needs a signed request header that its site generates, you may reproduce documented public behaviour, but not anything designed specifically as anti-bot protection. When unsure, skip the source and write down why.
* Note each source's terms or licence in `SOURCES.md`. Prefer openly licensed datasets.
* Production safety (AGENTS.md §11): never write to the `matchmind` DB, never touch `data/models/`, don't restart the live API. Use a `matchpulse_staging` database for loads.

## Plan

### Phase 1: source spike (keep it short, ~1–2 hours)
Check every candidate from this box and fill in `docs/sources/SOURCES.md` with a matrix: source × reachable from EC2? × what it provides (full events with x/y? shots with x/y? xG? lineups? player ratings? momentum? team stats?) × competitions and seasons × how recent × licence/terms × effort. Candidates, at minimum:
* **FotMob** public JSON (match details, league fixtures).
* **Wyscout public dataset** (Pappalardo et al. 2019, figshare, CC BY 4.0): about 1,900 full-event matches (2017/18 top-5 leagues, World Cup 2018, Euro 2016). socceraction has a Wyscout→SPADL converter. This is probably the biggest win for full-feature matches and for model training data.
* **StatsBomb open-data updates**: compare `data/manifest.json`'s commit with upstream `statsbomb/open-data` and list any new competitions or matches.
* **Understat** (shot-level x/y + xG, top-5 leagues 2014→now), **football-data.co.uk** (results, odds), **SofaScore** (just test reachability once; if it's blocked, drop it), Metrica / SkillCorner open data (tracking, few matches).
* Anything else you find that's open and has event-level data.

### Phase 2: build it, in this order (adjust if the spike says otherwise and explain why)
1. **Full-event tier.** Ingest the best full-event source(s) (likely Wyscout) into SPADL with exactly the same columns and conventions as our StatsBomb SPADL (105×68, IDs `"{source}:{native}"`, e.g. `wy:2058017`, event IDs `"{source}:{match_id}:{action_index}"`). Run them through the existing model and backfill pipeline so they get our own xG/VAEP/xT and everything else, and load them into `matchpulse_staging`. Dedupe matches that exist in several sources (World Cup 2018 is in StatsBomb too) by date and teams, preferring StatsBomb. Map team and player identities across sources (`backend/matchpulse/teams.py`, `backend/matchpulse/players/`). Also write the SPADL parquet under `data/sources/<source>/` and say so in your LOG, because the W14 models agent wants more training data.
2. **Recent-match "lite" tier** from FotMob (and/or Understat): the current and recent seasons of the top-5 leagues + Champions League, with whatever exists (score, lineups, shots with x/y converted to 105×68, stats, momentum). Write an idempotent `refresh` command that fetches only new finished matches, so the owner can run it daily.
3. **Contract proposal for lite matches.** Most endpoints assume full events. Don't edit `fixtures/` or `api/schemas.py` (the orchestrator owns them). Instead write `docs/sources/CONTRACT_PROPOSAL.md`: a `data_tier` field (`full` / `lite`) in match meta, which endpoints and features work per tier, example JSON for a lite match, and how the frontend should degrade. The orchestrator and the frontend agent will pick it up.
4. New catalogue entries go to `data/sources/catalogue_<source>.json` in the same shape as `data/catalogue/matches.json`. The orchestrator merges them into the main catalogue.

### Verification
* Tests in `backend/tests/test_sources_*.py` (parsers on cached fixtures, coordinate conversion, dedupe, idempotent refresh), plus `uv run ruff check . && uv run ruff format --check .`.
* Prove it works end to end. Load a sample (e.g. 20 Wyscout and 20 FotMob matches) into `matchpulse_staging`, run the API from your worktree on port **8013** with `DATABASE_URL` pointing at staging, and hit the match list, match meta, timeline and replay endpoints for a full-tier and a lite-tier match. Run `tests/test_contract.py` against it where it applies.
* Record counts (matches per source/tier/competition/season, actions per match vs StatsBomb, coordinate sanity checks such as shot locations near goal) in `docs/sources/LOG.md`.

## Working style
This is a multi-day effort. Keep going through the phases without waiting for check-ins, and commit in small steps on `ws/W13-sources` (don't push or merge). Keep `docs/sources/LOG.md` updated. If you hit a decision that really needs the owner (e.g. a source is only usable with a paid key), write it at the top of the LOG under "Needs owner" and carry on with the next item. End with the AGENTS.md handoff.
