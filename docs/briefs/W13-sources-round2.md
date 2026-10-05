# W13 round 2: get full action data

Good work on round 1. The owner has changed the rules: **they take responsibility for source terms and licences themselves, so terms of service and missing licences are no longer a reason to skip a source.** Re-read AGENTS.md §3 "External data" (I merged the new version into your branch). In short:

* Allowed: scraping any public football site, including FotMob, WhoScored, SofaScore, Understat and figshare, and driving a real browser (Playwright Chromium, headed under `xvfb-run` if needed) the way a person would.
* Still required: go slowly (sequential, ≥3 s between page loads per host, ≥1 s for JSON APIs), cache every raw response under `data/raw/<source>/`, never refetch what's cached, and make refreshes incremental.
* Still not allowed: CAPTCHA-solving services, residential or rotating proxy networks, anything that overloads a site.

The goal is unchanged but the priority is now explicit: **full action streams (every on-ball action with x/y) for as many matches as possible, especially recent ones and the Champions League.** Shots-only data is the fallback.

## Tasks, in order

1. **WhoScored (top priority).** WhoScored's match centre embeds the full Opta event stream (`matchCentreData` in the page). socceraction already has a WhoScored/Opta → SPADL path. Use it, or follow its logic, and check the output against our StatsBomb SPADL conventions (105×68, home attacks +x, event and match IDs `ws:<id>`).
   * First test from this box with a real Playwright Chromium browser: one competition page, one fixtures page, one match centre page. Record exactly what happens (status codes, whether you get a challenge page, whether the JS challenge resolves in a real browser on its own).
   * **If it works from here:** build the scraper (competition → season → fixtures → match centre) for the top-5 leagues and the Champions League, 2023/24 → current season, newest first, then extend back in time as far as is useful. Run it as a resumable background job (`nice`, single sequential browser). Convert to SPADL, run our models (xG/VAEP/xT, etc.) and load into `matchpulse_staging`. Dedupe against StatsBomb (prefer StatsBomb) and against Understat/FotMob lite matches (the full tier replaces lite).
   * **If this box's IP is blocked:** build `scripts/sources/whoscored_local_fetch.py`, a self-contained fetcher (uv inline-script deps, Playwright) that the owner runs on their own computer on a home connection. It saves raw match-centre JSON to a folder and rsyncs it to this box over Tailscale (`ubuntu@100.97.212.47:~/hackathon/data/raw/whoscored/`), resumable, with the same pacing. Write one-command run instructions in `docs/sources/WHOSCORED_LOCAL.md`. Make the server-side importer pick up whatever lands in that folder.
2. **Wyscout public dataset (figshare).** The API and the `ndownloader` host both answered this box with a 403 / 202 bot challenge. Retry once with a real Playwright browser, which may pass the challenge on its own. If it still fails, add the figshare file list and expected filenames to `docs/sources/WYSCOUT_MANUAL.md` so the owner can download them in their browser, and make the importer run from `data/raw/wyscout/` as soon as the files appear.
3. **FotMob, now allowed.** Bulk-fetch and daily-refresh match details for the top-5 leagues + Champions League (this season and last) as a lite-tier source: shots with x/y, lineups, ratings, stats, momentum. Merge it with Understat (dedupe; take the richer field where they overlap).
4. **SofaScore:** test once with a real browser. If it loads, note what it provides that FotMob and Understat don't. Don't build a scraper unless it adds full action streams.
5. **Implement the lite tier in the API.** You now own this too: you may edit `backend/matchpulse/api/` (routes, repository, schemas) and add fixtures under `fixtures/` for a lite match, following your CONTRACT_PROPOSAL. Full-tier responses must stay byte-for-byte compatible (`tests/test_contract.py` passes unchanged for full matches). New fields stay optional. The W15 frontend already reads `data_tier`, `capabilities.full_events` / `capabilities.vaep` and null timeline series, and expects lite `/events` to return shots only in the existing event shape. Verify against `matchpulse_staging` on port 8013.
6. Keep `data/sources/catalogue_<source>.json` up to date for the orchestrator merge, and update `docs/sources/LOG.md` and `SOURCES.md` as you go.

Production safety from AGENTS.md §11 still applies: no writes to the `matchmind` DB, nothing in `data/models/`, no restarting the live API. There's about 160 GB free disk now. Keep raw caches under 40 GB and say so if you'll need more.

Finish with the AGENTS.md handoff, including how many full-tier matches you now have per competition and season, and whether the owner needs to run the local fetcher.
