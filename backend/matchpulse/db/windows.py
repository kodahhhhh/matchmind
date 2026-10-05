"""Offline loader for empirical game-state windows. Does not touch model columns.

Usage: DATA_DIR=/home/ubuntu/hackathon/data uv run python -m matchpulse.db.windows
Only analog:v1 windows are replaced. Run again after xG/VAEP/xT backfills so the
saved feature scaling, outcomes and neighbours agree with current model values.
"""

import time
from pathlib import Path

import pandas as pd
from psycopg.types.json import Jsonb

from matchpulse.api.repository import bundle, catalogue, clear_cache, connect
from matchpulse.models.gamestate import VERSION, build_windows, standardize_windows


def load_windows() -> dict:
    """Compute all demo windows off-line; publish corpus and scaling atomically."""
    start = time.monotonic()
    rows = []
    clear_cache()
    for i, mid in enumerate(catalogue(), 1):
        b = bundle(mid)
        rows.extend(
            build_windows(
                pd.DataFrame(b["events"]),
                b["match"]["markers"],
                b["match"],
                b["model_values"],
            )
        )
        if i % 25 == 0:
            print(f"windows: {i} matches, {len(rows)} states", flush=True)
    rows, scaling = standardize_windows(rows)
    with connect() as conn:
        conn.execute((Path(__file__).with_name("gamestate_api.sql")).read_text())
        conn.execute(
            "DELETE FROM gamestate_windows WHERE window_id LIKE %s", (VERSION + ":%",)
        )
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO gamestate_windows "
                "(window_id,match_id,team,minute,features,outcome,embedding) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s::vector)",
                [
                    (
                        r["window_id"],
                        r["match_id"],
                        r["team"],
                        r["minute"],
                        Jsonb(r["features"]),
                        Jsonb(r["outcome"]),
                        str(r["embedding"]),
                    )
                    for r in rows
                ],
            )
        conn.execute(
            "INSERT INTO gamestate_scaling(version,scaling) VALUES (%s,%s) ON "
            "CONFLICT(version) DO UPDATE SET "
            "scaling=EXCLUDED.scaling,built_at=now()",
            (VERSION, Jsonb(scaling)),
        )
        conn.execute("ANALYZE gamestate_windows")
    return {
        "matches": len(catalogue()),
        "windows": len(rows),
        "seconds": round(time.monotonic() - start, 2),
    }


if __name__ == "__main__":
    print(load_windows())
