"""Conservative, reproducible StatsBomb to Transfermarkt identity matching."""

import json
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from functools import lru_cache

import pandas as pd

from matchmind.config import get_settings
from matchmind.players.sources import save_frame, table

COUNTRIES = {
    "united states of america": "united states",
    "usa": "united states",
    "korea republic": "south korea",
    "republic of ireland": "ireland",
    "cote d ivoire": "ivory coast",
    "congo dr": "dr congo",
    "bosnia herzegovina": "bosnia and herzegovina",
}
CLUBS = {
    "udinese calcio": "udinese",
    "societa sportiva lazio s p a": "lazio",
    "uc sampdoria": "sampdoria",
    "ajax amsterdam": "ajax",
    "afc ajax": "ajax",
    "olympique lyonnais": "lyon",
    "olympique lyon": "lyon",
    "real betis balompie": "real betis",
    "olympique de marseille": "marseille",
    "psg": "paris saint germain",
    "internazionale": "inter milan",
    "inter": "inter milan",
    "bayern munich": "bayern munchen",
    "koln": "cologne",
    "fc koln": "cologne",
    "1 fc koln": "cologne",
    "borussia m gladbach": "borussia monchengladbach",
    "mainz": "mainz",
    "rb leipzig": "rasenballsport leipzig",
    "deportivo la coruna": "deportivo la coruna",
    "alaves": "deportivo alaves",
    "atletico madrid": "atletico de madrid",
    "real sociedad": "real sociedad de futbol",
    "barcelona": "barcelona",
}


@lru_cache(maxsize=250000)
def normalise(value: object) -> str:
    """Accent/punctuation-insensitive name, retaining meaningful name tokens."""
    if value is None or pd.isna(value):
        return ""
    value = str(value).translate(
        str.maketrans(
            {
                "ø": "o",
                "Ø": "O",
                "ł": "l",
                "Ł": "L",
                "ß": "ss",
                "đ": "d",
                "Đ": "D",
                "ð": "d",
                "Ð": "D",
                "þ": "th",
                "Þ": "Th",
                "ı": "i",
                "æ": "ae",
                "Æ": "Ae",
                "œ": "oe",
                "Œ": "Oe",
            }
        )
    )
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def country(value: object) -> str:
    name = normalise(value)
    return COUNTRIES.get(name, name)


def club(value: object) -> str:
    name = normalise(value)
    name = re.sub(r"\b(fc|cf|ac|sc|sv|vfb|vfl|bsc|tsg|04|05|1899|1860|1)\b", "", name)
    name = " ".join(name.split())
    return CLUBS.get(name, name)


def name_score(names: list[str], candidate: str) -> float:
    """Exact aliases first; only complete-token containment for shortened names."""
    target = normalise(candidate)
    tokens = set(target.split())
    best = 0.0
    for name in names:
        alias = normalise(name)
        other = set(alias.split())
        if alias == target:
            best = max(best, 1.0)
        elif len(tokens) >= 2 and tokens <= other:
            best = max(best, 0.97)
        elif len(other) >= 2 and other <= tokens:
            best = max(best, 0.96)
        elif len(tokens) >= 2 and len(other) >= 2:
            # Initials are useful only together with an exact surname.
            if target.split()[-1] == alias.split()[-1]:
                if target.split()[0][0] == alias.split()[0][0] and (
                    len(target.split()[0]) == 1 or len(alias.split()[0]) == 1
                ):
                    best = max(best, 0.90)
            matcher = SequenceMatcher(None, alias, target)
            if (
                matcher.real_quick_ratio() >= 0.94
                and matcher.quick_ratio() >= 0.94
                and matcher.ratio() >= 0.94
            ):
                best = max(best, 0.92)
    return best


def choose(
    names: list[str],
    candidates: list[dict],
    nationality: str,
    shirt: int | None = None,
    contextual: bool = False,
    first_year: int | None = None,
) -> tuple[dict, float] | None:
    """Reject ambiguous best matches and country conflicts outside game context."""
    scores = {}
    for row in candidates:
        dob = row.get("date_of_birth")
        if first_year is not None and pd.notna(dob):
            birth_year = int(str(dob)[:4])
            if not 14 <= first_year - birth_year <= 55:
                continue
        nationalities = {
            country(v) for v in str(row.get("country_of_citizenship", "")).split(",")
        }
        if not contextual and nationality not in nationalities:
            continue
        score = name_score(names, row["name"])
        if score < (0.90 if contextual else 0.96):
            continue
        number = row.get("number")
        same_shirt = (
            shirt is not None
            and pd.notna(number)
            and str(number).isdigit()
            and int(number) == shirt
        )
        # A mismatched shirt does not exclude a real transfer/renumbering, but
        # never boosts its confidence. Names must still pass independently.
        confidence = min(
            0.995, score * (0.99 if contextual else 0.94) + (0.005 if same_shirt else 0)
        )
        pid = int(row["player_id"])
        if pid not in scores or scores[pid][1] < confidence:
            scores[pid] = (row, confidence)
    ranked = sorted(scores.values(), key=lambda pair: -pair[1])
    if not ranked or (len(ranked) > 1 and ranked[0][1] - ranked[1][1] < 0.035):
        return None
    return ranked[0]


def build_map() -> pd.DataFrame:
    """Match every observed corpus identity, explicitly retaining unmatched rows."""
    root = get_settings().data_dir
    output = root / "processed/players"
    catalogue = [
        m
        for m in json.loads((root / "catalogue/matches.json").read_text())
        if m["training"]
    ]
    players = table("players")
    games = table("games")
    player_rows = {int(r["player_id"]): r for r in players.to_dict("records")}
    # Games include international competitions as well as domestic leagues.
    game_keys = defaultdict(list)
    for row in games.to_dict("records"):
        if pd.notna(row["home_club_name"]) and pd.notna(row["away_club_name"]):
            game_keys[
                (row["date"], club(row["home_club_name"]), club(row["away_club_name"]))
            ].append(int(row["game_id"]))
    matched_games = {}
    for match in catalogue:
        key = (
            match["match_date"],
            club(match["home"]["name"]),
            club(match["away"]["name"]),
        )
        ids = game_keys.get(key, [])
        if len(ids) == 1:
            matched_games[match["native_id"]] = ids[0]
    print(
        f"Matched {len(matched_games)} dated games by date and both clubs", flush=True
    )
    ids = set(matched_games.values())
    lineups = defaultdict(list)
    path = root / "raw/players/transfermarkt/game_lineups.csv.gz"
    for chunk in pd.read_csv(path, chunksize=250000, low_memory=False):
        for row in chunk[chunk.game_id.isin(ids)].to_dict("records"):
            pid = int(row["player_id"])
            if pid in player_rows:
                lineups[int(row["game_id"])].append(
                    {**player_rows[pid], "number": row["number"]}
                )
    appearances = root / "raw/players/transfermarkt/appearances.csv.gz"
    for chunk in pd.read_csv(appearances, chunksize=250000, low_memory=False):
        for row in chunk[chunk.game_id.isin(ids)].to_dict("records"):
            pid = int(row["player_id"])
            if pid in player_rows:
                lineups[int(row["game_id"])].append(player_rows[pid])
    identity = {}
    evidence = defaultdict(list)
    for match in catalogue:
        rosters = json.loads(
            (root / f"raw/statsbomb/data/lineups/{match['native_id']}.json").read_text()
        )
        for team in rosters:
            for row in team["lineup"]:
                pid = int(row["player_id"])
                item = identity.setdefault(pid, {"names": set(), "countries": set()})
                item["names"].update(
                    n for n in [row["player_name"], row.get("player_nickname")] if n
                )
                item["countries"].add(country((row.get("country") or {}).get("name")))
                item["name"] = row["player_name"]
                year = int(match["season"][:4])
                item["first_year"] = min(item.get("first_year", year), year)
                game = matched_games.get(match["native_id"])
                if game and lineups[game]:
                    found = choose(
                        list(item["names"]),
                        lineups[game],
                        "",
                        row.get("jersey_number"),
                        True,
                        year,
                    )
                    if found:
                        evidence[pid].append(found)
    # Include every model-observed ID, not unused bench players.
    observed = set(
        pd.read_parquet(root / "processed/player_vaep_totals.parquet").player_id.astype(
            int
        )
    )
    by_token = defaultdict(set)
    for pid, row in player_rows.items():
        for token in normalise(row["name"]).split():
            by_token[token].add(pid)
    rows = []
    for pid in sorted(observed):
        item = identity.get(pid, {"names": set(), "countries": set(), "name": str(pid)})
        contextual = evidence.get(pid, [])
        target_ids = {int(r["player_id"]) for r, _ in contextual}
        found = None
        method = "unmatched"
        if len(target_ids) == 1:
            found = max(contextual, key=lambda pair: pair[1])
            method = "game_lineup_name_shirt"
        elif not target_ids:
            candidates = set()
            for alias in item["names"]:
                tokens = normalise(alias).split()
                # Rare tokens narrow candidates without assuming Western surnames.
                for token in tokens:
                    candidates.update(by_token.get(token, set()))
            possible = []
            for nationality in item["countries"]:
                match = choose(
                    list(item["names"]),
                    [player_rows[p] for p in candidates],
                    nationality,
                    first_year=item.get("first_year"),
                )
                if match:
                    possible.append(match)
            if len({int(r["player_id"]) for r, _ in possible}) == 1:
                found = max(possible, key=lambda pair: pair[1])
                method = "name_citizenship"
        row, confidence = found if found else ({}, 0.0)
        rows.append(
            {
                "sb_player_id": pid,
                "tm_player_id": row.get("player_id"),
                "wikidata_qid": None,
                "method": method,
                "confidence": confidence,
                "sb_name": item["name"],
                "tm_name": row.get("name"),
            }
        )
    frame = pd.DataFrame(rows)
    frame["tm_player_id"] = frame.tm_player_id.astype("Int64")
    # Reject two SB identities bridged to the same TM ID: require human review.
    duplicates = frame.tm_player_id.notna() & frame.tm_player_id.duplicated(keep=False)
    frame.loc[duplicates, ["tm_player_id", "tm_name"]] = None
    frame.loc[duplicates, "confidence"] = 0.0
    frame.loc[duplicates, "method"] = "ambiguous_duplicate"
    cached_wikidata = output / "wikidata.json"
    if cached_wikidata.exists():
        bridges = json.loads(cached_wikidata.read_text())
        frame["wikidata_qid"] = frame.tm_player_id.map(
            lambda pid: (
                bridges.get(str(int(pid)), {}).get("wikidata_qid")
                if pd.notna(pid)
                else None
            )
        )
    save_frame(frame, output / "player_map.parquet")
    (output / "_READY").touch()
    print(f"READY: {frame.tm_player_id.notna().sum()}/{len(frame)} mapped", flush=True)
    return frame


if __name__ == "__main__":
    build_map()
