# AGENTS.md

Guidance for coding agents (Claude subagents, Codex) working on MatchMind.

## 1) Source of truth

* Read `PLAN.md` before starting any task. It defines the product, workstreams, ownership, API contract and design brief.
* Precedence when guidance conflicts:
  1. This file (conventions below)
  2. `fixtures/` (the API contract, by example)
  3. `PLAN.md`
  4. Your task prompt
* If your task prompt contradicts `PLAN.md`, follow the prompt only if it says it is changing the plan, and note it in your handoff.

## 2) Ownership: stay in your lane

* Every task belongs to a workstream (W0–W11 in `PLAN.md` §10) and **owns specific directories**. Only edit files your workstream owns.
* Need a change outside your area? Don't make it. Put it under "Requests for other workstreams" in your handoff.
* Shared files (`PLAN.md`, `AGENTS.md`, `fixtures/`, `docker-compose.yml`, root config) are edited by the orchestrator (Claude) only, unless your task explicitly grants it.

## 3) Hard rules

* **The LLM never produces numbers.** Every stat in an analyst answer must come from a tool result. Tools return IDs; answers cite them as `[[ev:<event_id>]]` or `[[seq:<sequence_id>]]`.
* **Never commit secrets.** Azure keys live in `backend/.env` (gitignored). Read config via `matchmind.config`, never `os.environ` scattered through the code.
* **Never commit data.** `data/` is gitignored. Scraped WhoScored data must never leave this machine.
* **No scraping outside W1.** No other task makes requests to WhoScored or any other third-party site.
* **No network calls in `metrics/` or `models/`.** They are pure functions over DataFrames and saved model files.
* **Counterfactual output is always labelled as modelled.** Never phrase it as what "would have" happened.
* Don't leave long-running processes behind (dev servers, scrapers, training jobs) unless your task says to.

## 4) Data conventions

* **Coordinates:** SPADL metres, **105 × 68**, origin bottom-left. In API responses, **the home team attacks left → right in both halves** (flip away-team actions and second-half orientation at the API boundary, not in storage). *This supersedes the "120×80" mention in `PLAN.md` §8.* The frontend pitch uses a 105×68 viewBox.
* **Event IDs:** strings, `"{source}:{match_id}:{action_index}"`, e.g. `"sb:3869685:1042"`. Sequence IDs: `"{source}:{match_id}:s{n}"`.
* **Match IDs:** `"{source}:{native_id}"`, where source is `sb` (StatsBomb) or `ws` (WhoScored).
* **Time:** `period` (1–5), `minute` and `second` as shown on the match clock (stoppage time continues counting, e.g. 45+2 → minute 47 with `period: 1`). DB `ts = kickoff_ts + elapsed match seconds`.
* **Teams in responses:** always `"home"` / `"away"` plus a `teams` object in match meta with names and colours. Never key series by team name.
* **xG:** always our own model's value (`xg`). StatsBomb's value, when present, is kept only as `sb_xg` for validation.
* **Units:** possession and field tilt are fractions 0–1 (the frontend formats percentages). Durations are in seconds.

## 5) Backend conventions (`backend/`)

* Python 3.12, managed with `uv`. Type hints on every public function. Format and lint with `ruff`.
* pandas for tabular work; keep DataFrame column names identical to the API field names where possible.
* `metrics/` functions take SPADL/events DataFrames and return DataFrames or dataclasses. No DB or HTTP access inside them.
* `api/routes/` are thin: load data, call metrics/models, serialise. No analytics logic in routes.
* Pydantic models in `api/schemas.py` must match `fixtures/` exactly. Changing a response shape means updating the fixture and the schema **in the same commit**, and flagging it in your handoff.
* Trained models save to `data/models/{name}.{ext}` with a sibling `{name}.json` holding training date, data size and validation metrics.

## 6) Frontend conventions (`frontend/`)

* Vite + React + TypeScript (strict) + Tailwind. D3 for scales and paths; React owns the DOM. Framer Motion for animation.
* All API access goes through `src/api/client.ts`. Set `VITE_USE_FIXTURES=1` to serve `fixtures/` instead of the backend, so frontend work never blocks on the backend.
* Colours, type and spacing come from theme tokens (`src/theme/`). No raw hex values in components. Team colours come from match meta.
* Follow the design brief in `PLAN.md` §8 and the `dataviz` skill for charts.
* Target viewport **1440 × 900** (demo recording size); must not break at 1280 × 800 or on mobile width.

## 7) Commands

These are the conventions W0 sets up; until W0 lands they may not exist yet.

```sh
docker compose up -d db                                    # TimescaleDB + pgvector on :5432
cd backend && uv sync
cd backend && uv run uvicorn matchmind.api.main:app --reload --port 8000
cd backend && uv run ruff check . && uv run ruff format --check .
cd backend && uv run pytest
cd frontend && npm install
cd frontend && npm run dev                                 # :5173, proxies /api → :8000
cd frontend && npm run typecheck && npm run lint
```

## 8) Verification

* Run lint, typecheck and tests **for the area you touched** only.
* Backend endpoints: validate the real response against its fixture (`tests/test_contract.py`).
* Frontend: take a Playwright screenshot at 1440×900 of every screen you changed and include the paths in your handoff.
* Models: record validation metrics in the sibling JSON and report them in your handoff.
* Don't claim something works unless you ran it. If you couldn't verify something, say so.

## 9) Git and handoff

* Work on a branch named `ws/<workstream>-<slug>` (e.g. `ws/W9-pitch`), in your own worktree when running in parallel.
* Small commits with imperative messages (`Add xG feature builder`). Don't push and don't merge; the orchestrator merges.
* End every task with a handoff in this shape:

```
## Handoff: <workstream>
Done:            what now works
Verified:        commands run + results, screenshot paths, metrics
Contract changes: fixture/schema changes (or "none")
Requests for other workstreams: (or "none")
Open issues / risks:
```

## 10) Environment

| Variable | Used by | Notes |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | analyst | Same value as `~/coline-app`. Client uses `<origin>/openai/v1/` |
| `AZURE_OPENAI_API_KEY` | analyst | Never log it |
| `ANALYST_MODEL` | analyst | `gpt-6.1-sol` |
| `BULK_MODEL` | commentary, routing | `gpt-6-luna` |
| `EMBED_DEPLOYMENT` | commentary, analogs | Azure embeddings deployment name |
| `DATABASE_URL` | db, api | `postgresql://matchmind:matchmind@localhost:5432/matchmind` |
| `DATA_DIR` | all | Defaults to `<repo>/data` |
