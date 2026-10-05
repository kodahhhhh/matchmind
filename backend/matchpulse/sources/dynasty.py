"""Afriskaut's Apache-2.0 Dynasty dataset: validate coverage before conversion."""

from collections import Counter
from datetime import datetime

from matchpulse.sources.common import NOMINAL, coordinates, identify_events, numeric_id


def seconds(value: str) -> int:
    """Parse video timestamps strictly; zero/invalid clock metadata is rejected."""
    h, m, s = value.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def coverage(meta: dict, events: list[dict]) -> list[str]:
    """Conservative eligibility gate for two-team, reviewed match streams."""
    issues = []
    for side in ("home", "away"):
        if not meta.get(f"{side}_team") or not meta.get(f"{side}_team_line_up"):
            issues.append(f"missing_{side}_identity_or_lineup")
        if not meta.get(f"is{side.title()}MatchReviewed"):
            issues.append(f"unreviewed_{side}")
        if meta.get(f"{side}_team_starting_direction") not in ("left", "right"):
            issues.append(f"missing_{side}_direction")
        passes = sum(
            e["event_name"] == "PASS" and e["team_id"] == meta.get(f"{side}_team")
            for e in events
        )
        if passes < 100:
            issues.append(f"sparse_{side}_stream")
    try:
        bounds = [
            seconds(meta[k])
            for k in (
                "match_start_time",
                "first_half_end_time",
                "second_half_start_time",
                "match_end_time",
            )
        ]
        if not (bounds[0] < bounds[1] < bounds[2] < bounds[3]):
            issues.append("invalid_clock_bounds")
        if min(bounds[1] - bounds[0], bounds[3] - bounds[2]) < 35 * 60:
            issues.append("incomplete_periods")
    except (ValueError, KeyError):
        issues.append("missing_clock_bounds")
    return issues


def catalogue_entry(meta: dict) -> dict:
    """Preserve real source dates; time is unverified wall clock in metadata."""
    value = meta["date"]
    date = (
        datetime.strptime(value, "%d/%m/%Y")
        if "/" in value
        else datetime.fromisoformat(value.replace("Z", "+00:00"))
    )
    return {
        "match_id": f"af:{meta['_id']}",
        "native_id": meta["_id"],
        "source": "af",
        "competition_id": numeric_id("af", meta["competition_id"]),
        "competition": "Dynasty Scouting League",
        "season_id": numeric_id("af", meta["season_id"]),
        "season": "2024",
        "gender": "male",
        "country": "Nigeria",
        "match_date": date.date().isoformat(),
        "kick_off": None,
        "stage": "Regular Season",
        "matchweek": None,
        **{
            side: {
                "id": numeric_id("af", meta[f"{side}_team"]),
                "name": meta[f"{side}_team_string"],
            }
            for side in ("home", "away")
        },
        "home_score": int(meta["home_goals"]),
        "away_score": int(meta["away_goals"]),
        "has_360": False,
        "reconstructed": False,
        "demo": False,
        "training": True,
        "data_tier": "full",
        "licence": "Apache-2.0",
        "sequence_method": "inferred_control_runs",
        "clock_provenance": "video offsets; second half mapped to minute 45",
        "period_durations": {
            "1": seconds(meta["first_half_end_time"])
            - seconds(meta["match_start_time"]),
            "2": seconds(meta["match_end_time"])
            - seconds(meta["second_half_start_time"]),
        },
        "capabilities": {
            "full_events": True,
            "freeze_frames": False,
            "pass_options": False,
        },
    }


def convert(meta: dict, rows: list[dict]) -> tuple[dict, list[dict], dict]:
    """Normalize reviewed streams; quarantine ambiguous dates/goals and missing sides.

    isHome describes venue (including neutral=3), not the acting team's identity.
    Determine sides by team_id. Starting direction labels name the starting side:
    'left' attacks +x, as documented in the provider's helper.
    """
    issues = coverage(meta, rows)
    if issues:
        raise ValueError(", ".join(issues))
    match = catalogue_entry(meta)
    names, lineups = {}, []
    for side in ("home", "away"):
        players = []
        for starter, group in ((True, "line_up"), (False, "subs")):
            for p in meta.get(f"{side}_team_{group}", []):
                pid = numeric_id("af", p["player_id"])
                name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
                names[p["player_id"]] = {"id": pid, "name": name}
                players.append(
                    {
                        "player_id": pid,
                        "player_name": name,
                        "jersey_number": int(p.get("number") or 0),
                        "positions": [
                            {
                                "position": p.get("position"),
                                "start_reason": "Starting XI",
                            }
                        ]
                        if starter
                        else [],
                        "source_player_id": p["player_id"],
                    }
                )
        lineups.append(
            {
                "team_id": match[side]["id"],
                "team_name": match[side]["name"],
                "lineup": players,
            }
        )
    match["lineups"] = lineups
    events, omitted, seen = [], Counter(), set()
    for source in rows:
        name, typ, outcome = (
            source["event_name"],
            source.get("event_type", "").strip(),
            source.get("event_outcome", ""),
        )
        side = next(
            (s for s in ("home", "away") if source["team_id"] == meta[f"{s}_team"]),
            None,
        )
        if side is None:
            raise ValueError("Event team outside match")
        t = seconds(source["event_start_time"])
        half = source.get("event_half")
        if half not in (1, 2):
            half = 1 if t <= seconds(meta["first_half_end_time"]) else 2
        anchor = seconds(
            meta["match_start_time"] if half == 1 else meta["second_half_start_time"]
        )
        local = t - anchor
        if local < 0:
            # Half-time substitutions legitimately precede the second-half whistle.
            if name == "SUBSTITUTION" and half == 2:
                local = 0
            else:
                omitted["outside_period_clock"] += 1
                continue
        if local > match["period_durations"][str(half)]:
            omitted["outside_period_clock"] += 1
            continue
        event = {
            "id": source["_id"],
            "period": half,
            "minute": NOMINAL[half] + local // 60,
            "second": local % 60,
            "elapsed_match_seconds": local
            + (match["period_durations"]["1"] if half == 2 else 0),
            "timestamp": (
                f"{local // 3600:02}:{local // 60 % 60:02}:{local % 60:02}.000"
            ),
            "team": match[side],
            "source_extra": source,
            "duration": max(0, seconds(source["event_stop_time"]) - t),
        }
        player = names.get(source.get("player_id"))
        if player:
            event["player"] = player
        else:
            omitted["unknown_player"] += 1
            continue
        action, raw_type, result = None, None, "success"
        if name in ("PASS", "CROSS", "THROW_IN", "CORNER", "FREE_KICK"):
            action, raw_type = (
                {
                    "PASS": "pass",
                    "CROSS": "cross",
                    "THROW_IN": "throw_in",
                    "CORNER": "corner_crossed",
                    "FREE_KICK": "freekick_short",
                }[name],
                "Pass",
            )
            if name == "CORNER" and typ == "SHORT":
                action = "corner_short"
            if name == "FREE_KICK":
                if typ in ("OFF_TARGET", "ON_TARGET", "SHOT_BLOCKED"):
                    action, raw_type, result = "shot_freekick", "Shot", "fail"
                elif typ in ("HIGH_CROSS", "LOW_CROSS"):
                    action = "freekick_crossed"
        elif name in ("SHOT", "GOAL", "PENALTY") and typ != "TEAM_OWN_GOAL":
            action, raw_type, result = (
                "shot",
                "Shot",
                "success" if name == "GOAL" else "fail",
            )
            if name == "PENALTY" or outcome == "PENALTY":
                action = "shot_penalty"
            elif outcome == "FREE_KICK":
                action = "shot_freekick"
        elif name == "DEF_ACTIONS":
            action, raw_type = {
                "TACKLE": ("tackle", "Duel"),
                "INTERCEPTION": ("interception", "Interception"),
                "CLEARANCE": ("clearance", "Clearance"),
                "FOUL": ("foul", "Foul Committed"),
                "PENALTY_CONCEDED": ("foul", "Foul Committed"),
                "BLOCK": (None, "Block"),
                "BLOCKED_PASS": (None, "Block"),
                "RECOVERY": (None, "Ball Recovery"),
                "DRIBBLED_PAST": (None, "Dribbled Past"),
                "ERROR": (None, "Error"),
            }.get(typ, (None, None))
        elif name == "POSSESSION":
            action, raw_type = {
                "DRIBBLE": ("take_on", "Dribble"),
                "BALL_PROGRESSION": ("dribble", "Carry"),
                "POSSESSION_LOST": ("bad_touch", "Miscontrol"),
                "FOUL_WON": (None, "Foul Won"),
                "PENALTY_WON": (None, "Foul Won"),
                "OFFSIDE": (None, "Offside"),
                "OFFSIDE_PROVOKED": (None, "Offside"),
                "SHIELD_BALL": (None, "Shield"),
            }.get(typ, (None, None))
        elif name == "DUEL":
            raw_type = "Duel"
            event["duel"] = {
                "type": {"name": "Aerial" if typ == "AERIAL_DUEL" else "Ground"},
                "outcome": {"name": "Lost" if outcome == "UNSUCCESSFUL" else "Won"},
            }
        elif name == "GK_ACTIONS":
            action, raw_type = {
                "GOAL_KEEPER_THROW": ("pass", "Pass"),
                "PUNCH": ("keeper_punch", "Goal Keeper"),
                "CLAIMED_CROSS": ("keeper_claim", "Goal Keeper"),
                "CATCH": ("keeper_pick_up", "Goal Keeper"),
                "SMOTHER": ("keeper_pick_up", "Goal Keeper"),
            }.get(typ, (None, None))
        elif name == "SAVE":
            action, raw_type = "keeper_save", "Goal Keeper"
        elif name == "CARD":
            raw_type = "Bad Behaviour"
            event["bad_behaviour"] = {
                "card": {"name": "Red Card" if outcome == "RED" else "Yellow Card"}
            }
        elif name == "SUBSTITUTION":
            replacement = names.get(outcome)
            if replacement:
                raw_type = "Substitution"
                event["substitution"] = {"replacement": replacement}
        elif name == "OWN_GOAL" or (name == "GOAL" and typ == "TEAM_OWN_GOAL"):
            raw_type = "Own Goal Against"
        if raw_type is None:
            omitted[f"{name}:{typ}"] += 1
            continue
        event["type"] = {"name": raw_type}
        if action or name in ("DEF_ACTIONS", "POSSESSION", "DUEL"):
            if outcome == "UNSUCCESSFUL" or action in ("bad_touch", "foul"):
                result = "fail"
            try:
                xy = coordinates(
                    float(source["event_start_x"]),
                    float(source["event_start_y"]),
                    497,
                    328,
                )
                end = coordinates(
                    float(source["event_end_x"]), float(source["event_end_y"]), 497, 328
                )
            except (ValueError, KeyError):
                omitted["invalid_coordinates"] += 1
                continue
            attacks_right = meta[f"{side}_team_starting_direction"] == "left"
            if (not attacks_right) != (half == 2):
                xy, end = (105 - xy[0], 68 - xy[1]), (105 - end[0], 68 - end[1])
            event["location"] = [xy[0] * 120 / 105, (68 - xy[1]) * 80 / 68]
            end_loc = [end[0] * 120 / 105, (68 - end[1]) * 80 / 68]
            if action:
                event.update(
                    spadl_type=action,
                    spadl_result=result,
                    spadl_bodypart="head" if outcome == "HEADER" else "other",
                )
            if raw_type == "Pass":
                event["pass"] = {"end_location": end_loc, "cross": name == "CROSS"}
                kind = {
                    "CORNER": "Corner",
                    "FREE_KICK": "Free Kick",
                    "THROW_IN": "Throw-in",
                }.get(name)
                if kind:
                    event["pass"]["type"] = {"name": kind}
                if result == "fail":
                    event["pass"]["outcome"] = {"name": "Incomplete"}
            elif raw_type == "Shot":
                event["shot"] = {
                    "outcome": {"name": "Goal" if name == "GOAL" else "Off T"},
                    "type": {
                        "name": {
                            "shot_penalty": "Penalty",
                            "shot_freekick": "Free Kick",
                        }.get(action, "Open Play")
                    },
                    "body_part": {"name": "Head" if outcome == "HEADER" else "Other"},
                }
                # Do not invent shot endpoints or an observed body part.
            elif raw_type == "Carry":
                event["carry"] = {"end_location": end_loc}
            elif raw_type == "Dribble":
                event["dribble"] = {
                    "outcome": {
                        "name": "Complete" if result == "success" else "Incomplete"
                    }
                }
            elif raw_type == "Duel":
                event["duel"] = {
                    "type": {"name": "Tackle"},
                    "outcome": {"name": "Won" if result == "success" else "Lost"},
                }
        # Providers can tag the same kick as both a corner/free-kick and a cross/pass.
        signature = (
            half,
            local,
            side,
            player["id"],
            raw_type,
            tuple(event.get("location", [])),
            tuple((event.get("pass") or {}).get("end_location", [])),
        )
        if signature in seen:
            omitted["duplicate_action_annotation"] += 1
            continue
        seen.add(signature)
        events.append(event)
    goals = Counter(
        e["team"]["id"]
        for e in events
        if e["type"]["name"] == "Shot" and e["shot"]["outcome"]["name"] == "Goal"
    )
    for e in events:
        if e["type"]["name"] == "Own Goal Against":
            other = (
                match["away"]["id"]
                if e["team"]["id"] == match["home"]["id"]
                else match["home"]["id"]
            )
            goals[other] += 1
    if any(goals[match[s]["id"]] != match[f"{s}_score"] for s in ("home", "away")):
        raise ValueError("Observed goals disagree with score; quarantine")
    return match, identify_events(match, events), dict(omitted)
