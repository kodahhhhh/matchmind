# W11 player data and profiles

This workstream extends the plan's original integration-only W11 assignment with
the explicitly requested player datasets and endpoints. It uses only the approved
CC0 Transfermarkt distribution, Wikidata/Commons APIs and local StatsBomb/model
artifacts. Nothing is scraped from Transfermarkt, and its image URLs are ignored.

## Build and publish

From this worktree's `backend/`:

```sh
uv sync --group models
export DATA_DIR=/home/ubuntu/hackathon/data
# First install only: original matcher + career computation, if artifacts absent.
# uv run --group models python -m matchmind.players.matching
# uv run --group models python -m matchmind.players.career

# Rerunnable W11b enrichment and publication; retain the shared DATA_DIR.
uv run --group models python -m matchmind.players.bulk
uv run --group models python -m matchmind.players.coverage_matching
uv run --group models python -m matchmind.players.build --enrich --load-db
```

The matcher writes the complete seven-column `player_map.parquet` atomically,
then touches the empty `_READY` marker. This is the W12 dependency. `profiles` and
`valuations` parquet files are independently published atomically. Career outputs
are `career.parquet` (player/competition/season/team), `matches.parquet`
(player/match), and `career.json` (the profile's career, heatmap, top moments and
match history). `coverage.json`, `spot_check.json` and `latencies.json` contain
verification evidence. All data outputs and raw caches stay outside Git.

Network enrichment is optional and rerunnable; raw JSON responses are cached.
W11b uses one complete P2446 SPARQL index, bulk English labels/aliases and basic
biographies (with explicit DOB precision and height units) from the approved
QLever mirror. Official Wikidata `wbgetentities` supplies full claims, multilingual
labels/aliases, sitelinks and qualified P54 spells for dataset identities and
plausible legacy candidates. This avoids tens of thousands of redundant requests
for TM-only basic biographies. English country/club labels use small bulk queries.

All requests use a descriptive User-Agent and a minimum 0.55-second start interval
within each sequential downloader. API calls carry `maxlag=5`. HTTP 429 honors
numeric or HTTP-date Retry-After; 502/503/504 and maxlag retry up to five attempts.
The observed anonymous limit was about ten successful API batches per minute;
429 cooldowns were honored. An exhausted source leaves remaining metadata null,
and a later run resumes from completed files. No unapproved hosts are queried.
Photos are Commons API derivatives at `upload.wikimedia.org` or
`thumb.wikimedia.org`, with author credit and an explicitly free licence. Noncommercial,
no-derivatives and unrecognized licences are rejected. Commons titles are batched
50 at a time, normalized/redirected by the API, and cached individually. The
requested derivative width is 400 pixels; narrow source files can be smaller.
Conflicting TM/Wikidata
birth years invalidate the QID/photo bridge. No provider requests occur in the
API, metrics or models at request time.

`--load-db` applies `db/players.sql` and upserts only `player_profiles`,
`player_valuations` and `player_careers`. It does not change existing match/event
rows or reset model outputs. Runtime reads the published files; restart the
consumer API process after rebuilding artifacts to replace its process caches.
The registered player router warms identities, histories and the substring search
index during application startup, before it accepts requests. Do not restart the
shared service from a player workstream.
The parquet reader requires the existing `models` dependency group (pyarrow).

## Orchestrator integration request

Register the exported router in `matchmind/api/main.py`, which is outside W11's
explicit ownership:

```python
from matchmind.api.routes.players import router as players_router

app.include_router(players_router, prefix="/api")
```

`players/schemas.py` owns the additive Pydantic contracts. Golden examples are in
`tests/golden/player_example.json`, `players_search_example.json` and
`leaderboard_example.json`, plus `player_tm_only_example.json` (Erling Haaland,
`player_id=-418560`). W11b adds `in_dataset` and `sources` to profiles,
and `in_dataset` to search
results. Existing fields remain present. The shared `fixtures/players` and frontend
types/components belong to the orchestrator and must be updated from these golden
examples during integration.
The `get_player_profile` analyst tool is registered in `analyst/tools.py`; its
output includes display-number evidence and labels for real event/sequence IDs.

Isolated API verification (never restart the shared :8000 service):

```sh
uv run --group models uvicorn matchmind.api.routes.players:create_player_app \
  --factory --host 127.0.0.1 --port 8040
```

Stop this process after verification. No frontend files are owned or changed.

## Definitions and limitations

Matching uses date and both clubs to identify TM games, then normalized player
names/nicknames and available shirt numbers inside those games' lineups and
appearances. Fallback requires a unique normalized name plus citizenship; known
TM birth years must imply an age from 14 through 55 in the earliest observed
season. Ambiguous candidates and duplicate TM bridges are left unmatched.
Confidence is a heuristic score, not a calibrated probability. Historical and
Indian-league TM coverage is weaker than recent European/demo competitions;
W11b adds Wikidata-only identities where no local TM record exists.
The original random sample exposed a retired Raúl/younger Raúl Blanco error; the
age check continues to reject that younger namesake. W11b evaluates the retired
player's independent Wikidata identity separately.

Career values sum our match-held-out VAEP and xG across all training matches,
excluding shootouts. VAEP includes synthetic SPADL actions for totals; top moments
sum split components of real source UUIDs and never fabricate citation IDs.
Minutes include actual stoppage/extra time from period timestamps and starting
lineups, substitutions, dismissals and temporary absences. Bench cards are not
appearances. `in_db` means replay events exist, rather than catalogue membership.

Progression counts successful passes/carries gaining at least 10 metres toward
the opposition goal, using the acting team's frame. Per-90 values divide summed
metrics by summed observed minutes. The 12×8 heatmap is row-major, bottom row
first, with each player attacking left to right; values divide by that player's
largest cell count, rather than representing probabilities. Commentary is a
snapshot of available DB sequence text and stays null outside that coverage.

Match prices use the latest valuation strictly before the source match date.
Undated reconstructed fixtures have null age and price; synthetic DB kickoffs
are never used. Season-end prices use June 30 for split-year seasons and December
31 for calendar seasons, selecting the latest valuation on or before that date.

Leaderboard filters select the observation cohort before aggregating one row per
player. VAEP/xG are totals; VAEP and progression per90 are exposure-weighted.
Market value and metric ranks are descending average ranks (ties share ranks).
For N eligible players, `underrated_score = (value_rank - metric_rank) / max(N-1,1)`.
Positive values mean performance ranks above price. Missing historical prices
produce null value rank and score. Price ranks are among known prices; missing
price coverage affects interpretation. Ranks are computed before applying limit.
When filters span teams/competitions/seasons, labels are joined and the latest
selected season end supplies the historical price.

StatsBomb is a selected and uneven corpus, especially Barcelona and Leverkusen.
These are observed-corpus summaries, not a complete professional career or a
population-wide claim about the best or most undervalued players.


## W11b identities, search and reloads

Positive `player_id` values are StatsBomb IDs. A Transfermarkt record without a
bridge into the training corpus uses `player_id=-tm_player_id`. These IDs are
stable and cannot collide with positive SB identifiers. Once a TM record acquires
a validated SB bridge, its dataset profile is the canonical searchable entry;
the redundant negative record is removed by the idempotent loader. The internal
legacy `sb_player_id` column stores both namespaces; its SQL comment documents
this convention.

Every observed StatsBomb identity retains a profile, even when no external bridge
is safe. The map still has its original seven columns and empty `_READY` marker.
The W11b matcher only extends unmatched identities and preserves original bridges.
It requires a unique candidate and a confidence of at least 0.8. Complete aliases
plus citizenship and a plausible age may establish a match; weaker names require
a P54 spell overlapping a verified match date or an exact cached TM appearance
for that club/date. Single-word nicknames require this dated club evidence.
Unqualified P54 membership is never a dated match. Colliding new TM/QID proposals
are rejected together. Confidence remains heuristic, not calibrated probability.

A profile lists its actual `sources` (`statsbomb`, `transfermarkt`, `wikidata`).
`in_dataset` is true only for observed players in the 2,924 training matches.
TM-only profiles have null `career`, `heatmap`, and `in_match`, and empty
`top_moments` and `matches`, even when a match_id query parameter is supplied.
They retain bio fields and every available valuation. Search checks full names,
nicknames and source aliases, then orders dataset entries first and current
market value descending, with stable IDs breaking ties. A precomputed substring
index preserves the previous accent-insensitive token semantics. Leaderboard
scope, formulas and response shape remain dataset-only.

The profile builder retains the existing TM-first DOB/height/nationality policy,
with Wikidata filling gaps. Contradictory birth years invalidate the QID/photo
bridge; same-year date disagreements retain the TM DOB. Remaining metadata stays
null. Commons credit/licence evidence is kept with its QID so a rebuilt mapping
cannot inherit a different identity's photo. The valuation artifact now covers
all 50,149 local TM IDs with available history, rather than only matched SB IDs.
SQL upserts are transactional; stale negative profiles are deleted, and existing
match/event/model tables are never changed.

Raw bulk responses, per-entity caches, individual Commons file metadata, request
logs and the W11 snapshot live under `data/raw/players/`. New proposals, the reviewed
30-mapping sample and the report are under `data/processed/players/`:
`new_matches.json`, `spot_check_w11b.json`, `w11b_verification.json`. The report uses
`raw/players/w11b-before/{profiles.parquet,player_map.parquet,coverage.json}` for its
baseline; preserve that snapshot when reproducing this run. Photo and identity
coverage by competition/season comes from `coverage.json`.

After loading and starting only the isolated :8040 app:

```sh
uv run --group models python -m matchmind.players.verify \
  --origin http://127.0.0.1:8040
uv run ruff check .
uv run ruff format --check .
uv run --group models pytest
```

Stop :8040 when finished. No frontend work or shared-service restart is authorized
for this workstream. The larger artifact/search startup cost is paid once per API
process; latency evidence in VERIFICATION.md distinguishes startup and requests.
