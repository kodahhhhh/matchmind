"""Polite, resumable bulk Wikidata enrichment; raw evidence never enters Git."""

import argparse
import hashlib
import json
import time
from collections import defaultdict
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

from matchpulse.config import get_settings
from matchpulse.players.sources import USER_AGENT, table

PREFIXES = """
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
"""
WD_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
_last_request = 0.0


def raw_directory() -> Path:
    """Return the shared, ignored provider cache."""
    return get_settings().data_dir / "raw/players/bulk"


def atomic_json(path: Path, value: object) -> None:
    """Publish valid JSON only after the complete response has been received."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".part")
    temporary.write_text(json.dumps(value, ensure_ascii=False))
    temporary.replace(path)


def retry_delay(value: str | None, attempt: int) -> float:
    """Honor both forms of Retry-After, with bounded exponential fallback."""
    if value:
        try:
            return max(0, float(value))
        except ValueError:
            try:
                return max(0, parsedate_to_datetime(value).timestamp() - time.time())
            except (ValueError, TypeError):
                pass
    return min(60, 5 * 2**attempt)


def request_json(url: str, params: dict, namespace: str) -> dict:
    """Cache sequential requests, <=2/second, retrying 429/lag/temporary errors."""
    global _last_request
    key = hashlib.sha256(json.dumps([url, params], sort_keys=True).encode()).hexdigest()
    directory = raw_directory()
    path = directory / namespace / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    directory.mkdir(parents=True, exist_ok=True)
    for attempt in range(5):
        time.sleep(max(0, 0.55 - (time.monotonic() - _last_request)))
        _last_request = time.monotonic()
        started = time.monotonic()
        response = httpx.get(
            url,
            params=params,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/sparql-results+json, application/json",
            },
            timeout=180,
            follow_redirects=True,
        )
        result = response.json() if response.is_success else {}
        error = result.get("error", {}).get("code")
        with (directory / "requests.jsonl").open("a") as log:
            log.write(
                json.dumps(
                    {
                        "at": datetime.now(UTC).isoformat(),
                        "source": namespace,
                        "status": response.status_code,
                        "error": error,
                        "attempt": attempt + 1,
                        "seconds": round(time.monotonic() - started, 3),
                        "cache_key": key,
                    }
                )
                + "\n"
            )
        if response.status_code in {429, 502, 503, 504} or error in {
            "maxlag",
            "ratelimited",
        }:
            if attempt < 4:
                delay = retry_delay(response.headers.get("Retry-After"), attempt)
                print(
                    f"{namespace}: {response.status_code}/{error}, "
                    f"retry in {delay:.1f}s",
                    flush=True,
                )
                time.sleep(delay)
                continue
        response.raise_for_status()
        if error:
            raise ValueError(f"{namespace}: API error {error}")
        atomic_json(path, result)
        return result
    raise RuntimeError("Retry limit reached")


def sparql(query: str, namespace: str) -> list[dict]:
    """Try the official endpoint, then the explicitly approved QLever mirror."""
    for url in (
        "https://query.wikidata.org/sparql",
        "https://qlever.cs.uni-freiburg.de/api/wikidata",
    ):
        try:
            params = {"query": PREFIXES + query}
            if "query.wikidata.org" in url:
                params["format"] = "json"
            return request_json(url, params, namespace)["results"]["bindings"]
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            print(f"{namespace}: {url}: {type(exc).__name__}", flush=True)
    raise RuntimeError(f"Both bulk query providers failed for {namespace}")


def tm_index() -> dict[int, str]:
    """Fetch every P2446 bridge once; refuse duplicate/ambiguous identifiers."""
    rows = sparql("SELECT ?item ?tm WHERE { ?item wdt:P2446 ?tm }", "tm-index")
    candidates = defaultdict(set)
    for row in rows:
        if row["tm"]["value"].isdigit():
            candidates[int(row["tm"]["value"])].add(
                row["item"]["value"].rsplit("/", 1)[-1]
            )
    result = {
        pid: next(iter(qids)) for pid, qids in candidates.items() if len(qids) == 1
    }
    atomic_json(raw_directory() / "tm_index.json", result)
    print(f"Bulk P2446: {len(rows)} rows; {len(result)} unique bridges", flush=True)
    return result


def football_names() -> dict[str, list[str]]:
    """Bulk labels/aliases also find retired footballers absent from the TM CSV."""
    path = raw_directory() / "football_names.json"
    if path.exists():
        result = json.loads(path.read_text())
    else:
        rows = sparql(
            """SELECT ?item ?name WHERE {
      ?item wdt:P106 wd:Q937857 .
      ?item rdfs:label ?name .
      FILTER(LANG(?name) = "en")
    }""",
            "football-names",
        )
        result = defaultdict(list)
        for row in rows:
            qid = row["item"]["value"].rsplit("/", 1)[-1]
            result[qid].append(row["name"]["value"])
    alias_query = (
        PREFIXES + "SELECT ?item ?name WHERE { ?item wdt:P106 wd:Q937857 . "
        '?item skos:altLabel ?name . FILTER(LANG(?name) = "en") }'
    )
    aliases = request_json(
        "https://qlever.cs.uni-freiburg.de/api/wikidata",
        {"query": alias_query},
        "football-aliases",
    )["results"]["bindings"]
    for row in aliases:
        qid = row["item"]["value"].rsplit("/", 1)[-1]
        result.setdefault(qid, []).append(row["name"]["value"])
    result = {q: sorted(set(names)) for q, names in result.items()}
    atomic_json(path, result)
    print(f"Bulk football names: {len(result)} identities", flush=True)
    return dict(result)


def entities(qids: list[str]) -> dict[str, dict]:
    """Fetch batches of 50; a completed per-item cache makes resumes cheap."""
    directory = raw_directory() / "entities"
    directory.mkdir(parents=True, exist_ok=True)
    qids = list(dict.fromkeys(qids))
    missing = [q for q in qids if not (directory / f"{q}.json").exists()]
    for offset in range(0, len(missing), 50):
        batch = missing[offset : offset + 50]
        response = request_json(
            WD_API,
            {
                "action": "wbgetentities",
                "format": "json",
                "ids": "|".join(batch),
                "props": "claims|labels|aliases|sitelinks",
                "languages": "en|es|fr|de|pt|it",
                "sitefilter": "enwiki",
                "maxlag": "5",
            },
            "entities",
        )
        received = response.get("entities", {})
        for qid in batch:
            # Do not cache an omitted entity as successfully fetched.
            if qid in received:
                atomic_json(directory / f"{qid}.json", received[qid])
        if offset % 500 == 0 or offset + 50 >= len(missing):
            print(
                f"Entities {min(offset + 50, len(missing))}/{len(missing)} new",
                flush=True,
            )
    return {
        q: json.loads((directory / f"{q}.json").read_text())
        for q in qids
        if (directory / f"{q}.json").exists()
    }


def claim_values(entity: dict, prop: str) -> list[dict]:
    """Read non-deprecated claims, favoring preferred rank if it exists."""
    claims = [
        s
        for s in entity.get("claims", {}).get(prop, [])
        if s.get("rank") != "deprecated"
        and s.get("mainsnak", {}).get("snaktype") == "value"
    ]
    preferred = [s for s in claims if s.get("rank") == "preferred"]
    return preferred or claims


def value(statement: dict) -> object:
    """Read an already validated claim's typed data value."""
    return statement["mainsnak"]["datavalue"]["value"]


def describe(entity: dict) -> dict:
    """Keep source precision, units and all historical club qualifiers."""
    names = [v["value"] for v in entity.get("labels", {}).values()]
    names += [
        v["value"] for aliases in entity.get("aliases", {}).values() for v in aliases
    ]
    record = {"wikidata_qid": entity.get("id"), "names": sorted(set(names))}
    label = entity.get("labels", {}).get("en", {}).get("value")
    record["label"] = label or (names[0] if names else None)
    births = {
        exact_date(str(value(s)["time"]))
        for s in claim_values(entity, "P569")
        if value(s).get("precision", 0) >= 11 and str(value(s)["time"]).startswith("+")
    }
    births.discard(None)
    record["dob"] = next(iter(births)) if len(births) == 1 else None
    heights = set()
    for s in claim_values(entity, "P2048"):
        quantity = value(s)
        unit = quantity.get("unit", "").rsplit("/", 1)[-1]
        if unit in {"Q11573", "Q174728"}:
            cm = round(float(quantity["amount"]) * (100 if unit == "Q11573" else 1))
            if 120 <= cm <= 230:
                heights.add(cm)
    record["height_cm"] = next(iter(heights)) if len(heights) == 1 else None
    images = [value(s) for s in claim_values(entity, "P18")]
    record["photo"] = images[0] if images else None
    record["countries"] = sorted(
        {
            value(s)["id"]
            for prop in ("P27", "P1532")
            for s in claim_values(entity, prop)
        }
    )
    spells = []
    # Historical normal-rank spells still matter when a current club is preferred.
    for s in entity.get("claims", {}).get("P54", []):
        if (
            s.get("rank") == "deprecated"
            or s.get("mainsnak", {}).get("snaktype") != "value"
        ):
            continue
        qualifiers = s.get("qualifiers", {})
        spells.append(
            {
                "qid": value(s)["id"],
                **{
                    key: [
                        v["datavalue"]["value"]
                        for v in qualifiers.get(prop, [])
                        if v.get("snaktype") == "value"
                    ]
                    for key, prop in (("start", "P580"), ("end", "P582"))
                },
            }
        )
    record["clubs"] = spells
    record["tm_ids"] = [
        int(value(s)) for s in claim_values(entity, "P2446") if str(value(s)).isdigit()
    ]
    return record


def exact_date(stamp: str) -> str | None:
    """Normalize padded Wikidata years; reject invalid or imprecise dates."""
    if stamp.startswith("-"):
        return None
    try:
        year, month, day = (int(p) for p in stamp.lstrip("+").split("T")[0].split("-"))
        return date(year, month, day).isoformat()
    except (ValueError, OverflowError):
        return None


def read_descriptions(directory: Path | None = None) -> dict[str, dict]:
    """Read completed entities only, never issuing runtime provider calls."""
    directory = directory or raw_directory() / "entities"
    result = read_bulk_biographies(directory.parent)
    labels_path = directory.parent / "labels.json"
    if labels_path.exists():
        for qid, names in json.loads(labels_path.read_text()).items():
            result.setdefault(
                qid,
                {
                    "wikidata_qid": qid,
                    "names": names,
                    "label": names[0],
                    "dob": None,
                    "height_cm": None,
                    "photo": None,
                    "countries": [],
                    "clubs": [],
                    "tm_ids": [],
                },
            )
    result.update(
        {p.stem: describe(json.loads(p.read_text())) for p in directory.glob("Q*.json")}
    )
    return result


def biographies() -> None:
    """Bulk basic biographies spare tens of thousands of throttled API calls."""
    path = raw_directory() / "tm_bios.json"
    if path.exists():
        return
    query = (
        PREFIXES
        + """
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX psv: <http://www.wikidata.org/prop/statement/value/>
PREFIX wikibase: <http://wikiba.se/ontology#>
SELECT ?item ?tm ?dob ?height ?unit ?photo ?country WHERE {
 ?item wdt:P2446 ?tm .
 OPTIONAL {
  ?item p:P569 ?s . ?s a wikibase:BestRank; psv:P569 ?v .
  ?v wikibase:timeValue ?dob; wikibase:timePrecision ?precision .
  FILTER(?precision >= 11)
 }
 OPTIONAL {
  ?item p:P2048 ?hs . ?hs a wikibase:BestRank; psv:P2048 ?hv .
  ?hv wikibase:quantityAmount ?height; wikibase:quantityUnit ?unit
 }
 OPTIONAL { ?item wdt:P18 ?photo }
 OPTIONAL { ?item wdt:P27 ?country }
}"""
    )
    result = request_json(
        "https://qlever.cs.uni-freiburg.de/api/wikidata", {"query": query}, "tm-bios"
    )
    atomic_json(path, result)


def read_bulk_biographies(directory: Path) -> dict[str, dict]:
    """Parse precision-qualified bulk claims, with conflicts retained as null."""
    path = directory / "tm_bios.json"
    if not path.exists():
        return {}
    bridges = json.loads((directory / "tm_index.json").read_text())
    local_ids = table("players").player_id.astype(int)
    wanted = {bridges[str(pid)] for pid in local_ids if str(pid) in bridges}
    candidates_path = directory / "priority_candidates.json"
    if candidates_path.exists():
        wanted.update(json.loads(candidates_path.read_text()))
    names_path = directory / "football_names.json"
    names = json.loads(names_path.read_text()) if names_path.exists() else {}
    records = {}
    for binding in json.loads(path.read_text())["results"]["bindings"]:
        qid = binding["item"]["value"].rsplit("/", 1)[-1]
        if qid not in wanted:
            continue
        row = records.setdefault(
            qid,
            {
                "names": names.get(qid, []),
                "dob": set(),
                "height_cm": set(),
                "photo": set(),
                "countries": set(),
                "tm_ids": set(),
            },
        )
        if "dob" in binding:
            parsed = exact_date(binding["dob"]["value"])
            if parsed:
                row["dob"].add(parsed)
        if "height" in binding and "unit" in binding:
            unit = binding["unit"]["value"].rsplit("/", 1)[-1]
            if unit in {"Q11573", "Q174728"}:
                cm = round(
                    float(binding["height"]["value"]) * (100 if unit == "Q11573" else 1)
                )
                if 120 <= cm <= 230:
                    row["height_cm"].add(cm)
        if "photo" in binding:
            row["photo"].add(binding["photo"]["value"])
        if "country" in binding:
            row["countries"].add(binding["country"]["value"].rsplit("/", 1)[-1])
        if binding["tm"]["value"].isdigit():
            row["tm_ids"].add(int(binding["tm"]["value"]))
    result = {}
    for qid, row in records.items():
        result[qid] = {
            "wikidata_qid": qid,
            "names": row["names"],
            "label": row["names"][0] if row["names"] else None,
            "dob": next(iter(row["dob"])) if len(row["dob"]) == 1 else None,
            "height_cm": next(iter(row["height_cm"]))
            if len(row["height_cm"]) == 1
            else None,
            "photo": sorted(row["photo"])[0] if row["photo"] else None,
            "countries": sorted(row["countries"]),
            "tm_ids": sorted(row["tm_ids"]),
            "clubs": [],
        }
    return result


def reference_labels() -> None:
    """Cache club names plus small batches of any missing country/team labels."""
    path = raw_directory() / "labels.json"
    labels = json.loads(path.read_text()) if path.exists() else {}
    if not labels:
        query = (
            PREFIXES + "SELECT ?item ?name WHERE { ?item wdt:P31 wd:Q476028 . "
            '?item rdfs:label ?name . FILTER(LANG(?name) = "en") }'
        )
        rows = request_json(
            "https://qlever.cs.uni-freiburg.de/api/wikidata",
            {"query": query},
            "club-labels",
        )["results"]["bindings"]
        for row in rows:
            labels.setdefault(row["item"]["value"].rsplit("/", 1)[-1], []).append(
                row["name"]["value"]
            )
    records = read_descriptions()
    needed = {q for r in records.values() for q in r["countries"]} | {
        s["qid"] for r in records.values() for s in r["clubs"]
    }
    missing = sorted(needed - labels.keys())
    for offset in range(0, len(missing), 250):
        values = " ".join("wd:" + q for q in missing[offset : offset + 250])
        query = (
            PREFIXES
            + "SELECT ?item ?name WHERE { VALUES ?item { "
            + values
            + ' } ?item rdfs:label ?name . FILTER(LANG(?name) = "en") }'
        )
        rows = request_json(
            "https://qlever.cs.uni-freiburg.de/api/wikidata",
            {"query": query},
            "reference-labels",
        )["results"]["bindings"]
        for row in rows:
            labels.setdefault(row["item"]["value"].rsplit("/", 1)[-1], []).append(
                row["name"]["value"]
            )
        atomic_json(path, labels)
    atomic_json(path, labels)
    print(f"Reference labels {len(labels)}; new QIDs {len(missing)}", flush=True)


def enrich_all() -> None:
    """Bulk bios for every TM identity; detailed claims for SB/legacy candidates."""
    bridges = tm_index()
    import pandas as pd

    mapping = pd.read_parquet(
        get_settings().data_dir / "processed/players/player_map.parquet"
    )
    priority = mapping.tm_player_id.dropna().astype(int).tolist()
    from matchpulse.players.coverage_matching import candidate_qids, observations

    names = football_names()
    unmatched = set(mapping.loc[mapping.tm_player_id.isna(), "sb_player_id"])
    qids = candidate_qids(names, observations(), unmatched)
    atomic_json(raw_directory() / "priority_candidates.json", sorted(qids))
    biographies()
    entities([bridges[pid] for pid in priority if pid in bridges] + sorted(qids))
    reference_labels()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--names", action="store_true")
    args = parser.parse_args()
    if args.names:
        football_names()
    else:
        enrich_all()
