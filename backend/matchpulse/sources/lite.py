"""Shot-level sources never masquerade as a complete event stream."""

from datetime import datetime

import numpy as np

from matchpulse.sources.common import numeric_id

LEAGUES = {
    "EPL": ("Premier League", "England"),
    "La_liga": ("La Liga", "Spain"),
    "Bundesliga": ("1. Bundesliga", "Germany"),
    "Serie_A": ("Serie A", "Italy"),
    "Ligue_1": ("Ligue 1", "France"),
}


def understat(
    fixture: dict, detail: dict, league: str, season: int
) -> tuple[dict, dict]:
    """Parse cached AJAX JSON, preserving unknown period/second as null.

    Official match.js draws home at X*width, (1-Y)*height on its top-left canvas:
    source Y is bottom-left, so SPADL y = Y*68 (no extra Y inversion).
    """
    if not fixture.get("isResult"):
        raise ValueError("Only finished Understat matches may be imported")
    date = datetime.fromisoformat(fixture["datetime"])
    competition, country = LEAGUES[league]
    match = {
        "match_id": f"us:{fixture['id']}",
        "source": "us",
        "native_id": int(fixture["id"]),
        "competition_id": numeric_id("us", league),
        "competition": competition,
        "season_id": numeric_id("us", season),
        "season": f"{season}/{season + 1}",
        "country": country,
        "gender": "male",
        "stage": "Regular Season",
        "matchweek": None,
        "match_date": date.date().isoformat(),
        "kick_off": date.time().isoformat(),
        "home": {
            "id": numeric_id("us", fixture["h"]["id"]),
            "name": fixture["h"]["title"],
        },
        "away": {
            "id": numeric_id("us", fixture["a"]["id"]),
            "name": fixture["a"]["title"],
        },
        "home_score": int(fixture["goals"]["h"]),
        "away_score": int(fixture["goals"]["a"]),
        "has_360": False,
        "reconstructed": False,
        "demo": False,
        "training": False,
        "data_tier": "lite",
        "licence": "No open data licence found; publication rights unresolved",
    }
    lineups, shots = {"home": [], "away": []}, []
    for key, side in (("h", "home"), ("a", "away")):
        roster = detail.get("rosters", {}).get(key, {})
        for player in roster.values():
            lineups[side].append(
                {
                    "player_id": numeric_id("us", player["player_id"]),
                    "source_player_id": player["player_id"],
                    "name": player["player"],
                    "position": player["position"],
                    "starter": player["position"] != "Sub",
                    "minutes": int(player["time"]),
                    "jersey": None,
                    "rating": None,
                    "source_extra": player,
                }
            )
        for index, shot in enumerate(detail.get("shots", {}).get(key, [])):
            if str(shot["match_id"]) != str(fixture["id"]):
                raise ValueError("Shot belongs to a different match")
            x, y = float(shot["X"]) * 105, float(shot["Y"]) * 68
            if not np.isfinite([x, y]).all() or not (0 <= x <= 105 and 0 <= y <= 68):
                raise ValueError("Shot outside normalized pitch")
            shots.append(
                {
                    "id": f"{match['match_id']}:{key}{index}",
                    "source_event_id": str(shot["id"]),
                    "team": side,
                    "player_id": numeric_id("us", shot["player_id"]),
                    "player": shot["player"],
                    "minute": int(shot["minute"]),
                    "second": None,
                    "period": None,
                    "time_precision": "minute",
                    "x": x,
                    "y": y,
                    "result": shot["result"],
                    "body_part": shot["shotType"],
                    "situation": shot["situation"],
                    "xg": None,
                    "provider_xg": float(shot["xG"]),
                    "source_extra": shot,
                }
            )
    shots.sort(key=lambda e: (e["minute"], e["source_event_id"]))
    for index, shot in enumerate(shots):
        shot["id"] = f"{match['match_id']}:{index}"
    bundle = {
        "match_id": match["match_id"],
        "data_tier": "lite",
        "lineups": lineups,
        "shots": shots,
        "team_stats": None,
        "provider_momentum": None,
        "player_ratings": None,
        "source_fixture": fixture,
        "capabilities": {
            "full_events": False,
            "shots": bool(shots),
            "lineups": any(lineups.values()),
            "vaep": False,
            "xt": False,
            "pass_options": False,
            "game_state": False,
        },
    }
    return match, bundle


def enrich_understat(bundle: dict, fixture: dict, discovery: dict) -> dict:
    """Retain provider aggregates using exact team/date evidence, never as ours."""
    stats = {}
    for key, side in (("h", "home"), ("a", "away")):
        team = discovery.get("teams", {}).get(str(fixture[key]["id"]), {})
        rows = [
            row
            for row in team.get("history", [])
            if row.get("date") == fixture["datetime"] and row.get("h_a") == key
        ]
        stats[side] = rows[0] if len(rows) == 1 else None
    bundle["provider_team_stats"] = stats
    bundle["capabilities"]["provider_team_stats"] = any(stats.values())
    return bundle


def fotmob(detail: dict) -> tuple[dict, dict]:
    """Inspect a cached match detail; network refresh is excluded by source terms."""
    general, content = detail["general"], detail["content"]
    if not general.get("finished"):
        raise ValueError("Only finished FotMob matches may be imported")
    date = datetime.fromisoformat(general["matchTimeUTCDate"].replace("Z", "+00:00"))
    header = detail["header"]["teams"]
    season = date.year if date.month >= 7 else date.year - 1
    match = {
        "match_id": f"fm:{general['matchId']}",
        "native_id": int(general["matchId"]),
        "source": "fm",
        "competition_id": numeric_id("fm", general["leagueId"]),
        "competition": general["leagueName"],
        "season_id": numeric_id("fm", season),
        "season": f"{season}/{season + 1}",
        "country": general.get("countryCode", ""),
        "gender": general.get("gender", "male"),
        "stage": "Regular Season",
        "matchweek": general.get("matchRound"),
        "match_date": date.date().isoformat(),
        "kick_off": date.time().isoformat(),
        **{
            s: {
                "id": numeric_id("fm", general[f"{s}Team"]["id"]),
                "name": general[f"{s}Team"]["name"],
            }
            for s in ("home", "away")
        },
        "home_score": header[0]["score"],
        "away_score": header[1]["score"],
        "has_360": False,
        "reconstructed": False,
        "demo": False,
        "training": False,
        "data_tier": "lite",
        "licence": "Proprietary; systematic/regular automated use prohibited",
    }
    shots = []
    for index, shot in enumerate((content.get("shotmap") or {}).get("shots", [])):
        side = "home" if shot["teamId"] == general["homeTeam"]["id"] else "away"
        minute = int(shot["min"]) + int(shot.get("minAdded") or 0)
        x, y = float(shot["x"]), float(shot["y"])
        if not (0 <= x <= 105 and 0 <= y <= 68):
            raise ValueError("FotMob shot outside metre pitch")
        shots.append(
            {
                "id": f"{match['match_id']}:{index}",
                "source_event_id": str(shot["id"]),
                "team": side,
                "player_id": numeric_id("fm", shot["playerId"]),
                "player": shot["playerName"],
                "period": {
                    "FirstHalf": 1,
                    "SecondHalf": 2,
                    "FirstPeriodOfExtraTime": 3,
                    "SecondPeriodOfExtraTime": 4,
                }.get(shot.get("period")),
                "minute": minute,
                "second": None,
                "time_precision": "minute",
                "x": x,
                "y": y,
                "xg": None,
                "provider_xg": shot.get("expectedGoals"),
                "result": shot["eventType"],
                "body_part": shot.get("shotType"),
                "situation": shot.get("situation"),
                "source_extra": shot,
            }
        )
    return match, {
        "match_id": match["match_id"],
        "data_tier": "lite",
        "shots": shots,
        "lineups": content.get("lineup"),
        "player_ratings": content.get("playerStats"),
        "team_stats": content.get("stats"),
        "provider_momentum": content.get("momentum"),
        "match_facts": content.get("matchFacts"),
        "coordinate_status": (
            "metres verified; lateral origin pending provider documentation"
        ),
        "capabilities": {
            "full_events": False,
            "vaep": False,
            "xt": False,
            "game_state": False,
            "pass_options": False,
        },
    }


def score_shots(match: dict, bundle: dict, inference: object) -> dict:
    """Apply our xG to Understat shots without constructing fake SPADL actions."""
    events = []
    for shot in bundle["shots"]:
        if shot["result"] == "OwnGoal":
            continue
        body = {
            "Head": "Head",
            "Header": "Head",
            "RightFoot": "Right Foot",
            "LeftFoot": "Left Foot",
        }.get(shot["body_part"], "Other")
        kind = {
            "Penalty": "Penalty",
            "DirectFreekick": "Free Kick",
            "FromCorner": "Corner",
            "OpenPlay": "Open Play",
        }.get(shot["situation"], "Other")
        events.append(
            {
                "id": shot["id"],
                "minute": shot["minute"],
                "period": 1,
                "team": match[shot["team"]],
                "location": [shot["x"] * 120 / 105, (68 - shot["y"]) * 80 / 68],
                "type": {"name": "Shot"},
                "shot": {
                    "body_part": {"name": body},
                    "type": {"name": kind},
                    "outcome": {
                        "name": "Goal" if shot["result"] == "Goal" else "Off T"
                    },
                },
            }
        )
    ratings = inference.shots(match, events)
    for shot in bundle["shots"]:
        shot["xg"] = ratings.get(shot["id"])
    bundle["xg_provenance"] = (
        "MatchPulse current model; missing context; cross-source transfer unvalidated"
    )
    bundle["capabilities"]["own_xg"] = bool(ratings)
    match["capabilities"] = dict(bundle["capabilities"])
    return bundle
