# MatchMind — Build Plan

> An AI football analyst that explains *why* a match turned, with every claim linked to real events, and models *what could have happened instead*.

StormHacks 2026 · Deadline **Sun Oct 4, 12:00pm PDT** · This file is the single spec for every agent (Claude subagents and Codex). If something here conflicts with a task prompt, this file wins; update it rather than drifting.

---

## 1. Decisions (locked)

| Topic | Decision |
|---|---|
| LLM | Azure OpenAI. **`gpt-6.1-sol`** = analyst (tool calling, explanations). **`gpt-6-luna`** = bulk jobs (sequence commentary, query routing). Existing Azure embeddings deployment for vectors. |
| Who calculates | **Python calculates, the LLM only explains.** No number in an answer may come from the LLM; every number comes from a tool result. |
| Custom models | Trained on this EC2 (16 cores, 61 GB, CPU only): **xG**, **VAEP action values**, **game-state outcome model**. No LLM training. |
| Database | **TimescaleDB + pgvector**, self-hosted in Docker on this EC2. Hypertable for events, continuous aggregates for per-minute metrics, pgvector for commentary search and game-state analogs. No TiDB. |
| Data | StatsBomb open data (free) + **World Cup 2026 via a WhoScored scrape, gated on a 30-min spike** (§3.2). |
| Design | Broadcast dark, made genuinely beautiful (§8). |
| Hosting | This EC2 + a free `.tech` domain via MLH. |
| Execution | Claude orchestrates and owns the core; Codex gets well-specified, file-isolated tasks (§10). |

## 2. Product

### Screens
1. **Match browser.** Competition tabs; match cards with score, date and a tiny momentum sparkline.
2. **Match view** (the main screen):
   - **Pitch** (centre): events for the selected window. Passes as arrows, carries as dashed lines, shots as circles sized by xG, goals highlighted. Replay mode animates sequences.
   - **Timeline** (bottom): per-minute possession, xG (cumulative), field tilt, and a **momentum** line. Goals, subs and cards are markers. Click or drag to set the pitch window.
   - **Analyst panel** (right): chat with Sol. Answers stream in with citations like `[61' Pedri → Yamal]`; clicking one jumps the pitch and timeline to that event.
   - **Tabs:** Replay · Top sequences · Players (VAEP rankings) · What if.
   - **"Find the turning point"** button: prominent and one click.
3. **What if** (inside Match view): pick an event (sub, goal, red card) and a change. Shows a **branching timeline**: actual line vs a modelled band, plus a list of real historical analog situations. Always labelled "modelled hypothetical".

### Core features in priority order (cut from the bottom)
1. Replay + timeline, synced
2. AI analyst with clickable citations
3. Find the turning point
4. Top sequences + player rankings
5. What if (counterfactual model + analogs)
6. Hybrid search across all matches ("every time France broke down the left")
7. Stretch: ElevenLabs voice commentary of the turning point

## 3. Data

### 3.1 StatsBomb open data (free, local)
`git clone --depth 1 https://github.com/statsbomb/open-data data/raw/statsbomb`

**Demo competitions (187 matches):**

| Competition | Matches | Notes |
|---|---|---|
| World Cup 2022 | 64 | Final = flagship turning-point demo (Mbappé 80–81') |
| Euro 2024 | 51 | Spain: Yamal, Pedri |
| Bundesliga 2023/24 | 34 | **Leverkusen's matches only**, not the full league |
| Copa América 2024 | 32 | |
| MLS 2023 | 6 | **Inter Miami only**, Messi |

**Training corpus:** all 2,651 men's matches in open data (used for xG, VAEP and the game-state model).

### 3.2 World Cup 2026 via WhoScored (gated)
- **Spike (30 min, first thing):** use Playwright (Chromium is already installed) to load one WC 2026 match page and extract the embedded Opta event JSON (`matchCentreData`).
  - **Pass:** full event list with x/y coordinates and qualifiers → scrape all 104 matches with polite rate limiting (one page at a time, randomized delay of several seconds), caching raw JSON to `data/raw/whoscored/`.
  - **Fail** (Cloudflare blocks it or the data is missing): drop WC 2026 and do not retry. Note it in §12.
- WhoScored has no xG, so **our own xG model is used for every source** (keeps metrics consistent).
- Scraped data is for the demo only: never committed, never redistributed. `data/` is gitignored.

### 3.3 Normalisation
All sources convert to **SPADL** via `socceraction` (StatsBomb and Opta/WhoScored loaders both exist). Everything downstream reads SPADL plus a small `match_meta` table, so it never needs to know the source.

Output: `data/processed/{source}/{match_id}.parquet` + `data/processed/matches.parquet`.

## 4. Models

| Model | Method | Trained on | Validation (report in README) |
|---|---|---|---|
| **xG** | LightGBM on shots: distance, angle, body part, shot type, assist type, under pressure, game state | ~70k StatsBomb shots | Log loss + Brier vs StatsBomb's own xG on held-out matches |
| **VAEP** | `socceraction` VAEP (scores / concedes within the next 10 actions), LightGBM | All 2,651 matches as SPADL | AUC on held-out matches |
| **xT** | `socceraction` xT grid (12×8) | Same | n/a (used for the pass-vs-shoot approximation) |
| **Game-state** | LightGBM quantile regression (p10/p50/p90) | 5-min windows across all matches | Pinball loss; calibration of p10–p90 coverage |
| **Turning point** | `ruptures` PELT on the momentum series | n/a | Sanity check: WC 2022 final flags ~80' |

**Game-state window features:** minute, score diff, possession %, field tilt, xT rate, VAEP rate for and against, shots, minutes since last sub, players on pitch (red cards), home/away.
**Targets:** xG for and against over the next 15 minutes, possession over the next 15 minutes.

**Counterfactual changes supported:**
- `remove_goal`: score diff reverts (e.g. "What if Mbappé's penalty was missed?")
- `no_sub`: minutes-since-sub feature reverts
- `remove_red_card`: players-on-pitch reverts

Output = the model's p10–p90 band for the next 15 minutes **plus the k nearest real windows from pgvector** (analogs) with what actually happened in them. The UI shows the confounding caveat in a tooltip.

**Derived metrics** (per minute, per team): possession, xG, field tilt (share of final-third touches), progressive passes and carries, VAEP sum, **momentum** = rolling 5-min VAEP difference (home − away). **Sequence danger** = sum of VAEP over the possession sequence.

## 5. Database (TimescaleDB + pgvector, Docker)

```
matches(match_id PK, source, competition, season, kickoff_ts, home, away, score, meta jsonb)
players(player_id PK, name, team, position)
events  — HYPERTABLE on ts (= kickoff_ts + match clock)
  (event_id, match_id, ts, period, minute, second, team, player_id, type, result,
   x, y, end_x, end_y, xg, vaep, vaep_off, vaep_def, xt, sequence_id, extra jsonb)
minute_metrics — CONTINUOUS AGGREGATE over events, 1-minute buckets per match+team
sequences(sequence_id, match_id, team, start_ts, end_ts, n_events, danger, events int[])
commentary(sequence_id, match_id, minute, text, embedding vector(D))   -- HNSW index, plus tsvector for hybrid search
gamestate_windows(window_id, match_id, team, minute, features jsonb, outcome jsonb, embedding vector(16))
```

Tiger Data track talking points: hypertable + continuous aggregates serve the timeline instantly; one Postgres holds time series, relational data and vectors. Check with MLH whether self-hosted counts for the prize.

## 6. API (FastAPI) — contract

Fixtures for every endpoint live in `fixtures/` and are committed **before** any implementation. The frontend builds against fixtures from day one. Changing a shape means updating the fixture in the same commit.

```
GET  /api/competitions
GET  /api/matches?competition=
GET  /api/matches/{id}                    → meta, lineups, score timeline, subs, cards
GET  /api/matches/{id}/events?from=&to=   → events (fields as in the events table)
GET  /api/matches/{id}/timeline           → per-minute series per team + markers
GET  /api/matches/{id}/sequences?sort=danger&limit=5
GET  /api/matches/{id}/players            → VAEP rankings: progression, creation, defending
GET  /api/matches/{id}/turning-points     → [{minute_start, minute_end, before{}, after{}, magnitude}]
POST /api/matches/{id}/counterfactual     {event_id, change} → {actual{}, modelled{p10,p50,p90}, analogs[]}
GET  /api/search?q=&match_id=             → hybrid search over commentary
POST /api/matches/{id}/ask                {question, history[]} → SSE: {type:"text"|"citation"|"tool"|"done"}
```

**Citation format** in analyst text: `[[ev:<event_id>]]` or `[[seq:<sequence_id>]]`. The frontend renders these as chips.

## 7. LLM layer

- **Client:** Python `openai` SDK, `base_url = <AZURE_OPENAI_ENDPOINT origin>/openai/v1/`, same env vars as `~/coline-app` (`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`). Model names come from config (`ANALYST_MODEL=gpt-6.1-sol`, `BULK_MODEL=gpt-6-luna`, `EMBED_DEPLOYMENT=…`). Copy values into `backend/.env`; never commit it.
- **Analyst (Sol):** a tool loop. Tools: `get_window_stats`, `get_events`, `get_top_sequences`, `get_player_rankings`, `find_turning_points`, `run_counterfactual`, `search_moments`. The system prompt requires citing tool-returned IDs and never inventing numbers.
  - **Prompt caching:** system prompt + tool schemas + match summary form a fixed prefix; history and the question go after it.
- **Commentary (Luna):** offline batch. One broadcast-style line per sequence for all demo matches, generated from structured sequence data. Then embed and load into `commentary`.
- **Eval:** a 10-question golden set on the WC 2022 final. Check that every number in each answer appears in that answer's tool results (automated check).

## 8. Design brief — "broadcast dark, but beautiful"

Think Apple TV sports or a Champions League broadcast graphics package, not a generic dark dashboard.

- **Palette:** near-black base with a green tint (`#07100c`-ish), the pitch slightly lighter with subtle mowing stripes and thin, low-contrast lines. **Team colours are the only saturated colours on screen**; everything else is neutral greys. Accent for AI elements: a single cool tone used sparingly.
- **Type:** a condensed display face for scores, minutes and big numbers (broadcast feel), a clean sans for UI text, tabular numerals everywhere data changes.
- **Motion:** pass arrows draw on along their path; trails fade out over a short time; the timeline scrubs smoothly; turning-point reveal animates the change in momentum. Nothing bounces.
- **Pitch rendering:** SVG, StatsBomb coordinates (120×80), soft glow on the active sequence only, xG as circle area.
- **Layout:** pitch is the hero (≥55% width on desktop). Analyst panel is a slide-over on narrow screens. Must look good at 1440×900 (video recording size).
- **Charts:** follow the `dataviz` skill. Two-team series use team colours; momentum is a single diverging area around zero.
- **Quality bar:** every screen should look good as a screenshot in the Devpost gallery.

## 9. Repo layout

```
hackathon/
  PLAN.md
  docker-compose.yml          # timescaledb-ha (includes pgvector)
  fixtures/                   # committed JSON for every endpoint
  data/                       # gitignored: raw/, processed/, models/
  backend/                    # uv project, Python 3.12
    matchmind/
      ingest/   statsbomb.py whoscored.py spadl.py
      models/   xg.py vaep.py gamestate.py
      metrics/  timeline.py sequences.py players.py turning.py
      analyst/  client.py tools.py agent.py prompts.py commentary.py
      db/       schema.sql load.py
      api/      main.py routes/*.py
    tests/
  frontend/                   # Vite + React + TS + Tailwind + D3 + Framer Motion
    src/components/{pitch,timeline,analyst,whatif,browser}/
```

## 10. Workstreams and owners

Each workstream owns its directories exclusively so parallel agents never edit the same files. Codex tasks run in separate git worktrees and merge through Claude.

| # | Workstream | Owner | Owns | Depends on | Done when |
|---|---|---|---|---|---|
| W0 | Scaffold, contracts, fixtures, docker-compose, Azure smoke test | **Claude** | root, `fixtures/`, `api/` stubs | — | Stub API serves every fixture; Sol and Luna each answer a test call from Python |
| W1 | WhoScored spike → full scrape | **Subagent** | `ingest/whoscored.py` | — | §3.2 pass/fail recorded; if pass, 104 raw JSON files cached |
| W2 | StatsBomb ingest → SPADL parquet | **Codex** | `ingest/statsbomb.py`, `ingest/spadl.py` | W0 | All 2,651 matches converted; 187 demo matches have meta |
| W3 | xG + VAEP + xT training | **Claude** | `models/xg.py`, `models/vaep.py` | W2 | Models saved to `data/models/`; validation numbers in README |
| W4 | Metrics, sequences, players, turning points | **Claude** | `metrics/` | W3 | Real responses match fixture shapes; WC22 final turning point ≈ 80' |
| W5 | DB schema + loader | **Codex** | `db/`, docker-compose | W0, W4 | Hypertable + continuous aggregate populated for demo matches |
| W6 | Game-state model + analogs | **Subagent** | `models/gamestate.py` | W3 | p10–p90 coverage reported; analog query < 200 ms |
| W7 | Analyst agent (Sol) + tools + SSE | **Claude** | `analyst/` (except commentary) | W4 | Golden set passes the numbers check |
| W8 | Commentary batch (Luna) + embeddings + hybrid search | **Codex** | `analyst/commentary.py`, `api/routes/search.py` | W5 | All demo sequences have commentary; search returns sensible hits |
| W9 | Frontend: design system, pitch, timeline | **Codex** | `frontend/src/components/{pitch,timeline}`, theme | W0 fixtures | Pitch + timeline synced on fixture data at 1440×900 |
| W10 | Frontend: browser, analyst panel, what-if, citations | **Codex** | `frontend/src/components/{browser,analyst,whatif}` | W9 | Works against the real API end to end |
| W11 | Integration, deploy, domain | **Claude** | — | all | Live on the `.tech` domain |

Claude reviews every Codex merge against this plan and the design brief, with screenshots for frontend work.

## 11. Timeline (T0 = planning sign-off)

| By | Milestone |
|---|---|
| T+1h | W0 done; W1 spike verdict; StatsBomb cloned; Timescale up |
| T+4h | SPADL conversion done; frontend pitch rendering fixture data |
| T+7h | xG + VAEP trained; real timeline/events endpoints live; analyst answers one question end to end |
| T+11h | Turning points, sequences, players live; DB loaded; commentary batch running; frontend on real API |
| T+15h | What-if + search working → **FEATURE FREEZE** |
| T+18h | Polish, design pass, bug fixes, deployed |
| **Sun ~10:00am** | Demo video recorded |
| **Sun 11:30am** | Devpost submitted (30-min buffer) |

If T0 slips, cut features in §2 order. Never cut the 30-minute buffer.

## 12. Risks and fallbacks

| Risk | Fallback |
|---|---|
| WhoScored blocks the scrape | Drop WC 2026; 187 StatsBomb matches is still plenty |
| Opta → SPADL mapping quirks | WC 2026 matches get replay + xG + VAEP only, no commentary, if time is short |
| VAEP training slow | Train on a 1,000-match subset |
| Counterfactual model looks weak | Lead with analogs (real data), show the model band as secondary |
| Sol tool loop is flaky | Fall back to fixed pipelines per question type (routed by Luna) |
| Frontend behind schedule | Drop replay animation first, then the what-if branching visual (keep a table) |
| Judges challenge the counterfactual | Say it outright: observational data, confounded by why subs happen; that's why we show analogs and a range, not a single number |

## 13. Humans (team)

- **Design check-ins** every ~4 hours on screenshots Claude posts.
- **Register the `.tech` domain** (MLH free code).
- **Demo video** (≤3 min, 1440×900) and **Devpost writeup**.
- **Present** (1–2 people).
- **Ask MLH** whether self-hosted TimescaleDB qualifies for the Tiger Data prize.

## 14. Demo script (3 min)

1. **0:00–0:20** Hook: "Stats apps tell you *what* happened. MatchMind tells you *why*, and what could have happened instead."
2. **0:20–1:00** WC 2022 final → **Find the turning point** → lands on 80–81' → Sol explains, citations jump the pitch.
3. **1:00–1:40** "Who was actually progressing the ball?" → VAEP ranking vs raw pass counts; they differ.
4. **1:40–2:20** What if: "Mbappé's penalty is missed" → modelled band vs actual, plus real analog matches.
5. **2:20–2:45** Search across 187+ matches: "every time a team broke down the left after a turnover".
6. **2:45–3:00** Architecture: own models trained on 2,651 matches, Timescale continuous aggregates + pgvector, LLM explains and never calculates.

## 15. Submission checklist

- [ ] GitHub repo public, README with screenshots, architecture diagram, model validation numbers
- [ ] Demo video link (≤3 min)
- [ ] Opt into each track separately: **Sports Analytics, Python (SSSS), Best Design (IATSU), Tiger Data, .Tech Domain** (+ ElevenLabs if built)
- [ ] Data attribution: StatsBomb open data licence credit in README and app footer
