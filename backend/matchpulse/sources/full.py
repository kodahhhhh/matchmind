"""Source-converted SPADL into the existing model and raw-event staging boundary."""

from collections import Counter

import numpy as np
import pandas as pd

from matchpulse.sources.common import NOMINAL, identify_events, numeric_id


def normalize_actions(
    match: dict,
    actions: pd.DataFrame,
    original: dict[int, dict],
    markers: list[dict] | None = None,
) -> tuple[pd.DataFrame, list[dict]]:
    """Preserve converter coordinates; annotate interpolated carries explicitly.

    SPADL uses home-oriented metres. Existing raw metrics/storage use the acting
    team's attacking frame and StatsBomb-shaped locations. Namespaced IDs avoid
    native-ID collisions; synthetic carries have no claimed provider event ID.
    """
    actions = actions.copy().reset_index(drop=True)
    actions["action_id"] = np.arange(len(actions))
    actions["original_event_id"] = actions.original_event_id.astype(object)
    native_home = match["source_home_id"]
    offsets, total = {}, 0.0
    for period, group in actions.groupby("period_id", sort=True):
        offsets[int(period)] = total
        total += float(group.time_seconds.max()) + 1
    events = []
    for row in actions.to_dict("records"):
        period = int(row["period_id"])
        if period not in NOMINAL or period == 5:
            continue
        side = "home" if row["team_id"] == native_home else "away"
        native_event = row["original_event_id"]
        raw = original.get(int(native_event), {}) if pd.notna(native_event) else {}
        inferred = pd.isna(native_event)
        eid = f"{match['match_id']}:a{int(row['action_id']):06d}"
        start = [float(row["start_x"]), float(row["start_y"])]
        end = [float(row["end_x"]), float(row["end_y"])]
        if side == "away":
            start, end = [105 - start[0], 68 - start[1]], [105 - end[0], 68 - end[1]]
        location = [start[0] * 120 / 105, (68 - start[1]) * 80 / 68]
        endpoint = [end[0] * 120 / 105, (68 - end[1]) * 80 / 68]
        kind, result, body = row["type_name"], row["result_name"], row["bodypart_name"]
        time = float(row["time_seconds"])
        pid = row["player_id"]
        pid = (
            numeric_id(match["source"], int(pid))
            if pd.notna(pid) and int(pid) > 0
            else None
        )
        name = (
            match.get("player_names", {}).get(str(int(row["player_id"])))
            if pid
            else None
        )
        event = {
            "id": eid,
            "period": period,
            "minute": NOMINAL[period] + int(time // 60),
            "second": int(time % 60),
            "timestamp": (
                f"{int(time) // 3600:02}:{int(time) // 60 % 60:02}:{time % 60:06.3f}"
            ),
            "elapsed_match_seconds": offsets[period] + time,
            "team": match[side],
            "location": location,
            "duration": 0,
            "source_extra": raw,
            "source_event_id": int(native_event) if pd.notna(native_event) else None,
            "inferred": inferred,
            "spadl_type": kind,
            "spadl_result": result,
            "spadl_bodypart": body,
        }
        if pid:
            event["player"] = {"id": pid, "name": name or "Unknown"}
        if kind in (
            "pass",
            "cross",
            "throw_in",
            "freekick_short",
            "freekick_crossed",
            "corner_short",
            "corner_crossed",
            "goalkick",
        ):
            event["type"] = {"name": "Pass"}
            event["pass"] = {
                "end_location": endpoint,
                "cross": kind in ("cross", "corner_crossed", "freekick_crossed"),
            }
            source_kind = {
                "throw_in": "Throw-in",
                "goalkick": "Goal Kick",
                "freekick_short": "Free Kick",
                "freekick_crossed": "Free Kick",
                "corner_short": "Corner",
                "corner_crossed": "Corner",
            }.get(kind)
            if source_kind:
                event["pass"]["type"] = {"name": source_kind}
            if result != "success":
                event["pass"]["outcome"] = {
                    "name": "Pass Offside" if result == "offside" else "Incomplete"
                }
        elif kind.startswith("shot"):
            event["type"] = {"name": "Shot"}
            event["shot"] = {
                "type": {
                    "name": {
                        "shot_penalty": "Penalty",
                        "shot_freekick": "Free Kick",
                    }.get(kind, "Open Play")
                },
                "outcome": {"name": "Goal" if result == "success" else "Off T"},
                "body_part": {
                    "name": {
                        "head": "Head",
                        "foot_right": "Right Foot",
                        "foot_left": "Left Foot",
                    }.get(body, "Other")
                },
            }
            if result == "owngoal":
                event["type"] = {"name": "Own Goal Against"}
        elif kind == "dribble":
            event.update(type={"name": "Carry"}, carry={"end_location": endpoint})
        elif kind == "take_on":
            event.update(
                type={"name": "Dribble"},
                dribble={
                    "outcome": {
                        "name": "Complete" if result == "success" else "Incomplete"
                    }
                },
            )
        elif kind == "tackle":
            event.update(
                type={"name": "Duel"},
                duel={
                    "type": {"name": "Tackle"},
                    "outcome": {"name": "Won" if result == "success" else "Lost"},
                },
            )
        else:
            event["type"] = {
                "name": {
                    "interception": "Interception",
                    "clearance": "Clearance",
                    "foul": "Foul Committed",
                    "bad_touch": "Miscontrol",
                }.get(kind, "Goal Keeper")
            }
        if result in ("yellow_card", "red_card"):
            event["foul_committed"] = {
                "card": {"name": "Red Card" if result == "red_card" else "Yellow Card"}
            }
        if result == "owngoal":
            event["type"] = {"name": "Own Goal Against"}
            marker = {
                **event,
                "id": eid + ":goal_for",
                "team": match["away" if side == "home" else "home"],
                "type": {"name": "Own Goal For"},
                "derived_marker": True,
            }
            for key in ("player", "spadl_type", "spadl_result", "spadl_bodypart"):
                marker.pop(key, None)
            events.append(marker)
        events.append(event)
        actions.loc[row["action_id"], "original_event_id"] = eid
    actions["game_id"] = numeric_id(match["source"], match["native_id"])
    actions["team_id"] = actions.team_id.map(
        lambda x: numeric_id(match["source"], int(x))
    )
    actions["player_id"] = actions.player_id.map(
        lambda x: (
            numeric_id(match["source"], int(x)) if pd.notna(x) and int(x) > 0 else 0
        )
    )
    actions["home_team_id"] = match["home"]["id"]
    events.extend(markers or [])
    events = identify_events(match, events)
    goals = Counter()
    for e in events:
        if e["type"]["name"] == "Shot" and e["shot"]["outcome"]["name"] == "Goal":
            goals[e["team"]["id"]] += 1
        if e["type"]["name"] == "Own Goal Against":
            goals[
                match["away" if e["team"]["id"] == match["home"]["id"] else "home"][
                    "id"
                ]
            ] += 1
    if any(goals[match[s]["id"]] != match[f"{s}_score"] for s in ("home", "away")):
        raise ValueError(
            f"Converted goal counts {dict(goals)} disagree with source score"
        )
    return actions, events
