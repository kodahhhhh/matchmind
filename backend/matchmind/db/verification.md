# W5 verification — 2026-10-03

Environment: Python 3.12.3, PostgreSQL 17 image `timescale/timescaledb-ha:pg17`,
TimescaleDB 2.30.2, pgvector 0.8.6. Image digest:
`sha256:2fcc39a5d4c8a65f58691ef92c7819df5773db72397b2dd8493f114659b519c2`.
Docker Compose and uv were installed on the host for this task.

All runs used `DATA_DIR=/home/ubuntu/hackathon/data` from the W5 worktree.

| Command | Result | Elapsed |
|---|---|---|
| `uv run python -m matchmind.db.load init` | Both extensions and schema created | 0.048 s |
| `uv run python -m matchmind.db.load load-catalogue` | Complete catalogue and lineups | 2.748 s |
| `uv run python -m matchmind.db.load load-events --source raw --demo-only --workers 4` | 493 matches | 48.543 s |
| `uv run python -m matchmind.db.load refresh` | All populated match ranges refreshed | 30.072 s |
| `uv run ruff check .` | Pass | — |
| `uv run ruff format --check .` | 6 files formatted | — |
| `uv run pytest` | 9 passed | 7.17 s |

The first unbounded refresh and a global min/max refresh were canceled after
observing repeated empty-range work. The final refresh implementation merges
populated match ranges. The 30.072 s result is the successful full refresh after
those partial attempts, not a clean cold rebuild benchmark. The final tests use
a fresh disposable database and pass with this implementation.

| Relation/count | Rows |
|---|---:|
| matches | 4,235 |
| teams | 354 |
| players | 11,889 |
| events | 1,752,302 |
| distinct event matches | 493 |
| sequences | 89,482 |
| minute_metrics | 94,082 |
| minute_metrics_view | 94,938 |
| commentary | 0 (ready for W8) |
| gamestate_windows | 0 (ready for W6) |

All five event model columns are NULL. Aggregate event-count sum is 1,752,041,
exactly matching the non-shootout event count across all demo matches.

World Cup final `sb:3869685`: 4,407 events; six goals before period 5, six converted
shootout penalties in period 5; coordinates constrained to 105x68 metres.
The timeline has 138 period/minute rows per team (276 total), clock minutes
0–124, with overlapping stoppage/next-period minutes preserved separately.
It counts 4,386 non-shootout events and 30 non-shootout shots.

Database size: **2,416,129,715 bytes** via `pg_database_size` (about 2.25 GiB).
Physical PGDATA allocation from `du -sh`: **3.3G**, including **1.1G pg_wal**.
Compression is configured, but chunks have not been compressed during loading.

Timeline benchmark on a local psycopg connection, fetching all columns and rows:

```sql
SELECT * FROM minute_metrics_view
WHERE match_id = 'sb:3869685'
ORDER BY period, minute, team;
```

- First timed fetch: **3.410 ms** (cache already warmed by count checks).
- Following 30 fetches: median **2.441 ms**, p95 **2.797 ms**, maximum **3.011 ms**.
- `EXPLAIN (ANALYZE, BUFFERS)`: planning **0.634 ms**, execution **0.921 ms**.
- These are warm local DB timings, not API/network or cold-cache latency.

Integration tests cover schema reapplication with data, catalogue upserts,
hypertable/continuous aggregate existence, both HNSW indexes, vector operations,
raw count/goals/coordinates, NULL model values, timeline counts and fractions,
period overlap, match reload and refresh, transaction rollback on COPY failure,
stable synthetic dates, explicit SPADL stub, generated text search, and embedding
dimension mismatch rejection.

The test databases were removed. `matchmind-db-1` is left running and healthy on
5432 with the named volume `matchmind_db_data`. No other task process remains.
See README.md in this directory for the integration contract and provisional
possession/progression definitions.
