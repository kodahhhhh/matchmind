"""Offline adapter for locally cached Pappalardo Wyscout archives."""

from pathlib import Path

import pandas as pd


def convert_events(events: list[dict], home_team_id: int) -> pd.DataFrame:
    """Use the pinned socceraction converter on owner-provided Pappalardo files.

    Source X/Y percentages are acting-team attacking-relative. Socceraction makes
    home attack +x across periods; original native event IDs survive conversion.
    The package's loader normalization is reused without instantiating its loader
    (which can implicitly download when its directory is empty).
    """
    from socceraction.data.wyscout.loader import _convert_events
    from socceraction.spadl import add_names
    from socceraction.spadl.wyscout import convert_to_actions

    normalized = _convert_events(pd.DataFrame(events))
    actions = add_names(convert_to_actions(normalized, home_team_id))
    actions["home_team_id"] = home_team_id
    return actions


COMPETITIONS = {
    "England": ("Premier League", "England", "2017/2018"),
    "France": ("Ligue 1", "France", "2017/2018"),
    "Germany": ("1. Bundesliga", "Germany", "2017/2018"),
    "Italy": ("Serie A", "Italy", "2017/2018"),
    "Spain": ("La Liga", "Spain", "2017/2018"),
    "European_Championship": ("UEFA Euro", "International", "2016"),
    "World_Cup": ("FIFA World Cup", "International", "2018"),
}


def prepare_files(data_dir: Path) -> Path:
    """Extract only expected JSON filenames from completed local ZIPs, offline."""
    import shutil
    import stat
    import zipfile

    root = data_dir / "raw/wyscout"
    target = root / "dataset"
    target.mkdir(parents=True, exist_ok=True)
    allowed = {
        f"{kind}_{country}.json"
        for kind in ("matches", "events")
        for country in COMPETITIONS
    }
    for directory in (root / "incoming", root):
        for name in (
            "teams.json",
            "players.json",
            "competitions.json",
            *sorted(allowed),
        ):
            if (directory / name).exists() and not (target / name).exists():
                shutil.copyfile(directory / name, target / name)
        for archive in directory.glob("*.zip"):
            with zipfile.ZipFile(archive) as z:
                if sum(i.file_size for i in z.infolist()) > 2 * 1024**3:
                    raise ValueError("Extraction budget exceeded")
                for member in z.infolist():
                    if stat.S_ISLNK(member.external_attr >> 16):
                        raise ValueError("Archive symlink")
                    if (
                        member.filename in allowed
                        and not (target / member.filename).exists()
                    ):
                        tmp = target / (member.filename + ".part")
                        tmp.write_bytes(z.read(member))
                        tmp.replace(target / member.filename)
    return target


def catalogue_entry(raw: dict, country: str, teams: dict, players: dict) -> dict:
    """Real source dates/scores/rosters; source has no jersey-number coverage."""
    from datetime import datetime

    from matchpulse.sources.common import numeric_id

    if raw["status"] != "Played":
        raise ValueError("Only played matches")
    competition, nation, season = COMPETITIONS[country]
    date = datetime.fromisoformat(raw["dateutc"])
    sides = {t["side"]: t for t in raw["teamsData"].values()}
    match = {
        "match_id": f"wy:{raw['wyId']}",
        "source": "wy",
        "native_id": raw["wyId"],
        "competition_id": numeric_id("wy", raw["competitionId"]),
        "competition": competition,
        "season_id": numeric_id("wy", raw["seasonId"]),
        "season": season,
        "country": nation,
        "gender": "male",
        "stage": "Regular Season"
        if nation != "International"
        else str(raw.get("roundId")),
        "matchweek": raw.get("gameweek"),
        "match_date": date.date().isoformat(),
        "kick_off": date.time().isoformat(),
        "has_360": False,
        "reconstructed": False,
        "demo": False,
        "training": True,
        "data_tier": "full",
        "licence": "CC BY 4.0, Pappalardo et al. 2019",
        "source_home_id": sides["home"]["teamId"],
        "capabilities": {
            "full_events": True,
            "vaep": True,
            "xt": True,
            "game_state": False,
            "pass_options": False,
        },
        "sequence_method": "inferred_control_runs",
        "player_names": {},
        "lineups": [],
        "source_match": raw,
    }
    for side in ("home", "away"):
        team = sides[side]
        native = team["teamId"]
        match[side] = {"id": numeric_id("wy", native), "name": teams[native]["name"]}
        match[f"{side}_score"] = int(team["score"])
        roster = []
        for starter, group in ((True, "lineup"), (False, "bench")):
            for player in team.get("formation", {}).get(group, []):
                pid = player["playerId"]
                info = players.get(pid, {})
                name = (
                    " ".join(
                        str(info.get(k, "")) for k in ("firstName", "lastName")
                    ).strip()
                    or info.get("shortName")
                    or "Unknown"
                )
                match["player_names"][str(pid)] = name
                roster.append(
                    {
                        "player_id": numeric_id("wy", pid),
                        "player_name": name,
                        "jersey_number": 0,
                        "source_player_id": pid,
                        "jersey_known": False,
                        "positions": [
                            {
                                "position": info.get("role", {}).get("name"),
                                "start_reason": "Starting XI",
                            }
                        ]
                        if starter
                        else [],
                    }
                )
        match["lineups"].append(
            {
                "team_id": match[side]["id"],
                "team_name": match[side]["name"],
                "lineup": roster,
            }
        )
    return match


def import_dataset(
    data_dir: object,
    inference: object,
    database_url: str | None,
    limit: int | None = None,
) -> dict:
    """Incrementally convert each country from local files and current models."""
    import json
    from collections import defaultdict

    from matchpulse.sources.common import save_json
    from matchpulse.sources.full import normalize_actions
    from matchpulse.sources.import_full import prefer_full, publish

    root = prepare_files(data_dir)
    required = [root / f"{name}.json" for name in ("teams", "players")]
    if not all(p.exists() for p in required):
        return {
            "imported": 0,
            "needs_owner": "Supply files in raw/wyscout/incoming/",
        }
    teams = {t["wyId"]: t for t in json.loads(required[0].read_text())}
    players = {p["wyId"]: p for p in json.loads(required[1].read_text())}
    path = data_dir / "sources/catalogue_wyscout.json"
    catalogue = json.loads(path.read_text()) if path.exists() else []
    existing = {m["match_id"]: m for m in catalogue}
    imported, skipped, duplicates, quarantined = 0, 0, [], []
    for country in COMPETITIONS:
        matches_path, events_path = (
            root / f"matches_{country}.json",
            root / f"events_{country}.json",
        )
        if not matches_path.exists() or not events_path.exists():
            continue
        matches = json.loads(matches_path.read_text())
        entries = [
            catalogue_entry(m, country, teams, players)
            for m in matches
            if m.get("status") == "Played"
        ]
        accepted, rejected = prefer_full(data_dir, entries)
        duplicates.extend(rejected)
        accepted = {m["match_id"]: m for m in accepted}
        grouped = defaultdict(list)
        for event in json.loads(events_path.read_text()):
            grouped[event["matchId"]].append(event)
        for match in sorted(
            accepted.values(),
            key=lambda m: (m["match_date"], m["match_id"]),
            reverse=True,
        ):
            mid = match["match_id"]
            target = data_dir / f"sources/wyscout/scored/{match['native_id']}.parquet"
            if mid in existing and target.exists():
                skipped += 1
                continue
            try:
                raw = grouped[match["native_id"]]
                actions = convert_events(raw, match["source_home_id"])
                actions = actions[actions.period_id < 5].reset_index(drop=True)
                actions, events = normalize_actions(
                    match, actions, {e["id"]: e for e in raw}
                )
                publish(data_dir, match, actions, events, inference, database_url)
                existing[mid] = {
                    k: v
                    for k, v in match.items()
                    if k not in ("source_match", "lineups", "player_names")
                }
                save_json(path, sorted(existing.values(), key=lambda m: m["match_id"]))
                imported += 1
                if imported % 20 == 0:
                    print(
                        json.dumps(
                            {
                                "source": "wyscout",
                                "new": imported,
                                "total": len(existing),
                                "country": country,
                            }
                        ),
                        flush=True,
                    )
                if limit is not None and imported >= limit:
                    return {
                        "imported": imported,
                        "skipped": skipped,
                        "total": len(existing),
                        "duplicates": duplicates,
                        "quarantined": quarantined,
                    }
            except (ValueError, KeyError) as exc:
                quarantined.append({"match_id": mid, "error": str(exc)})
    return {
        "imported": imported,
        "skipped": skipped,
        "total": len(existing),
        "duplicates": duplicates,
        "quarantined": quarantined,
    }
