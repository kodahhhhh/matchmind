"""Add conservative alias/history bridges without weakening the original map."""

import json
from collections import defaultdict

import pandas as pd

from matchmind.config import get_settings
from matchmind.players.bulk import (
    atomic_json,
    entities,
    football_names,
    raw_directory,
    read_descriptions,
    reference_labels,
)
from matchmind.players.matching import club, country, name_score, normalise
from matchmind.players.sources import save_frame, table


def observations() -> dict[int, dict]:
    """Collect verified roster names, citizenship and dated team appearances."""
    root = get_settings().data_dir
    records = {}
    for match in json.loads((root / "catalogue/matches.json").read_text()):
        if not match["training"]:
            continue
        for team in json.loads(
            (root / f"raw/statsbomb/data/lineups/{match['native_id']}.json").read_text()
        ):
            for p in team["lineup"]:
                row = records.setdefault(
                    p["player_id"],
                    {
                        "names": set(),
                        "countries": set(),
                        "appearances": set(),
                        "first_year": 9999,
                    },
                )
                row["names"].update(
                    n for n in (p["player_name"], p.get("player_nickname")) if n
                )
                row["countries"].add(country((p.get("country") or {}).get("name")))
                row["first_year"] = min(row["first_year"], int(match["season"][:4]))
                if match["match_date"]:
                    row["appearances"].add(
                        (match["match_date"], club(team["team_name"]))
                    )
    return records


def candidate_qids(
    names: dict[str, list[str]], observed: dict[int, dict], unmatched: set[int]
) -> set[str]:
    """Use complete names/tokens to bound entity downloads for legacy players."""
    by_token = defaultdict(set)
    for qid, aliases in names.items():
        for alias in aliases:
            for token in normalise(alias).split():
                by_token[token].add(qid)
    result = set()
    for pid in unmatched:
        sb = observed.get(pid, {})
        candidates = set()
        for alias in sb.get("names", []):
            tokens = normalise(alias).split()
            if tokens:
                # The least frequent token is adequate for exact/contained names.
                candidates.update(
                    by_token.get(
                        min(tokens, key=lambda t: len(by_token.get(t, []))), []
                    )
                )
        for qid in candidates:
            if (
                max((name_score(list(sb["names"]), n) for n in names[qid]), default=0)
                >= 0.96
            ):
                result.add(qid)
    return result


def qualifier_bound(values: list[dict], end: bool = False) -> str | None:
    """Expand year/month precision to its defensible interval boundary."""
    import calendar

    if not values:
        return None
    bounds = []
    for v in values:
        stamp = v.get("time", "")
        if not stamp.startswith("+"):
            continue
        parts = stamp[1:].split("T")[0].split("-")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            continue
        year = int(parts[0])
        if not 1 <= year <= 9999:
            continue
        precision = v.get("precision", 0)
        if precision < 9:
            continue
        month = int(parts[1]) if precision >= 10 else (12 if end else 1)
        if not 1 <= month <= 12:
            continue
        day = (
            int(parts[2])
            if precision >= 11
            else (calendar.monthrange(year, month)[1] if end else 1)
        )
        if not 1 <= day <= calendar.monthrange(year, month)[1]:
            continue
        bounds.append(f"{year:04}-{month:02}-{day:02}")
    return (max(bounds) if end else min(bounds)) if bounds else None


def club_overlap(sb: dict, wd: dict, labels: dict[str, dict]) -> bool:
    """Require a known team label and a qualified spell overlapping match day."""
    for spell in wd.get("clubs", []):
        start, end = (
            qualifier_bound(spell["start"]),
            qualifier_bound(spell["end"], True),
        )
        # Unqualified membership does not prove that a player was there then.
        if not start:
            continue
        names = {club(n) for n in labels.get(spell["qid"], {}).get("names", [])}
        for played, team in sb["appearances"]:
            if team in names and start <= played and (end is None or played <= end):
                return True
    return False


def history_index() -> dict[int, set[tuple[str, str]]]:
    """Read cached TM appearances by actual club/date, without provider traffic."""
    clubs = {
        int(r["club_id"]): club(r["name"]) for r in table("clubs").to_dict("records")
    }
    result = defaultdict(set)
    path = get_settings().data_dir / "raw/players/transfermarkt/appearances.csv.gz"
    for chunk in pd.read_csv(
        path, usecols=["player_id", "player_club_id", "date"], chunksize=250000
    ):
        for pid, cid, played in chunk.itertuples(index=False, name=None):
            if int(cid) in clubs:
                result[int(pid)].add((played, clubs[int(cid)]))
    return dict(result)


def select_bridge(
    sb: dict,
    candidates: list[dict],
    labels: dict[str, dict],
    history: dict[int, set[tuple[str, str]]],
) -> tuple[dict, float, str] | None:
    """Accept unique aliases with nationality/age or dated club corroboration."""
    scored = []
    for candidate in candidates:
        dob = candidate.get("dob")
        if dob and not 14 <= sb["first_year"] - int(dob[:4]) <= 55:
            continue
        score = max(
            (name_score(list(sb["names"]), alias) for alias in candidate["names"]),
            default=0,
        )
        if score < 0.90:
            continue
        nationals = {
            country(n)
            for q in candidate.get("countries", [])
            for n in labels.get(q, {}).get("names", [])
        }
        nationals.update(country(n) for n in candidate.get("tm_nationalities", []))
        nation = bool((sb["countries"] - {""}) & nationals)
        contextual = club_overlap(sb, candidate, labels) or bool(
            sb["appearances"] & history.get(candidate.get("tm_player_id"), set())
        )
        if contextual and score >= 0.90:
            confidence, method = min(0.985, score * 0.98), "alias_dated_club"
        elif nation and dob and score >= 0.96:
            # Single-word nicknames need dated club evidence, even if unique.
            multiword = any(
                len(normalise(a).split()) >= 2
                and name_score(list(sb["names"]), a) >= 0.96
                for a in candidate["names"]
            )
            if not multiword:
                continue
            confidence, method = score * 0.94, "alias_citizenship_age"
        else:
            continue
        if confidence >= 0.8:
            scored.append((candidate, confidence, method))
    scored.sort(key=lambda r: -r[1])
    if not scored or (len(scored) > 1 and scored[0][1] - scored[1][1] < 0.035):
        return None
    return scored[0]


def extend_map(fetch: bool = False) -> pd.DataFrame:
    """Only add new unambiguous bridges; write all considered candidate evidence."""
    root = get_settings().data_dir
    output = root / "processed/players"
    mapping = pd.read_parquet(output / "player_map.parquet")
    observed = observations()
    unmatched = set(mapping.loc[mapping.tm_player_id.isna(), "sb_player_id"])
    if fetch:
        qids = candidate_qids(football_names(), observed, unmatched)
        entities(list(qids))
    descriptions = read_descriptions()
    if fetch:
        reference_labels()
        descriptions = read_descriptions()
    players = table("players")
    bridges_path = raw_directory() / "tm_index.json"
    bridges = json.loads(bridges_path.read_text()) if bridges_path.exists() else {}
    candidates = {q: dict(r) for q, r in descriptions.items() if r["dob"]}
    for row in players.to_dict("records"):
        pid = int(row["player_id"])
        qid = bridges.get(str(pid))
        key = qid if qid in candidates else f"tm:{pid}"
        candidate = candidates.setdefault(
            key,
            {
                "names": [],
                "countries": [],
                "clubs": [],
                "dob": None,
                "wikidata_qid": None,
            },
        )
        candidate["names"] = sorted(set(candidate["names"] + [str(row["name"])]))
        candidate["tm_player_id"] = pid
        candidate["tm_name"] = row["name"]
        candidate["tm_nationalities"] = str(row["country_of_citizenship"]).split(",")
        tm_dob = (
            str(row["date_of_birth"])[:10] if pd.notna(row["date_of_birth"]) else None
        )
        if candidate["dob"] and tm_dob and candidate["dob"][:4] != tm_dob[:4]:
            # Contradictory bridge cannot contribute Wikidata aliases/metadata.
            candidate.update(
                {
                    "names": [row["name"]],
                    "countries": [],
                    "clubs": [],
                    "wikidata_qid": None,
                }
            )
        candidate["dob"] = tm_dob or candidate["dob"]
    by_token = defaultdict(set)
    for key, row in candidates.items():
        for alias in row["names"]:
            for token in normalise(alias).split():
                by_token[token].add(key)
    history = history_index()
    used_tm = set(mapping.tm_player_id.dropna().astype(int))
    used_wd = set(mapping.wikidata_qid.dropna())
    additions = []
    for _index, row in mapping.iterrows():
        pid = int(row.sb_player_id)
        if pid not in unmatched or pid not in observed:
            continue
        sb = observed[pid]
        possible = set()
        for alias in sb["names"]:
            for token in normalise(alias).split():
                possible.update(by_token.get(token, set()))
        found = select_bridge(
            sb, [candidates[k] for k in sorted(possible)], descriptions, history
        )
        if not found:
            continue
        target, confidence, method = found
        tm_id, qid = target.get("tm_player_id"), target.get("wikidata_qid")
        if tm_id in used_tm or qid in used_wd:
            continue
        additions.append(
            {
                "sb_player_id": pid,
                "sb_name": row.sb_name,
                "tm_player_id": tm_id,
                "wikidata_qid": qid,
                "confidence": confidence,
                "method": method,
                "names": target["names"],
                "dob": target["dob"],
                "countries": sorted(sb["countries"]),
                "source_countries": target.get("tm_nationalities", []),
                "observed": sorted(sb["appearances"]),
                "clubs": target["clubs"],
            }
        )
    # Reject collisions between *new* proposals rather than depending on row order.
    tm_counts = pd.Series([r["tm_player_id"] for r in additions]).value_counts()
    wd_counts = pd.Series([r["wikidata_qid"] for r in additions]).value_counts()
    accepted = []
    for r in additions:
        if (
            tm_counts.get(r["tm_player_id"], 0) > 1
            or wd_counts.get(r["wikidata_qid"], 0) > 1
        ):
            continue
        index = mapping.index[mapping.sb_player_id == r["sb_player_id"]][0]
        for field in ("tm_player_id", "wikidata_qid", "confidence", "method"):
            mapping.loc[index, field] = r[field]
        mapping.loc[index, "tm_name"] = candidates.get(
            r["wikidata_qid"], candidates.get(f"tm:{r['tm_player_id']}", {})
        ).get("tm_name")
        accepted.append(r)
    previous_path = output / "new_matches.json"
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else []
    cumulative = {r["sb_player_id"]: r for r in previous + accepted}
    atomic_json(previous_path, list(cumulative.values()))
    save_frame(mapping, output / "player_map.parquet")
    print(
        f"Added {len(accepted)} identities: "
        f"{mapping.tm_player_id.notna().sum()} TM, "
        f"{mapping.wikidata_qid.notna().sum()} QIDs",
        flush=True,
    )
    return mapping


if __name__ == "__main__":
    extend_map(fetch=True)
