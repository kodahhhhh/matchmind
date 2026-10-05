"""Build additive profiles and historical valuations from cached CC0 sources."""

import argparse
import html
import json
from urllib.parse import unquote, urlparse

import httpx
import pandas as pd
import psycopg
from psycopg.types.json import Jsonb

from matchpulse.config import get_settings
from matchpulse.players.bulk import atomic_json, raw_directory, read_descriptions
from matchpulse.players.bulk import request_json as cached_json
from matchpulse.players.sources import save_frame, table


def plain(value: str) -> str:
    """Remove Commons metadata markup from display credits."""
    import re

    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def free_license(licence: str) -> bool:
    """Allow explicit free licences; reject noncommercial/no-derivatives terms."""
    import re

    if re.search(r"\b(?:NC|ND)\b", licence, flags=re.I):
        return False
    return bool(
        re.fullmatch(
            r"(?:CC BY(?:-SA)? (?:[1-4]\.0|2\.5)(?: [a-z-]+)?|"
            r"CC0(?: 1\.0)?|Public domain|PDM(?: 1\.0)?|"
            r"GFDL(?: [12]\.[0-3])?|FAL(?: [12]\.[0-3])?|Free Art License)",
            licence,
            flags=re.I,
        )
    )


def photos(enrichment: dict[int, dict]) -> dict[int, dict]:
    """Use credited Commons derivatives only with explicitly free licences."""
    files = {}
    for pid, row in enrichment.items():
        if row.get("photo"):
            photo = row["photo"]
            filename = (
                unquote(urlparse(photo).path.rsplit("/", 1)[-1])
                if "://" in photo
                else photo
            )
            title = "File:" + filename.replace("_", " ")
            files.setdefault(title, []).append(pid)
    result = {}
    import hashlib

    file_cache = raw_directory() / "commons-files"
    file_cache.mkdir(parents=True, exist_ok=True)
    pages = {}
    for title in files:
        path = file_cache / (hashlib.sha256(title.encode()).hexdigest() + ".json")
        if path.exists():
            pages[title] = json.loads(path.read_text())
    titles = [title for title in files if title not in pages]
    for offset in range(0, len(titles), 50):
        try:
            data = cached_json(
                "https://commons.wikimedia.org/w/api.php",
                {
                    "action": "query",
                    "format": "json",
                    "titles": "|".join(titles[offset : offset + 50]),
                    "prop": "imageinfo",
                    "iiprop": "url|extmetadata",
                    "iiurlwidth": "400",
                    "maxlag": "5",
                    "redirects": "1",
                },
                "commons",
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            print(f"Commons batch {offset}: HTTP {status}", flush=True)
            if status in {429, 403, 503}:
                break
            continue
        except (httpx.HTTPError, ValueError) as exc:
            print(f"Commons batch {offset}: {type(exc).__name__}", flush=True)
            continue
        query = data.get("query", {})
        redirects = {
            r["from"]: r["to"]
            for field in ("normalized", "redirects")
            for r in query.get(field, [])
        }
        fetched = {p["title"]: p for p in query.get("pages", {}).values()}
        for title in titles[offset : offset + 50]:
            canonical = title
            seen = set()
            while canonical in redirects and canonical not in seen:
                seen.add(canonical)
                canonical = redirects[canonical]
            if canonical in fetched:
                pages[title] = fetched[canonical]
                atomic_json(
                    file_cache / (hashlib.sha256(title.encode()).hexdigest() + ".json"),
                    pages[title],
                )
        print(
            f"Commons {min(offset + 50, len(titles))}/{len(titles)} new files",
            flush=True,
        )
    for title, page in pages.items():
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
            or not free_license(licence)
            or not url
            or urlparse(url).hostname
            not in {"upload.wikimedia.org", "thumb.wikimedia.org"}
        ):
            continue
        for pid in files[title]:
            result[pid] = {
                "wikidata_qid": enrichment[pid].get("wikidata_qid"),
                "photo_url": url,
                "photo_credit": author,
                "photo_license": licence,
            }
    return result


def build_profiles(enrich: bool = False) -> pd.DataFrame:
    """Publish all SB identities plus every unbridged TM player, with provenance."""
    root = get_settings().data_dir
    output = root / "processed/players"
    mapping = pd.read_parquet(output / "player_map.parquet")
    players = table("players").set_index("player_id")
    cache = output / "wikidata.json"
    enrichment = (
        {int(k): v for k, v in json.loads(cache.read_text()).items()}
        if cache.exists()
        else {}
    )
    descriptions = read_descriptions(root / "raw/players/bulk/entities")
    bridges_path = root / "raw/players/bulk/tm_index.json"
    bridges = json.loads(bridges_path.read_text()) if bridges_path.exists() else {}
    for tm_id, qid in bridges.items():
        # Exact P2446 is usable even when a biography batch has not finished.
        if int(tm_id) in players.index:
            enrichment[int(tm_id)] = descriptions.get(qid, {"wikidata_qid": qid})
    for tm_id in list(enrichment):
        tm_dob = (
            players.loc[tm_id].get("date_of_birth") if tm_id in players.index else None
        )
        wd_dob = enrichment[tm_id].get("dob")
        if pd.notna(tm_dob) and wd_dob and str(tm_dob)[:4] != wd_dob[:4]:
            enrichment.pop(tm_id)
    photo_cache = output / "photos.json"
    photo_data = (
        {int(k): v for k, v in json.loads(photo_cache.read_text()).items()}
        if photo_cache.exists()
        else {}
    )
    # Photos are keyed by stable profile ID, so WD-only players use their SB ID.
    source_records = mapping.to_dict("records")
    used_tm = set(mapping.tm_player_id.dropna().astype(int))
    source_records += [
        {
            "sb_player_id": -int(tm_id),
            "tm_player_id": int(tm_id),
            "sb_name": row["name"],
            "confidence": 1.0,
            "wikidata_qid": None,
        }
        for tm_id, row in players.iterrows()
        if tm_id not in used_tm
    ]
    wd_profiles = {}
    for row in source_records:
        pid, tm_id = int(row["sb_player_id"]), row["tm_player_id"]
        wd = (
            enrichment.get(int(tm_id), {})
            if pd.notna(tm_id)
            else descriptions.get(row.get("wikidata_qid"), {})
        )
        if wd:
            wd_profiles[pid] = wd
    if enrich:
        photo_data.update(photos(wd_profiles))
        atomic_json(photo_cache, photo_data)
    old_path = output / "profiles.parquet"
    old = (
        pd.read_parquet(old_path).set_index("sb_player_id").to_dict("index")
        if old_path.exists()
        else {}
    )
    lineup = {}
    for match in json.loads((root / "catalogue/matches.json").read_text()):
        if match["training"]:
            for team in json.loads(
                (
                    root / f"raw/statsbomb/data/lineups/{match['native_id']}.json"
                ).read_text()
            ):
                for player in team["lineup"]:
                    lineup[player["player_id"]] = player
    rows = []
    for row in source_records:
        pid = int(row["sb_player_id"])
        tm_id = int(row["tm_player_id"]) if pd.notna(row["tm_player_id"]) else None
        tm = players.loc[tm_id].to_dict() if tm_id is not None else {}
        tm = {key: None if pd.isna(v) else v for key, v in tm.items()}
        wd = wd_profiles.get(pid, {})
        sb = lineup.get(pid, {})
        dob = tm.get("date_of_birth") or wd.get("dob")
        dob = str(dob)[:10] if dob else None
        positions = sb.get("positions", [])
        nickname = sb.get("player_nickname")
        name = row["sb_name"]
        sources = (
            (["statsbomb"] if pid > 0 else [])
            + (["transfermarkt"] if tm_id is not None else [])
            + (["wikidata"] if wd.get("wikidata_qid") else [])
        )
        cached_photo = photo_data.get(pid, {})
        if cached_photo.get("wikidata_qid") != wd.get("wikidata_qid"):
            cached_photo = {}
        inherited = (
            old.get(pid, {})
            if old.get(pid, {}).get("wikidata_qid") == wd.get("wikidata_qid")
            else {}
        )
        photo = {
            k: cached_photo.get(k) or inherited.get(k)
            for k in ("photo_url", "photo_credit", "photo_license")
        }
        # Remove inherited credits when the QID was rejected or licence is not free.
        if not wd.get("wikidata_qid") or not free_license(
            photo.get("photo_license") or ""
        ):
            photo = {k: None for k in ("photo_url", "photo_credit", "photo_license")}
        wd_nationalities = [
            descriptions[q]["label"]
            for q in wd.get("countries", [])
            if q in descriptions and descriptions[q]["label"]
        ]
        rows.append(
            {
                "sb_player_id": pid,
                "in_dataset": pid > 0,
                "sources": sources,
                "aliases": wd.get("names", []),
                "name": name,
                "short_name": nickname or tm.get("name") or wd.get("label") or name,
                "nickname": nickname,
                "date_of_birth": dob,
                "height_cm": tm.get("height_in_cm") or wd.get("height_cm"),
                "foot": tm.get("foot"),
                "position": tm.get("sub_position")
                or (positions[0]["position"] if positions else None),
                "nationality": tm.get("country_of_citizenship")
                or (sb.get("country") or {}).get("name")
                or (", ".join(wd_nationalities) or None),
                "tm_player_id": tm_id,
                "wikidata_qid": wd.get("wikidata_qid"),
                "caps": tm.get("international_caps"),
                "current_club": tm.get("current_club_name"),
                "market_value_eur": tm.get("market_value_in_eur"),
                "peak_market_value_eur": tm.get("highest_market_value_in_eur"),
                "match_confidence": row["confidence"],
                **photo,
            }
        )
    frame = pd.DataFrame(rows)
    for col in (
        "tm_player_id",
        "caps",
        "height_cm",
        "market_value_eur",
        "peak_market_value_eur",
    ):
        frame[col] = pd.to_numeric(frame[col], errors="coerce").astype("Int64")
    assert frame.sb_player_id.is_unique
    assert (
        frame.loc[~frame.in_dataset, "sb_player_id"]
        .eq(-frame.loc[~frame.in_dataset, "tm_player_id"])
        .all()
    )
    assert set(frame.tm_player_id.dropna().astype(int)) == set(players.index)
    save_frame(frame, output / "profiles.parquet")
    atomic_json(cache, enrichment)
    qids = frame[frame.in_dataset].set_index("sb_player_id").wikidata_qid
    mapping["wikidata_qid"] = mapping.sb_player_id.map(qids)
    save_frame(mapping, output / "player_map.parquet")
    valuations = table("player_valuations")
    valuations = valuations[valuations.player_id.isin(players.index)].rename(
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
        conn.execute(
            "DELETE FROM player_profiles WHERE NOT in_dataset "
            "AND NOT (sb_player_id = ANY(%s))",
            ([r["sb_player_id"] for r in profiles],),
        )
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
                    tuple(
                        r[c].tolist()
                        if hasattr(r[c], "tolist")
                        else r[c]
                        if isinstance(r[c], list)
                        else None
                        if pd.isna(r[c])
                        else r[c]
                        for c in columns
                    )
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
