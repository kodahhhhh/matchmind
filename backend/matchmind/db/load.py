"""Offline database loaders. Always set DATA_DIR when running from a worktree.

Commands: init, load-catalogue, load-events --source raw --demo-only, refresh.
Raw event indices are StatsBomb's one-based ``index``, not list offsets. Storage
coordinates use the acting team's frame, in metres with bottom-left origin.
``extra`` retains the entire raw event (including original coordinates/UUID).

Future ``--source spadl`` reads DATA_DIR/processed/spadl/{match_id}.parquet.
Expected columns: event_id (sb:<native_id>:<action_index>), match_id, action_index,
period, minute, second, team ('home'/'away'), player_id, type_name, result_name,
bodypart_name, x, y, end_x, end_y, sequence_id; nullable model fields xg, vaep,
vaep_off, vaep_def, xt, sb_xg; optional extra dict. Coordinates must be 105x68
metres in the acting team's attacking frame; ts is derived from match kickoff
and match-clock seconds. SPADL and raw IDs must never coexist for one match.
A source switch must explicitly invalidate dependent sequences/commentary.
"""

import argparse
import json
import re
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from matchmind.config import get_settings

EVENT_COLUMNS = (
    "event_id",
    "match_id",
    "ts",
    "period",
    "minute",
    "second",
    "team",
    "player_id",
    "type",
    "result",
    "type_name",
    "result_name",
    "bodypart_name",
    "x",
    "y",
    "end_x",
    "end_y",
    "xg",
    "vaep",
    "vaep_off",
    "vaep_def",
    "xt",
    "sb_xg",
    "sequence_id",
    "extra",
)


def apply_schema(database_url: str, embed_dim: int = 1536) -> None:
    """Apply idempotent DDL, refusing to silently change embedding dimensions."""
    with psycopg.connect(database_url) as conn:
        conn.execute(
            "SELECT set_config('matchmind.embed_dim', %s, true)", (str(embed_dim),)
        )
        conn.execute(Path(__file__).with_name("schema.sql").read_text())


def read_catalogue(data_dir: Path) -> list[dict[str, Any]]:
    """Read the complete catalogue, including reconstructed matches."""
    return json.loads((data_dir / "catalogue/matches.json").read_text())


def catalogue_kickoffs(matches: list[dict[str, Any]]) -> dict[str, datetime]:
    """Use source wall-clock dates or the synthetic rule documented in SQL."""
    ranks: dict[tuple[str, str], int] = defaultdict(int)
    result = {}
    for match in sorted(matches, key=lambda m: m["native_id"]):
        if match["match_date"]:
            kickoff = datetime.fromisoformat(
                f"{match['match_date']}T{match.get('kick_off') or '00:00:00'}"
            ).replace(tzinfo=UTC)
        else:
            key = (match["competition"], match["season"])
            year = int(re.search(r"\d{4}", match["season"])[0])
            kickoff = datetime(year, 7, 1, tzinfo=UTC) + timedelta(days=ranks[key])
            ranks[key] += 1
        result[match["match_id"]] = kickoff
    return result


def load_catalogue(database_url: str, data_dir: Path) -> dict[str, int]:
    """Upsert every catalogue match and lineup; keep historical lineups in meta."""
    matches = read_catalogue(data_dir)
    kickoffs = catalogue_kickoffs(matches)
    teams = {}
    players = {}
    match_rows = []
    for match in matches:
        lineups = json.loads(
            (
                data_dir / "raw/statsbomb/data/lineups" / f"{match['native_id']}.json"
            ).read_text()
        )
        for side in ("home", "away"):
            team = match[side]
            teams[team["id"]] = (team["id"], team["name"])
        for lineup in lineups:
            teams[lineup["team_id"]] = (lineup["team_id"], lineup["team_name"])
            for player in lineup["lineup"]:
                positions = player.get("positions", [])
                players[player["player_id"]] = (
                    player["player_id"],
                    player["player_name"],
                    lineup["team_id"],
                    positions[0]["position"] if positions else None,
                )
        match_rows.append(
            (
                match["match_id"],
                "sb",
                match["competition"],
                match["season"],
                kickoffs[match["match_id"]],
                match["home"]["id"],
                match["away"]["id"],
                Jsonb({"home": match["home_score"], "away": match["away_score"]}),
                Jsonb(
                    {
                        **match,
                        "lineups": lineups,
                        "synthetic_kickoff": not bool(match["match_date"]),
                    }
                ),
            )
        )
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO teams VALUES (%s,%s) ON CONFLICT (team_id) "
            "DO UPDATE SET name=EXCLUDED.name",
            teams.values(),
        )
        cur.executemany(
            "INSERT INTO matches VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (match_id) DO UPDATE SET source=EXCLUDED.source, "
            "competition=EXCLUDED.competition, season=EXCLUDED.season, "
            "kickoff_ts=EXCLUDED.kickoff_ts, home=EXCLUDED.home, away=EXCLUDED.away, "
            "score=EXCLUDED.score, meta=EXCLUDED.meta",
            match_rows,
        )
        cur.executemany(
            "INSERT INTO players VALUES (%s,%s,%s,%s) ON CONFLICT (player_id) "
            "DO UPDATE SET name=EXCLUDED.name, team=EXCLUDED.team, "
            "position=EXCLUDED.position",
            players.values(),
        )
    return {"matches": len(matches), "teams": len(teams), "players": len(players)}


def coordinates(location: list[float] | None) -> tuple[float | None, float | None]:
    """Convert raw 120x80 top-left coordinates; clip off-pitch endpoints.

    Shots can end outside the pitch. Original values remain in extra; clipping
    makes the relational coordinates safe for the pitch viewBox.
    """
    if not location:
        return None, None
    return (
        min(105.0, max(0.0, location[0] * 105 / 120)),
        min(68.0, max(0.0, 68 - location[1] * 68 / 80)),
    )


def snake_name(name: str) -> str:
    """Normalize StatsBomb labels without claiming a complete SPADL conversion."""
    return name.lower().replace(" ", "_").replace("*", "")


def raw_event_row(
    event: dict[str, Any], match: dict[str, Any], kickoff: datetime
) -> tuple[Any, ...]:
    """Map one raw event while retaining unmodified source data in extra."""
    event_type = event["type"]["name"]
    type_name = snake_name(event_type)
    detail = event.get(type_name, {})
    outcome = detail.get("outcome", {}).get("name")
    if event_type in ("Pass", "Carry") and outcome is None:
        result_name = "success"
    elif outcome in ("Complete", "Won", "Success", "Success In Play", "Goal"):
        result_name = "success"
    elif outcome is not None:
        result_name = "fail"
    else:
        result_name = None
    bodypart = detail.get("body_part", {}).get("name")
    x, y = coordinates(event.get("location"))
    end_x, end_y = coordinates(detail.get("end_location"))
    team_id = event["team"]["id"]
    if team_id not in (match["home"]["id"], match["away"]["id"]):
        raise ValueError(f"Unexpected team for {match['match_id']}: {team_id}")
    team = "home" if team_id == match["home"]["id"] else "away"
    # Timestamp's fraction preserves sub-second order; minute already includes
    # the nominal period offset. Never add 45/90 again or drop stoppage time.
    fraction = float("0." + event.get("timestamp", "0.0").split(".")[-1])
    ts = kickoff + timedelta(seconds=event["minute"] * 60 + event["second"] + fraction)
    sequence = f"{match['match_id']}:s{event['possession']}"
    return (
        f"{match['match_id']}:{event['index']}",
        match["match_id"],
        ts,
        event["period"],
        event["minute"],
        event["second"],
        team,
        event.get("player", {}).get("id"),
        event_type,
        outcome,
        type_name,
        result_name,
        snake_name(bodypart) if bodypart else None,
        x,
        y,
        end_x,
        end_y,
        None,
        None,
        None,
        None,
        None,
        event.get("shot", {}).get("statsbomb_xg"),
        sequence,
        Jsonb(event),
    )


def load_raw_match(database_url: str, data_dir: Path, match: dict[str, Any]) -> int:
    """Atomically replace a match using COPY; preserve downstream commentary.

    An advisory transaction lock serializes same-match re-runs. Upsert raw
    possession sequences, but never overwrite a W4 danger value. Model columns
    on events are reset to NULL: run raw loading BEFORE model backfills.
    """
    events = json.loads(
        (
            data_dir / "raw/statsbomb/data/events" / f"{match['native_id']}.json"
        ).read_text()
    )
    with psycopg.connect(database_url) as conn:
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (match["match_id"],),
        )
        stored = conn.execute(
            "SELECT kickoff_ts FROM matches WHERE match_id=%s", (match["match_id"],)
        ).fetchone()
        if stored is None:
            raise ValueError("Run load-catalogue before load-events")
        rows = [raw_event_row(event, match, stored[0]) for event in events]
        conn.execute("DELETE FROM events WHERE match_id=%s", (match["match_id"],))
        with conn.cursor().copy(
            sql.SQL("COPY events ({}) FROM STDIN").format(
                sql.SQL(",").join(map(sql.Identifier, EVENT_COLUMNS))
            )
        ) as copy:
            for row in rows:
                copy.write_row(row)
        sequences: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
        for row in rows:
            sequences[row[-2]].append(row)
        sequence_rows = []
        for sequence_id, actions in sequences.items():
            owner = actions[0][-1].obj["possession_team"]["id"]
            sequence_rows.append(
                (
                    sequence_id,
                    match["match_id"],
                    "home" if owner == match["home"]["id"] else "away",
                    min(a[2] for a in actions),
                    max(a[2] for a in actions),
                    len(actions),
                    [a[-1].obj["index"] for a in actions],
                )
            )
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO sequences (sequence_id,match_id,team,start_ts,end_ts,"
                "n_events,events) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (sequence_id) DO UPDATE SET team=EXCLUDED.team, "
                "start_ts=EXCLUDED.start_ts,end_ts=EXCLUDED.end_ts, "
                "n_events=EXCLUDED.n_events,events=EXCLUDED.events",
                sequence_rows,
            )
    return len(rows)


def load_spadl_match(database_url: str, data_dir: Path, match: dict[str, Any]) -> int:
    """Future parquet loader: see module docstring for the required columns."""
    raise NotImplementedError(
        "SPADL loading awaits W2; expected data/processed/spadl/{match_id}.parquet. "
        "See matchmind.db.load module docstring for the column contract."
    )


def load_events(
    database_url: str,
    data_dir: Path,
    *,
    source: str = "raw",
    demo_only: bool = False,
    match_id: str | None = None,
    workers: int = 4,
) -> dict[str, int]:
    """Bulk load independent matches in worker processes; fail on any error."""
    matches = [
        m
        for m in read_catalogue(data_dir)
        if (not demo_only or m["demo"])
        and (match_id is None or m["match_id"] == match_id)
    ]
    if not matches:
        raise ValueError("No catalogue matches selected")
    if source == "spadl":
        load_spadl_match(database_url, data_dir, matches[0])
    if source != "raw":
        raise ValueError(f"Unsupported source: {source}")
    count = 0
    if workers == 1:
        for match in matches:
            count += load_raw_match(database_url, data_dir, match)
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(load_raw_match, database_url, data_dir, m): m[
                    "match_id"
                ]
                for m in matches
            }
            for completed, future in enumerate(as_completed(futures), 1):
                try:
                    count += future.result()
                except Exception as exc:
                    raise RuntimeError(f"Failed loading {futures[future]}") from exc
                if completed % 50 == 0:
                    print(f"Loaded {completed}/{len(matches)} matches", flush=True)
    return {"matches": len(matches), "events": count}


def refresh(database_url: str) -> None:
    """Refresh all history after loading/backfilling, including invalidations."""
    with psycopg.connect(database_url, autocommit=True) as conn:
        # Refresh populated match ranges, not the years of empty buckets
        # between competitions. Recent Timescale versions batch those empty
        # ranges too. Merge overlapping matches to avoid repeated work.
        ranges = conn.execute(
            "SELECT time_bucket(INTERVAL '1 minute', min(ts)) AS start, "
            "time_bucket(INTERVAL '1 minute', max(ts)) + INTERVAL '1 minute' "
            "FROM events GROUP BY match_id ORDER BY start"
        ).fetchall()
        merged: list[tuple[datetime, datetime]] = []
        for start, end in ranges:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        for bounds in merged:
            conn.execute(
                "CALL refresh_continuous_aggregate("
                "'minute_metrics', %s::timestamptz, %s::timestamptz)",
                bounds,
            )
        conn.execute("ANALYZE events")
        conn.execute("ANALYZE minute_metrics")


def main() -> None:
    """Run the offline loader CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    commands.add_parser("load-catalogue")
    commands.add_parser("refresh")
    events = commands.add_parser("load-events")
    events.add_argument("--source", choices=["raw", "spadl"], default="raw")
    events.add_argument("--demo-only", action="store_true")
    events.add_argument("--match-id")
    events.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    settings = get_settings()
    start = perf_counter()
    counts: dict[str, int] = {}
    if args.command == "init":
        apply_schema(settings.database_url, settings.embed_dim)
    elif args.command == "load-catalogue":
        counts = load_catalogue(settings.database_url, settings.data_dir)
    elif args.command == "load-events":
        if args.workers < 1:
            parser.error("--workers must be positive")
        counts = load_events(
            settings.database_url,
            settings.data_dir,
            source=args.source,
            demo_only=args.demo_only,
            match_id=args.match_id,
            workers=args.workers,
        )
    else:
        refresh(settings.database_url)
    print(
        json.dumps(
            {
                "command": args.command,
                **counts,
                "seconds": round(perf_counter() - start, 3),
            }
        )
    )


if __name__ == "__main__":
    main()
