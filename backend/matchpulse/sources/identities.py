"""Conservative source identity bridges, without editing shared player registries."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from matchpulse.config import get_settings
from matchpulse.players.matching import normalise
from matchpulse.sources.common import canonical_team, decode_name, save_json


def select_player(
    name: str, team_candidates: set[int], aliases: dict[str, set[int]]
) -> int | None:
    """Match an exact known alias within observed team membership; reject ambiguity."""
    candidates = aliases.get(normalise(name), set()) & team_candidates
    return next(iter(candidates)) if len(candidates) == 1 else None


def build(data_dir: Path) -> dict:
    """Reuse existing player aliases/team normalizer, recording unmatched identities.

    Source-local numeric identities remain primary in staging/SPADL. These reviewed
    evidence bridges are for W14/API integration; no fuzzy name-only merge is done.
    Team membership is historical StatsBomb evidence, not a present-day club guess.
    """
    catalogue = json.loads((data_dir / "catalogue/matches.json").read_text())
    teams, membership = defaultdict(set), defaultdict(set)
    for match in catalogue:
        for side in ("home", "away"):
            teams[(match["gender"], canonical_team(match[side]["name"]))].add(
                match[side]["id"]
            )
    for path in (data_dir / "raw/statsbomb/data/lineups").glob("*.json"):
        for team in json.loads(path.read_text()):
            membership[team["team_id"]].update(p["player_id"] for p in team["lineup"])
    aliases = defaultdict(set)
    profiles = data_dir / "processed/players/profiles.parquet"
    if profiles.exists():
        for row in pd.read_parquet(profiles).to_dict("records"):
            for name in [
                row.get("name"),
                row.get("short_name"),
                row.get("nickname"),
                *list(row.get("aliases", [])),
            ]:
                if isinstance(name, str) and name:
                    aliases[normalise(name)].add(int(row["sb_player_id"]))
    source_teams, source_players = {}, {}
    for path in sorted((data_dir / "sources").glob("catalogue_*.json")):
        for match in json.loads(path.read_text()):
            for side in ("home", "away"):
                team = match[side]
                key = (match["gender"], canonical_team(team["name"]))
                candidates = teams.get(key, set())
                chosen = next(iter(candidates)) if len(candidates) == 1 else None
                source_teams[team["id"]] = {
                    "source": match["source"],
                    "source_id": team["id"],
                    "name": team["name"],
                    "sb_team_id": chosen,
                    "method": "normalized_known_team_alias"
                    if chosen
                    else "unmatched_or_ambiguous",
                }
    for source, subdirectory in (
        ("af", "dynasty/normalized"),
        ("us", "understat/lite"),
        ("fm", "fotmob/lite"),
        ("wy", "wyscout/normalized"),
        ("ws", "whoscored/normalized"),
    ):
        for path in (data_dir / "sources" / subdirectory).glob("*.json"):
            document = json.loads(path.read_text())
            for side in ("home", "away"):
                team = document["meta"][side]
                bridge = source_teams.get(team["id"], {})
                team_members = membership.get(bridge.get("sb_team_id"), set())
                if source in ("af", "wy", "ws"):
                    lineup = next(
                        t["lineup"]
                        for t in document["meta"]["lineups"]
                        if t["team_id"] == team["id"]
                    )
                    players = [(p["player_id"], p["player_name"]) for p in lineup]
                else:
                    players = [
                        (p["player_id"], p["name"]) for p in document["lineups"][side]
                    ]
                for pid, name in players:
                    name = decode_name(name)
                    selected = select_player(name, team_members, aliases)
                    entry = source_players.setdefault(
                        pid,
                        {
                            "source": source,
                            "source_id": pid,
                            "name": name,
                            "sb_player_id": None,
                            "method": "unmatched_or_ambiguous",
                        },
                    )
                    if selected:
                        if entry["sb_player_id"] not in (None, selected):
                            entry.update(
                                sb_player_id=None, method="conflicting_team_evidence"
                            )
                        elif entry["method"] != "conflicting_team_evidence":
                            entry.update(
                                sb_player_id=selected,
                                method="exact_alias_and_observed_team",
                            )
    report = {
        "teams": list(source_teams.values()),
        "players": list(source_players.values()),
        "summary": {
            "teams": len(source_teams),
            "mapped_teams": sum(
                x["sb_team_id"] is not None for x in source_teams.values()
            ),
            "players": len(source_players),
            "mapped_players": sum(
                x["sb_player_id"] is not None for x in source_players.values()
            ),
            "methods": dict(Counter(x["method"] for x in source_players.values())),
        },
    }
    save_json(data_dir / "sources/identity_map.json", report)
    return report["summary"]


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(build(get_settings().data_dir), indent=2))


if __name__ == "__main__":
    main()
