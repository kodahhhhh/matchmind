"""Cached downloads from the two explicitly approved CC0 player sources."""

import hashlib
import json
import time
from pathlib import Path

import httpx
import pandas as pd

from matchmind.config import get_settings

USER_AGENT = (
    "MatchMind/1.1 (StormHacks 2026; football identity research; cached CC0 enrichment)"
)
TM_ORIGIN = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data"


def table(name: str) -> pd.DataFrame:
    """Read an approved Transfermarkt dataset, downloading only if absent."""
    if name not in {
        "players",
        "player_valuations",
        "appearances",
        "games",
        "game_lineups",
        "clubs",
        "transfers",
    }:
        raise ValueError("Unapproved table")
    path = get_settings().data_dir / "raw/players/transfermarkt" / f"{name}.csv.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        temporary = path.with_suffix(".part")
        with httpx.stream(
            "GET",
            f"{TM_ORIGIN}/{name}.csv.gz",
            timeout=180,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            with temporary.open("wb") as output:
                for chunk in response.iter_bytes():
                    output.write(chunk)
        temporary.replace(path)
    return pd.read_csv(path, low_memory=False)


def cached_json(url: str, params: dict, namespace: str) -> dict:
    """Cache raw Wikimedia responses and keep requests at most one per second."""
    key = hashlib.sha256(json.dumps([url, params], sort_keys=True).encode()).hexdigest()
    directory = get_settings().data_dir / "raw/players/wikidata" / namespace
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    # Sequential callers only; delay also applies after failed requests.
    try:
        response = httpx.get(
            url,
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=60,
            follow_redirects=True,
        )
        response.raise_for_status()
        result = response.json()
        path.write_text(json.dumps(result))
        return result
    finally:
        time.sleep(1.05)


def wikidata(tm_ids: list[int]) -> dict[int, dict]:
    """Bridge exact P2446 identifiers, batching without guessing identities."""
    output = {}
    for offset in range(0, len(tm_ids), 100):
        values = " ".join(f'"{pid}"' for pid in tm_ids[offset : offset + 100])
        query = (
            "SELECT ?tm ?item ?dob ?height ?photo WHERE { VALUES ?tm { "
            + values
            + " } ?item wdt:P2446 ?tm . OPTIONAL { ?item wdt:P569 ?dob } "
            "OPTIONAL { ?item wdt:P2048 ?height } OPTIONAL { ?item wdt:P18 ?photo } }"
        )
        try:
            result = cached_json(
                "https://query.wikidata.org/sparql",
                {"query": query, "format": "json"},
                "sparql",
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            print(f"Wikidata batch {offset}: HTTP {status}", flush=True)
            if status in {429, 403, 503}:
                # Respect throttling: leave remaining enrichment absent and retry
                # in a later explicit build; never hammer or bypass the endpoint.
                break
            continue
        except (httpx.HTTPError, ValueError) as exc:
            print(f"Wikidata batch {offset}: {type(exc).__name__}", flush=True)
            continue
        for row in result["results"]["bindings"]:
            pid = int(row["tm"]["value"])
            item = output.setdefault(
                pid, {"wikidata_qid": row["item"]["value"].rsplit("/", 1)[-1]}
            )
            for field in ("dob", "height", "photo"):
                if field in row:
                    item.setdefault(field, row[field]["value"])
        print(f"Wikidata {min(offset + 100, len(tm_ids))}/{len(tm_ids)}", flush=True)
    return output


def save_frame(frame: pd.DataFrame, path: Path) -> None:
    """Publish a complete parquet atomically for dependent workstreams."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.parquet")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)
