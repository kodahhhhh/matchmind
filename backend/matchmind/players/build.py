"""Build additive profiles and historical valuations from cached CC0 sources."""

import argparse
import html
import json
from urllib.parse import unquote, urlparse

import pandas as pd
import psycopg
from psycopg.types.json import Jsonb

from matchmind.config import get_settings
from matchmind.players.sources import cached_json, save_frame, table, wikidata


def plain(value: str) -> str:
    """Remove Commons metadata markup from display credits."""
    import re

    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def photos(enrichment: dict[int, dict]) -> dict[int, dict]:
    """Use a Commons thumbnail only when author and licence are present."""
    files = {}
    for pid, row in enrichment.items():
        if row.get("photo"):
            title = "File:" + unquote(
                urlparse(row["photo"]).path.rsplit("/", 1)[-1]
            ).replace("_", " ")
            files.setdefault(title, []).append(pid)
    result = {}
    titles = list(files)
    for offset in range(0, len(titles), 20):
        try:
            data = cached_json(
                "https://commons.wikimedia.org/w/api.php",
                {
                    "action": "query",
                    "format": "json",
                    "titles": "|".join(titles[offset : offset + 20]),
                    "prop": "imageinfo",
                    "iiprop": "url|extmetadata",
                    "iiurlwidth": "320",
                },
                "commons",
            )
        except Exception as exc:
            print(f"Commons batch {offset}: {type(exc).__name__}", flush=True)
            continue
        for page in data.get("query", {}).get("pages", {}).values():
            infos = page.get("imageinfo", [])
            if not infos:
                continue
            info = infos[0]
            metadata = info.get("extmetadata", {})
            author = plain(metadata.get("Artist", {}).get("value", ""))
            licence = plain(metadata.get("LicenseShortName", {}).get("value", ""))
            url = info.get("thumburl") or info.get("url")
            if (
                not author
                or not licence
                or not url
                or urlparse(url).hostname != "upload.wikimedia.org"
            ):
                continue
            for pid in files.get(page["title"], []):
                result[pid] = {
                    "photo_url": url,
                    "photo_credit": author,
                    "photo_license": licence,
                }
        print(f"Commons {min(offset + 20, len(titles))}/{len(titles)}", flush=True)
    return result


def build_profiles(enrich: bool = False) -> pd.DataFrame:
    """Write profile/history artifacts; missing metadata stays null, never guessed."""
    root = get_settings().data_dir
    output = root / "processed/players"
    mapping = pd.read_parquet(output / "player_map.parquet")
    players = table("players").set_index("player_id")
    ids = mapping.tm_player_id.dropna().astype(int).unique().tolist()
    cache = output / "wikidata.json"
    enrichment = (
        {int(k): v for k, v in json.loads(cache.read_text()).items()}
        if cache.exists()
        else {}
    )
    if enrich:
        missing = [pid for pid in ids if pid not in enrichment]
        enrichment.update(wikidata(missing))
        cache.write_text(json.dumps(enrichment))
    photo_data = photos(enrichment)
    old_path = output / "profiles.parquet"
    old = (
        pd.read_parquet(old_path).set_index("sb_player_id").to_dict("index")
        if old_path.exists()
        else {}
    )
    lineup = {}
    catalogue = json.loads((root / "catalogue/matches.json").read_text())
    for match in catalogue:
        if match["training"]:
            for team in json.loads(
                (
                    root / f"raw/statsbomb/data/lineups/{match['native_id']}.json"
                ).read_text()
            ):
                for p in team["lineup"]:
                    lineup[p["player_id"]] = p
    rows = []
    for row in mapping.to_dict("records"):
        pid = row["sb_player_id"]
        tm = (
            players.loc[int(row["tm_player_id"])].to_dict()
            if pd.notna(row["tm_player_id"])
            else {}
        )
        wd = enrichment.get(int(row["tm_player_id"]), {}) if tm else {}
        sb = lineup.get(pid, {})
        dob = tm.get("date_of_birth") or wd.get("dob")
        dob = str(dob)[:10] if pd.notna(dob) else None
        positions = sb.get("positions", [])
        nickname = sb.get("player_nickname")
        name = row["sb_name"]
        # Preserve recognizable two-word names; do not invent nicknames.
        short_name = nickname or tm.get("name") or name
        record = {
            "sb_player_id": pid,
            "name": name,
            "short_name": short_name,
            "nickname": nickname,
            "date_of_birth": dob,
            "height_cm": tm.get("height_in_cm"),
            "foot": tm.get("foot"),
            "position": tm.get("sub_position")
            or (positions[0]["position"] if positions else None),
            "nationality": tm.get("country_of_citizenship")
            or (sb.get("country") or {}).get("name"),
            "tm_player_id": row["tm_player_id"],
            "wikidata_qid": wd.get("wikidata_qid"),
            "caps": tm.get("international_caps"),
            "current_club": tm.get("current_club_name"),
            "market_value_eur": tm.get("market_value_in_eur"),
            "peak_market_value_eur": tm.get("highest_market_value_in_eur"),
            "match_confidence": row["confidence"],
            **{
                key: old.get(pid, {}).get(key)
                for key in ("photo_url", "photo_credit", "photo_license")
            },
            **(photo_data.get(int(row["tm_player_id"]), {}) if tm else {}),
        }
        # Dict expansion above must preserve unmatched profiles as well.
        if not record:
            raise AssertionError("Empty profile")
        rows.append(record)
    frame = pd.DataFrame(rows).where(pd.notna(pd.DataFrame(rows)), None)
    for col in (
        "tm_player_id",
        "caps",
        "height_cm",
        "market_value_eur",
        "peak_market_value_eur",
    ):
        frame[col] = pd.to_numeric(frame[col], errors="coerce").astype("Int64")
    save_frame(frame, output / "profiles.parquet")
    mapping["wikidata_qid"] = mapping.tm_player_id.map(
        lambda pid: (
            enrichment.get(int(pid), {}).get("wikidata_qid") if pd.notna(pid) else None
        )
    )
    save_frame(mapping, output / "player_map.parquet")
    valuations = table("player_valuations")
    valuations = valuations[valuations.player_id.isin(ids)].rename(
        columns={
            "player_id": "tm_player_id",
            "market_value_in_eur": "value_eur",
            "current_club_name": "club",
        }
    )
    valuations = (
        valuations[["tm_player_id", "date", "value_eur", "club"]]
        .drop_duplicates(["tm_player_id", "date"])
        .sort_values(["tm_player_id", "date"])
    )
    save_frame(valuations, output / "valuations.parquet")
    print(
        f"Profiles {len(frame)}; histories {len(valuations)}; "
        f"photos {frame.photo_url.notna().sum()}",
        flush=True,
    )
    return frame


def load_database(database_url: str | None = None) -> dict:
    """Apply only additive W11 SQL and upsert profiles and valuations."""
    from pathlib import Path

    output = get_settings().data_dir / "processed/players"
    profiles = pd.read_parquet(output / "profiles.parquet").to_dict("records")
    valuations = pd.read_parquet(output / "valuations.parquet").to_dict("records")
    sql_path = Path(__file__).resolve().parents[1] / "db/players.sql"
    with psycopg.connect(database_url or get_settings().database_url) as conn:
        conn.execute(sql_path.read_text())
        columns = list(profiles[0])
        assignments = ",".join(
            f"{c}=EXCLUDED.{c}" for c in columns if c != "sb_player_id"
        )
        with conn.cursor() as cursor:
            cursor.executemany(
                f"INSERT INTO player_profiles ({','.join(columns)}) "
                f"VALUES ({','.join(['%s'] * len(columns))}) "
                f"ON CONFLICT (sb_player_id) DO UPDATE SET {assignments}",
                [
                    tuple(None if pd.isna(r[c]) else r[c] for c in columns)
                    for r in profiles
                ],
            )
            cursor.executemany(
                "INSERT INTO player_valuations (tm_player_id,date,value_eur,club) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT (tm_player_id,date) DO UPDATE "
                "SET value_eur=EXCLUDED.value_eur,club=EXCLUDED.club",
                [
                    (
                        r["tm_player_id"],
                        r["date"],
                        r["value_eur"],
                        None if pd.isna(r["club"]) else r["club"],
                    )
                    for r in valuations
                ],
            )
        career_path = output / "career.json"
        if career_path.exists():
            with conn.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO player_careers (sb_player_id,summary) VALUES (%s,%s) "
                    "ON CONFLICT (sb_player_id) DO UPDATE SET summary=EXCLUDED.summary",
                    [
                        (int(pid), Jsonb(value))
                        for pid, value in json.loads(career_path.read_text()).items()
                    ],
                )
    return {"profiles": len(profiles), "valuations": len(valuations)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--enrich", action="store_true")
    parser.add_argument("--load-db", action="store_true")
    args = parser.parse_args()
    build_profiles(args.enrich)
    if args.load_db:
        print(load_database())
