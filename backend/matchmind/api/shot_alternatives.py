"""Pass-instead-of-shot orchestration: raw shot lookup, orientation, serialisation."""

from fastapi import HTTPException

from matchmind.api.repository import bundle, require_match
from matchmind.metrics.match import clock_label
from matchmind.models.common import raw_events

# Closer than this (in goal probability) and neither choice is clearly better.
SIMILAR = 0.02
CAVEAT = (
    "Modelled hypothetical from the frozen moment of the shot: defenders would "
    "react, and the receiver's control and finish are assumed. Not what would "
    "have happened."
)
ASSUMPTIONS = [
    "Pass completion from a model of 360 freeze-frame passes (lane and target "
    "defenders, offside line).",
    "After receiving, the better of an immediate first-time shot (our xG model, "
    "same defenders and keeper) or the zone's average threat (xT).",
    "The actual shot and every hypothetical shot use the same xG model, which "
    "never saw this match.",
]


def shot_alternatives(match_id: str, event_id: str) -> dict:
    from matchmind.models.pass_options import alternatives, model_report, spadl_xy

    match = require_match(match_id)
    b = bundle(match_id)
    try:
        index = int(event_id.split(":")[2])
    except (IndexError, ValueError) as exc:
        raise HTTPException(422, "Choose a shot in this match") from exc
    events = raw_events(match["native_id"])
    by_index = {e["index"]: e for e in events}
    shot = by_index.get(index)
    if not event_id.startswith(match_id + ":") or not shot:
        raise HTTPException(422, "Choose a shot in this match")
    if shot["type"]["name"] != "Shot" or shot["period"] == 5:
        raise HTTPException(422, "Choose a shot in this match")
    detail = shot["shot"]
    if detail.get("type", {}).get("name") == "Penalty":
        raise HTTPException(422, "Penalties have no passing alternative")
    if not detail.get("freeze_frame"):
        raise HTTPException(422, "This shot has no player positions to model")
    side = "home" if shot["team"]["id"] == match["home"]["id"] else "away"
    before = [
        m
        for m in b["match"]["markers"]
        if m["type"] == "goal" and int(m["event_id"].split(":")[2]) < index
    ]
    score_diff = sum(m["team"] == side for m in before) - sum(
        m["team"] != side for m in before
    )
    related = next((e for e in events if e["id"] == detail.get("key_pass_id")), None)
    result = alternatives(shot, score_diff, match["native_id"], related)

    def orient(x: float, y: float) -> dict:
        # API frame: home attacks left to right in both halves.
        if side == "away":
            x, y = 105 - x, 68 - y
        return {"x": round(x, 2), "y": round(y, 2)}

    names = {
        p["player_id"]: p["short_name"]
        for lineup in b["match"]["lineups"].values()
        for p in lineup
    }
    options = [
        {
            "player_id": o["player_id"],
            "player": names.get(o["player_id"], o["player"] or "Teammate"),
            **orient(o["x"], o["y"]),
            "p_complete": round(o["p_complete"], 4),
            "xg_if_shot": round(o["xg_if_shot"], 4),
            "xt": round(o["xt"], 4),
            "value": round(o["value"], 4),
        }
        for o in result["options"]
    ]
    shot_xg = round(result["shot_xg"], 4)
    best = options[0] if options else None
    margin = round(best["value"] - shot_xg, 4) if best else None
    comparison = (
        "no_teammates"
        if best is None
        else "similar"
        if abs(margin) < SIMILAR
        else "pass_higher"
        if margin > 0
        else "shot_higher"
    )
    report = model_report()
    player_id = shot.get("player", {}).get("id")
    return {
        "match_id": match_id,
        "event_id": event_id,
        "label": "Modelled hypothetical",
        "shot": {
            "event_id": event_id,
            "team": side,
            "player_id": player_id,
            "player": names.get(player_id, shot.get("player", {}).get("name", "")),
            "period": shot["period"],
            "minute": shot["minute"],
            "label": clock_label(shot["period"], shot["minute"]),
            **orient(*spadl_xy(shot["location"])),
            "xg": shot_xg,
            "outcome": detail.get("outcome", {}).get("name", "Unknown"),
        },
        "options": options,
        "comparison": comparison,
        "margin": margin,
        "model": {
            "name": "Pass completion (LightGBM, StatsBomb 360)",
            "trained_passes": report["n_passes"],
            "trained_matches": report["n_matches"],
            "auc": round(report["metrics"]["model"]["auc"], 4),
            "brier": round(report["metrics"]["model"]["brier"], 4),
            "baseline_auc": round(report["metrics"]["geometry_only"]["auc"], 4),
        },
        "assumptions": ASSUMPTIONS,
        "caveat": CAVEAT,
    }
