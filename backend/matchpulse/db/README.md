# W5 database

Run from the worktree/repository root:

```sh
docker compose up -d --wait db
cd backend
uv sync
export DATA_DIR=/home/ubuntu/hackathon/data
uv run python -m matchpulse.db.load init
uv run python -m matchpulse.db.load load-catalogue
uv run python -m matchpulse.db.load load-events --source raw --demo-only --workers 4
uv run python -m matchpulse.db.load refresh
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

The Compose project is explicitly `matchmind`, so running the merged compose file
from the main checkout reuses `matchmind-db-1` and `matchmind_db_data`. The database
is available on localhost:5432 (user/password/database: `matchmind`). Tests create
and drop their own uniquely named database; they require CREATE DATABASE rights
and the local catalogue/raw data. They never clear the shared demo database.

`init` applies `schema.sql` idempotently and checks that an existing commentary
vector dimension agrees with `EMBED_DIM` (default 1536; HNSW vector limit 2000).
The SQL also works standalone with the default dimension. Config reads
`backend/.env` regardless of current working directory. No Azure credentials are
needed by the DB loader.

## Loading and identifiers

`load-catalogue` reads every catalogue match and every lineup file. Teams and
players use native numeric StatsBomb IDs; matches use `sb:<native_id>`. Historical
lineups are retained in `matches.meta.lineups`. `players.team` and `position` are
the last occurrence in catalogue traversal, not historical membership.

Missing match dates get July 1 of the season's first year plus the zero-based
native-ID-sorted rank of undated matches in that competition/season, in days.
`meta.synthetic_kickoff` marks these storage timestamps. Dated source kickoffs
have no timezone: their wall clock is stored as UTC without claiming an actual
UTC kickoff. Source date/kickoff remain in meta for display.

`load-events --match-id sb:3869685 --source raw --workers 1` replaces one match in
a transaction. Advisory locks serialize concurrent loads of the same match;
failed COPY rolls back its DELETE. Different matches load in worker processes.
Do raw loads **before** model backfills: raw reloads reset event model columns to
NULL. Re-run `refresh` after event/model changes. Raw loading upserts possession
sequences, retains existing danger and commentary, and assumes unchanged raw
source data. If source possessions change, invalidate downstream commentary and
remove obsolete sequences as part of that source migration.

Event IDs use the original one-based StatsBomb `index`, e.g. `sb:3869685:192`.
Sequence IDs use the source possession number, e.g. `sb:3869685:s14`.
`sequences.events` is the ordered integer array of those source indices. Sequence
team is the possession owner; an event in it can belong to the defending team.
`danger` is NULL until W4 computes it. Empty commentary/game-state tables and
HNSW/GIN indexes are ready for W8/W6.

`--source spadl` deliberately raises `NotImplementedError`. The module docstring
specifies `data/processed/spadl/{match_id}.parquet` and expected columns for W2.
W2 and W5 must coordinate source-ID changes before replacing raw events.

## Events and metrics

Events columns:

```text
event_id, match_id, ts, period, minute, second, team, player_id,
type, result, type_name, result_name, bodypart_name,
x, y, end_x, end_y, xg, vaep, vaep_off, vaep_def, xt, sb_xg,
sequence_id, extra
```

`type`/`result` preserve raw labels (a completed pass has no raw outcome).
`type_name` is a snake-case raw label, not a full SPADL action conversion.
`result_name` normalizes available outcomes to success/fail, otherwise NULL;
missing pass/carry outcomes are successful. `extra` is the full original raw
event, retaining UUID, coordinates, duration, cards, substitutions, shot details,
related events and player metadata. `sb_xg` is source-only validation data; no
StatsBomb xG is copied into `xg`.

Coordinates are converted with x * 105/120 and 68 - y * 68/80. StatsBomb uses the
acting team's attacking frame; no away-team or half rotation is applied in
storage. Out-of-pitch endpoints are clipped to the pitch; originals remain in
extra. W2 must agree on the attacking frame before loading SPADL, and W0/API
must orient responses according to AGENTS.md. Do not blindly flip both the raw
coordinates and a second time in the API.

`ts = kickoff_ts + minute*60 + second + source fractional second`. Retaining
period separately matters: first-half stoppage and second-half clock minutes
overlap. The hypertable primary key is `(event_id, ts)` because Timescale unique
keys must include the partition key. Match replacement preserves event-ID
uniqueness within the loader. Events use 90-day chunks and have `(match_id, ts)`
and `(match_id, sequence_id)` indexes.

`minute_metrics` is a materialized-only continuous aggregate grouped by bucket,
match, team and period. `minute_metrics_view` emits both teams for each observed
bucket and excludes shootouts. Order timeline queries by `period, minute, team`:

```sql
SELECT * FROM minute_metrics_view
WHERE match_id = 'sb:3869685'
ORDER BY period, minute, team;
```

The view returns event_count, passes, successful_passes, shots, xg, vaep,
final_third_actions, progressive_actions, possession and field_tilt. `xg` and
`vaep` sums remain NULL while models are absent; don't present these as zero.
Possession is currently a **pass-share proxy**, not timed possession. Field tilt
is the share of actions starting at x > 70 in the acting team's frame.
Progressive actions are successful passes/carries gaining at least 10m on x.
W4 should finalize these provisional metric definitions before API integration.
A zero denominator yields NULL, not a misleading 0/0 split. The view fills the
other team's missing row, but does not invent minutes with no events by either
team. Period 5 events remain queryable in `events`.

Refresh merges overlapping match time ranges and refreshes only those populated
ranges, avoiding the years of empty buckets between competitions. No automatic
refresh policy is installed: run the CLI after loading or model backfills.
Compression is enabled but no compression policy runs during loading/backfills;
compress old chunks manually after those writes are complete if desired.
