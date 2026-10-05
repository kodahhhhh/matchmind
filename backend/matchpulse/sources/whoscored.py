"""Import owner-run WhoScored captures, retaining Opta qualifiers and clocks."""

import json
from pathlib import Path

import pandas as pd

from matchpulse.sources.common import numeric_id, save_json
from matchpulse.sources.full import normalize_actions
from matchpulse.sources.import_full import prefer_full, publish, staged_ids


def convert_capture(document: dict) -> tuple[dict, pd.DataFrame, list[dict]]:
    """Use socceraction's WhoScored parser/Opta converter without network IO."""
    from datetime import datetime

    from socceraction.data.opta.loader import _eventtypesdf
    from socceraction.data.opta.parsers import WhoScoredParser
    from socceraction.spadl import add_names
    from socceraction.spadl.opta import convert_to_actions

    data = document.get("matchCentreData", document)
    context = document.get("context", {})
    native = int(context.get("match_id", data.get("matchId", data.get("game_id", 0))))
    if not native:
        raise ValueError("Capture needs a native match ID")
    cid = int(context.get("competition_id", data.get("competition_id", 0)))
    sid = int(context.get("season_id", data.get("season_id", 0)))
    if not cid or not sid:
        raise ValueError("Capture needs competition/season discovery context")
    periods = {e.get("period", {}).get("value") for e in data.get("events", [])}
    if not {1, 2}.issubset(periods):
        raise ValueError("Incomplete two-half event stream")
    if not any(
        e.get("type", {}).get("value") == 30
        and e.get("period", {}).get("value") in (2, 4)
        for e in data["events"]
    ):
        raise ValueError(
            "No observed final period-end event; unfinished/incomplete capture"
        )
    parser = WhoScoredParser.__new__(WhoScoredParser)
    parser.root = {
        **data,
        "startTime": data["startTime"].removesuffix("Z").split("+")[0],
    }
    parser.competition_id = cid
    parser.season_id = sid
    parser.game_id = native
    original = {int(e.get("id", e.get("eventId"))): e for e in data["events"]}
    frame = pd.DataFrame(parser.extract_events().values()).merge(
        _eventtypesdf, on="type_id", how="left"
    )
    # Parser uses expandedMinute (elapsed). SPADL needs the displayed clock;
    # retain both native representations in raw provenance.
    frame["minute"] = frame.event_id.map(lambda eid: int(original[eid]["minute"]))
    frame = frame[frame.period_id.between(1, 4)].sort_values(
        ["period_id", "minute", "second", "event_id"], kind="stable"
    )
    native_home = int(data["home"]["teamId"])
    actions = add_names(convert_to_actions(frame, native_home))
    actions["home_team_id"] = native_home
    date = datetime.fromisoformat(data["startTime"].replace("Z", "+00:00"))
    match = {
        "match_id": f"ws:{native}",
        "source": "ws",
        "native_id": native,
        "competition_id": numeric_id("ws", cid),
        "competition": context.get("competition", "WhoScored"),
        "season_id": numeric_id("ws", sid),
        "season": context.get("season", str(date.year)),
        "country": context.get("country", "International"),
        "gender": "male",
        "match_date": date.date().isoformat(),
        "kick_off": date.time().replace(tzinfo=None).isoformat(),
        "stage": context.get("stage"),
        "matchweek": None,
        "has_360": False,
        "reconstructed": False,
        "demo": False,
        "training": True,
        "data_tier": "full",
        "source_home_id": native_home,
        "sequence_method": "inferred_control_runs",
        "licence": "Owner accepts source terms responsibility",
        "capabilities": {
            "full_events": True,
            "vaep": True,
            "xt": True,
            "pass_options": False,
            "game_state": False,
        },
        "player_names": {},
        "lineups": [],
    }
    for side in ("home", "away"):
        team = data[side]
        match[side] = {"id": numeric_id("ws", team["teamId"]), "name": team["name"]}
        match[f"{side}_score"] = int(team["scores"]["running"])
        players = []
        for p in team.get("players", []):
            pid = int(p["playerId"])
            name = p["name"]
            match["player_names"][str(pid)] = name
            players.append(
                {
                    "player_id": numeric_id("ws", pid),
                    "player_name": name,
                    "source_player_id": pid,
                    "jersey_number": int(p.get("shirtNo") or p.get("shirtNumber") or 0),
                    "positions": [
                        {"position": p.get("position"), "start_reason": "Starting XI"}
                    ]
                    if p.get("isFirstEleven")
                    else [],
                }
            )
        match["lineups"].append(
            {"team_id": match[side]["id"], "team_name": team["name"], "lineup": players}
        )
    actions, events = normalize_actions(match, actions, original)
    match["source_metadata"] = {
        "venue": data.get("venueName"),
        "referee": data.get("referee"),
        "context": context,
    }
    return match, actions, events


def import_incoming(
    data_dir: Path,
    inference: object,
    database_url: str | None,
    limit: int | None = None,
) -> dict:
    """Pick up rsynced complete captures; never fetch from the server's blocked IP."""
    root = data_dir / "raw/whoscored"
    paths = sorted(set(root.glob("incoming/*.json")) | set(root.glob("match_*.json")))
    target = data_dir / "sources/catalogue_whoscored.json"
    catalogue = json.loads(target.read_text()) if target.exists() else []
    existing = {m["match_id"]: m for m in catalogue}
    imported, skipped, duplicates, quarantined = 0, 0, [], []
    loaded = staged_ids(database_url, "ws")
    for path in paths:
        try:
            document = json.loads(path.read_text())
            data = document.get("matchCentreData", document)
            native = document.get("context", {}).get(
                "match_id", data.get("matchId", data.get("game_id"))
            )
            if native and f"ws:{native}" in existing:
                if database_url and f"ws:{native}" not in loaded:
                    from matchpulse.db.load_sources import load_full

                    folder = data_dir / "sources/whoscored"
                    load_full(
                        database_url,
                        folder / f"normalized/{native}.json",
                        folder / f"scored/{native}.parquet",
                    )
                skipped += 1
                continue
            match, actions, events = convert_capture(document)
            accepted, rejected = prefer_full(data_dir, [match])
            duplicates.extend(rejected)
            if not accepted:
                continue
            publish(data_dir, match, actions, events, inference, database_url)
            existing[match["match_id"]] = {
                k: v for k, v in match.items() if k not in ("lineups", "player_names")
            }
            save_json(target, sorted(existing.values(), key=lambda m: m["match_id"]))
            imported += 1
            if limit and imported >= limit:
                break
        except (ValueError, KeyError) as exc:
            quarantined.append({"path": str(path), "error": str(exc)})
    return {
        "imported": imported,
        "skipped": skipped,
        "total": len(existing),
        "duplicates": duplicates,
        "quarantined": quarantined,
        "needs_owner": not bool(paths),
    }
