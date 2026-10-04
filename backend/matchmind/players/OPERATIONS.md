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
uv run --group models python -m matchmind.players.matching
uv run --group models python -m matchmind.players.build
uv run --group models python -m matchmind.players.career
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
Requests are sequential with a delay of at least one second. On HTTP 429, 403 or
503, the current source's remaining batches stop. Unavailable metadata stays
null. Photos are Commons API derivatives at `upload.wikimedia.org` or
`thumb.wikimedia.org`, with author credit and licence. Conflicting TM/Wikidata
birth years invalidate the QID/photo bridge. No provider requests occur in the
API, metrics or models at request time.

`--load-db` applies `db/players.sql` and upserts only `player_profiles`,
`player_valuations` and `player_careers`. It does not change existing match/event
rows or reset model outputs. Runtime reads the published files; restart the
consumer API process after rebuilding artifacts to replace its process caches.
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
`leaderboard_example.json`. No existing fixture or schema shape changes.
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
Indian-league coverage is much weaker than recent European/demo competitions.
The original random sample exposed a retired Raúl/younger Raúl Blanco error; the
age check rejects it and the retired player remains unmatched.

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
