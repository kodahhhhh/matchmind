"""Explicit DB orchestration boundary; model mathematics remains pure/local.

Run after raw reloads: uv run --group models python -m matchpulse.models.backfill
[--match-id sb:3869685]. COPY a temporary table and issue one UPDATE FROM.
Refresh separately with python -m matchpulse.db.load refresh.
"""

import argparse
import json
from typing import Any

import pandas as pd
import psycopg
from psycopg.rows import dict_row

from matchpulse.config import get_settings
from matchpulse.models.common import catalogue, data_dir, save_json, timestamp

COLUMNS = ["match_id", "original_event_id", "xg", "vaep", "vaep_off", "vaep_def", "xt"]


def join_outputs(
    actions: pd.DataFrame, shots: pd.DataFrame, xt: pd.DataFrame
) -> pd.DataFrame:
    """Sum split interception/pass actions by UUID; discard synthetic dribbles.

    xG is joined only after aggregation, so a shot's probability is never doubled.
    Unknown/inapplicable values stay NULL rather than silently becoming zero.
    """
    actions = actions.merge(
        xt[["action_id", "xt"]], on="action_id", validate="one_to_one"
    )
    actions = actions[actions.original_event_id.notna()].copy()
    values = (
        actions.groupby("original_event_id")[
            ["vaep_value", "offensive_value", "defensive_value", "xt"]
        ]
        .sum(min_count=1)
        .rename(
            columns={
                "vaep_value": "vaep",
                "offensive_value": "vaep_off",
                "defensive_value": "vaep_def",
            }
        )
    )
    values = values.join(
        shots.set_index("original_event_id")[["xg"]], how="outer", validate="one_to_one"
    )
    return values.reset_index()


def backfill(match_id: str | None = None) -> dict[str, Any]:
    matches = [
        m
        for m in catalogue()
        if m["demo"] and (match_id is None or m["match_id"] == match_id)
    ]
    if not matches:
        raise ValueError("No demo matches selected")
    shots = pd.read_parquet(data_dir() / "processed/xg/shots.parquet")
    frames = []
    for match in matches:
        native = match["native_id"]
        actions = pd.read_parquet(data_dir() / f"processed/vaep/{native}.parquet")
        xt = pd.read_parquet(data_dir() / f"processed/xt/{native}.parquet")
        values = join_outputs(actions, shots[shots.game_id == native], xt)
        values["match_id"] = match["match_id"]
        frames.append(values[COLUMNS])
    values = pd.concat(frames, ignore_index=True)
    with psycopg.connect(get_settings().database_url, row_factory=dict_row) as conn:
        # Same locks as the raw loader; stable ordering prevents deadlocks.
        for match in sorted(matches, key=lambda m: m["match_id"]):
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (match["match_id"],),
            )
        conn.execute(
            """CREATE TEMP TABLE model_values (match_id text,
            original_event_id text, xg double precision, vaep double precision,
            vaep_off double precision, vaep_def double precision,
            xt double precision, PRIMARY KEY(match_id, original_event_id))
            ON COMMIT DROP"""
        )
        with conn.cursor().copy("COPY model_values FROM STDIN") as copy:
            for row in values.itertuples(index=False, name=None):
                copy.write_row(tuple(None if pd.isna(v) else v for v in row))
        conn.execute("ANALYZE model_values")
        updated = conn.execute("""UPDATE events e SET xg=m.xg, vaep=m.vaep,
            vaep_off=m.vaep_off, vaep_def=m.vaep_def, xt=m.xt
            FROM model_values m WHERE e.match_id=m.match_id
            AND e.extra->>'id'=m.original_event_id
            AND (e.xg,e.vaep,e.vaep_off,e.vaep_def,e.xt) IS DISTINCT FROM
                (m.xg,m.vaep,m.vaep_off,m.vaep_def,m.xt)""").rowcount
        coverage = conn.execute(
            """SELECT e.type, count(*) AS raw_events,
            count(m.original_event_id) AS joined, count(e.xg) AS xg,
            count(e.vaep) AS vaep, count(e.xt) AS xt
            FROM events e LEFT JOIN model_values m ON e.match_id=m.match_id
            AND e.extra->>'id'=m.original_event_id
            WHERE e.match_id = ANY(%s) GROUP BY e.type ORDER BY e.type""",
            ([m["match_id"] for m in matches],),
        ).fetchall()
        missing_goals = conn.execute(
            """SELECT count(*) AS n FROM events
            WHERE match_id=ANY(%s) AND type='Shot'
            AND extra->'shot'->'outcome'->>'name'='Goal' AND xg IS NULL""",
            ([m["match_id"] for m in matches],),
        ).fetchone()["n"]
        if missing_goals:
            raise ValueError(f"{missing_goals} goal shots missing xG; rolling back")
    report = {
        "date": timestamp(),
        "n_matches": len(matches),
        "n_model_rows": len(values),
        "updated": updated,
        "missing_goal_xg": missing_goals,
        "coverage_by_type": coverage,
    }
    name = (
        "backfill.json"
        if match_id is None
        else f"backfill_{match_id.replace(':', '_')}.json"
    )
    save_json(name, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--match-id")
    args = parser.parse_args()
    match = args.match_id
    if match and not match.startswith("sb:"):
        match = f"sb:{match}"
    print(json.dumps(backfill(match), indent=2))


if __name__ == "__main__":
    main()
