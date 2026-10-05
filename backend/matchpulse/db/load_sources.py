"""W13 source loader: refuses every database except matchpulse_staging."""

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb

from matchpulse.config import get_settings
from matchpulse.db.load import EVENT_COLUMNS, apply_schema, refresh


def staging_url(database_url: str) -> str:
    """Validate parsed DB name before any connection/mutation, including init."""
    settings = conninfo_to_dict(database_url)
    if settings.get("dbname") != "matchpulse_staging":
        raise ValueError("W13 may write only to matchpulse_staging")
    return database_url


def initialize(database_url: str, embed_dim: int) -> None:
    """Create the staging database if absent and apply the existing schema."""
    staging_url(database_url)
    with psycopg.connect(
        make_conninfo(database_url, dbname="postgres"), autocommit=True
    ) as conn:
        if not conn.execute(
            "SELECT 1 FROM pg_database WHERE datname='matchpulse_staging'"
        ).fetchone():
            conn.execute("CREATE DATABASE matchpulse_staging")
    apply_schema(database_url, embed_dim)
    with psycopg.connect(database_url) as conn:
        conn.execute(Path(__file__).with_name("commentary.sql").read_text())
        conn.execute(Path(__file__).with_name("players.sql").read_text())
        conn.execute(Path(__file__).with_name("gamestate_api.sql").read_text())
        # Lite detail stays separate: no fake actions, sequences or minute_metrics.
        conn.execute(
            "CREATE TABLE IF NOT EXISTS source_lite_matches "
            "(match_id text PRIMARY KEY REFERENCES matches(match_id), "
            "payload jsonb NOT NULL)"
        )


def _upsert_match(conn: psycopg.Connection, match: dict) -> datetime:
    kickoff = datetime.fromisoformat(
        f"{match['match_date']}T{match.get('kick_off') or '00:00:00'}"
    ).replace(tzinfo=UTC)
    for side in ("home", "away"):
        team = match[side]
        conn.execute(
            "INSERT INTO teams VALUES (%s,%s) ON CONFLICT (team_id) "
            "DO UPDATE SET name=EXCLUDED.name",
            (team["id"], team["name"]),
        )
    conn.execute(
        "INSERT INTO matches VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (match_id) DO UPDATE SET source=EXCLUDED.source, "
        "competition=EXCLUDED.competition,season=EXCLUDED.season, "
        "kickoff_ts=EXCLUDED.kickoff_ts,home=EXCLUDED.home,away=EXCLUDED.away, "
        "score=EXCLUDED.score,meta=EXCLUDED.meta",
        (
            match["match_id"],
            match["source"],
            match["competition"],
            match["season"],
            kickoff,
            match["home"]["id"],
            match["away"]["id"],
            Jsonb({"home": match["home_score"], "away": match["away_score"]}),
            Jsonb(match),
        ),
    )
    return kickoff


def load_full(database_url: str, normalized: Path, scored: Path) -> int:
    """Transactional source-local replace, real model rows keyed by original IDs."""
    staging_url(database_url)
    document = json.loads(normalized.read_text())
    match, events = document["meta"], document["events"]
    if match.get("data_tier") != "full":
        raise ValueError("A lite match cannot use the full event loader")
    frame = pd.read_parquet(scored)
    ratings = frame.set_index("original_event_id").to_dict("index")
    rows = []
    with psycopg.connect(database_url) as conn:
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (match["match_id"],),
        )
        kickoff = _upsert_match(conn, match)
        for lineup in match["lineups"]:
            for p in lineup["lineup"]:
                conn.execute(
                    "INSERT INTO players VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT (player_id) DO UPDATE SET name=EXCLUDED.name",
                    (
                        p["player_id"],
                        p["player_name"],
                        lineup["team_id"],
                        p["positions"][0]["position"] if p["positions"] else None,
                    ),
                )
        for event in events:
            model = ratings.get(event["id"], {})
            loc = event.get("location")
            end = (event.get("pass") or event.get("carry") or {}).get(
                "end_location", loc
            )

            def xy(value: list | None) -> tuple:
                return (
                    (value[0] * 105 / 120, 68 - value[1] * 68 / 80)
                    if value
                    else (None, None)
                )

            def model_value(key: str, model: dict = model) -> float | None:
                value = model.get(key)
                return None if value is None or pd.isna(value) else float(value)

            side = "home" if event["team"]["id"] == match["home"]["id"] else "away"
            sid = f"{match['match_id']}:s{event['possession']}"
            rows.append(
                (
                    f"{match['match_id']}:{event['index']}",
                    match["match_id"],
                    kickoff + timedelta(seconds=event["elapsed_match_seconds"]),
                    event["period"],
                    event["minute"],
                    event["second"],
                    side,
                    event.get("player", {}).get("id"),
                    event["type"]["name"],
                    event.get("spadl_result"),
                    event.get("spadl_type") or "non_action",
                    event.get("spadl_result"),
                    event.get("spadl_bodypart"),
                    *xy(loc),
                    *xy(end),
                    model_value("xg"),
                    model_value("vaep_value"),
                    model_value("offensive_value"),
                    model_value("defensive_value"),
                    model_value("xt"),
                    None,
                    sid,
                    Jsonb(event),
                )
            )
        # Replacement invalidates source-dependent derived data within staging only.
        for table in ("commentary", "gamestate_windows", "sequences", "events"):
            conn.execute(f"DELETE FROM {table} WHERE match_id=%s", (match["match_id"],))
        with (
            conn.cursor() as cur,
            cur.copy(f"COPY events ({','.join(EVENT_COLUMNS)}) FROM STDIN") as copy,
        ):
            for row in rows:
                copy.write_row(row)
        groups = {}
        for row in rows:
            groups.setdefault(row[-2], []).append(row)
        for sid, group in groups.items():
            conn.execute(
                "INSERT INTO sequences "
                "(sequence_id,match_id,team,start_ts,end_ts,n_events,danger,events) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    sid,
                    match["match_id"],
                    group[0][6],
                    min(r[2] for r in group),
                    max(r[2] for r in group),
                    len(group),
                    sum(max(r[18] or 0, 0) for r in group),
                    [int(r[0].rsplit(":", 1)[1]) for r in group],
                ),
            )
    return len(rows)


def load_lite(database_url: str, path: Path) -> None:
    """Store available payload only. Do not put incomplete shots in full metrics."""
    staging_url(database_url)
    document = json.loads(path.read_text())
    match = document["meta"]
    if match.get("data_tier") != "lite":
        raise ValueError("Expected a lite payload")
    with psycopg.connect(database_url) as conn:
        _upsert_match(conn, match)
        conn.execute(
            "INSERT INTO source_lite_matches VALUES (%s,%s) "
            "ON CONFLICT (match_id) DO UPDATE SET payload=EXCLUDED.payload",
            (match["match_id"], Jsonb(document)),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "load", "refresh"])
    parser.add_argument("--full-limit", type=int, default=20)
    parser.add_argument("--lite-limit", type=int, default=20)
    args = parser.parse_args()
    if min(args.full_limit, args.lite_limit) < 0:
        parser.error("Match limits must be nonnegative")
    settings = get_settings()
    url = staging_url(settings.database_url)
    if args.command == "init":
        initialize(url, settings.embed_dim)
    elif args.command == "refresh":
        refresh(url)
    else:
        root = settings.data_dir / "sources"
        accepted = json.loads((root / "catalogue_dynasty.json").read_text())
        full = [
            root / f"dynasty/normalized/{m['native_id']}.json"
            for m in sorted(accepted, key=lambda m: str(m["native_id"]))
        ][: args.full_limit]
        lite = sorted((root / "understat/lite").glob("*.json"))[: args.lite_limit]
        count = 0
        for p in full:
            count += load_full(url, p, root / "dynasty/scored" / f"{p.stem}.parquet")
        for p in lite:
            load_lite(url, p)
        print(json.dumps({"full": len(full), "lite": len(lite), "events": count}))


if __name__ == "__main__":
    main()
