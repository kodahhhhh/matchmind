"""Sync downstream flags after loading more catalogue matches into the DB.

Run once after `load-events` and the model backfill, from backend/:

    uv run python ../scripts/activate_matches.py

1. `matches.meta.demo` follows `data/catalogue/matches.json`.
2. Player career rows mark a match `in_db` when it has events in the DB, so player
   pages link to it. Updates `processed/players/{matches.parquet,career.json}` and
   the `player_careers` table the same way.

Restart the API afterwards (cached player store and catalogue).
"""

import json

import pandas as pd
import psycopg
from psycopg.types.json import Jsonb

from matchpulse.config import get_settings


def main() -> None:
    settings = get_settings()
    data = settings.data_dir
    demo = [
        m["match_id"]
        for m in json.loads((data / "catalogue/matches.json").read_text())
        if m["demo"]
    ]
    with psycopg.connect(settings.database_url) as conn:
        flagged = conn.execute(
            """UPDATE matches SET meta = jsonb_set(meta, '{demo}',
            to_jsonb(match_id = ANY(%s)))
            WHERE (meta->>'demo')::boolean IS DISTINCT FROM (match_id = ANY(%s))""",
            (demo, demo),
        ).rowcount
        loaded = {
            r[0]
            for r in conn.execute(
                "SELECT match_id FROM matches m WHERE EXISTS "
                "(SELECT 1 FROM events e WHERE e.match_id=m.match_id)"
            )
        }

        players = data / "processed/players"
        frame = pd.read_parquet(players / "matches.parquet")
        frame["in_db"] = frame.match_id.isin(loaded)
        tmp = players / "matches.tmp.parquet"
        frame.to_parquet(tmp, index=False)
        tmp.replace(players / "matches.parquet")

        careers = json.loads((players / "career.json").read_text())
        for career in careers.values():
            for match in career.get("matches") or []:
                match["in_db"] = match["match_id"] in loaded
        tmp = players / "career.tmp.json"
        tmp.write_text(json.dumps(careers))
        tmp.replace(players / "career.json")

        rows = conn.execute("SELECT sb_player_id, summary FROM player_careers")
        updates = []
        for pid, summary in rows.fetchall():
            changed = False
            for match in summary.get("matches") or []:
                now = match["match_id"] in loaded
                changed |= match.get("in_db") != now
                match["in_db"] = now
            if changed:
                updates.append((Jsonb(summary), pid))
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE player_careers SET summary=%s WHERE sb_player_id=%s", updates
            )
    print(
        json.dumps(
            {
                "demo_matches": len(demo),
                "loaded_matches": len(loaded),
                "match_meta_updated": flagged,
                "player_match_rows_in_db": int(frame.in_db.sum()),
                "player_careers_updated": len(updates),
            }
        )
    )


if __name__ == "__main__":
    main()
