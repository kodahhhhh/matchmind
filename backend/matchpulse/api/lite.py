"""Present available shot-tier data without invoking full-event analytics."""

from collections import defaultdict

from matchpulse.teams import match_colors, short_name, team_short


def compute_lite(payload: dict) -> dict:
    """Build existing response collections; unavailable measurements stay null."""
    meta = payload["meta"]
    colors = match_colors(meta["home"]["name"], meta["away"]["name"])
    teams = {
        side: {**meta[side], "short": team_short(meta[side]["name"]), "color": color}
        for side, color in zip(("home", "away"), colors, strict=True)
    }
    lineups = {
        side: [
            {
                "player_id": p["player_id"],
                "name": p["name"],
                "short_name": short_name(None, p["name"]),
                "jersey": p.get("jersey"),
                "position": (
                    {0: "Goalkeeper", 1: "Defender", 2: "Midfielder", 3: "Forward"}.get(
                        p.get("source_extra", {}).get("usualPlayingPositionId"),
                        p.get("position"),
                    )
                ),
                "starter": p["starter"],
            }
            for p in (payload.get("lineups") or {}).get(side, [])
        ]
        for side in teams
    }
    events, markers = [], []
    buckets = defaultdict(list)
    for shot in payload["shots"]:
        x, y = shot["x"], shot["y"]
        if shot["team"] == "away":
            x, y = 105 - x, 68 - y
        own_goal = shot["result"] == "OwnGoal"
        goal = shot["result"] == "Goal"
        event = {
            "id": shot["id"],
            "period": shot["period"],
            "minute": shot["minute"],
            "second": shot["second"],
            "t": None,
            "team": shot["team"],
            "player_id": shot["player_id"],
            "player": shot["player"],
            "type": {"Penalty": "shot_penalty", "DirectFreekick": "shot_freekick"}.get(
                shot["situation"], "shot"
            ),
            "result": "goal" if goal else "fail",
            "bodypart": "head"
            if shot["body_part"] in ("Head", "Header")
            else "foot"
            if shot["body_part"] in ("RightFoot", "LeftFoot")
            else None,
            "x": round(x, 2),
            "y": round(y, 2),
            "end_x": None,
            "end_y": None,
            "xg": shot["xg"],
            "sb_xg": None,
            "vaep": None,
            "sequence_id": None,
            "under_pressure": None,
            "time_precision": shot["time_precision"],
        }
        events.append(event)
        buckets[(shot["period"], shot["minute"])].append(shot)
        if goal or own_goal:
            markers.append(
                {
                    "type": "goal",
                    "event_id": shot["id"],
                    "period": shot["period"],
                    "minute": shot["minute"],
                    "second": shot["second"],
                    "t": None,
                    "team": ("away" if shot["team"] == "home" else "home")
                    if own_goal
                    else shot["team"],
                    "player_id": shot["player_id"],
                    "detail": "Own goal" if own_goal else None,
                }
            )
    cumulative, missing = {side: 0.0 for side in teams}, {side: False for side in teams}
    minutes = []
    # Only observed shot buckets. Empty minutes do not imply complete coverage.
    for (period, minute), shots in sorted(
        buckets.items(), key=lambda item: (item[0][0] or 0, item[0][1])
    ):
        row = {
            "index": len(minutes),
            "period": period,
            "minute": minute,
            "label": str(minute),
            "momentum": None,
        }
        for side in teams:
            observed = [
                s for s in shots if s["team"] == side and s["result"] != "OwnGoal"
            ]
            unavailable = any(s["xg"] is None for s in observed)
            total = sum(s["xg"] for s in observed if s["xg"] is not None)
            cumulative[side] += total
            missing[side] |= unavailable
            row[side] = {
                "possession": None,
                "field_tilt": None,
                "passes": None,
                "vaep": None,
                "shots": len(observed),
                "xg": None if unavailable else total,
                "xg_cum": None if missing[side] else cumulative[side],
            }
        minutes.append(row)
    detail = {
        **{
            k: meta.get(k)
            for k in (
                "match_id",
                "competition",
                "season",
                "stage",
                "match_date",
                "kick_off",
                "reconstructed",
            )
        },
        "venue": None,
        "referee": None,
        "teams": teams,
        "score": {"home": meta["home_score"], "away": meta["away_score"]},
        "periods": [],
        "duration_t": None,
        "lineups": lineups,
        "markers": markers,
        "data_tier": "lite",
        "source": meta["source"],
        "capabilities": payload["capabilities"],
        "clock_precision": "minute",
        "xg_provenance": payload.get("xg_provenance"),
        "provider_team_stats": payload.get("provider_team_stats")
        or payload.get("team_stats"),
        "provider_momentum": payload.get("provider_momentum"),
        "provider_player_ratings": payload.get("player_ratings"),
    }
    return {
        "match": detail,
        "events": events,
        "minutes": minutes,
        "sequences": [],
        "players": [],
        "turning_points": [],
    }
