"""Pure fixture-compatible match analytics over DB event DataFrames.

Fallbacks: xg -> sb_xg; vaep -> exponential distance-to-goal threat gain,
shots -> sb_xg (goal) / 0.6*sb_xg (miss), failed actions -> -0.01.
Possession is pass share; field tilt is final-third action share. Empty buckets
use a neutral 0.5 fraction. Read model columns row by row, including zero values.
StatsBomb locations are already attacking-relative across halves; the one away
rotation fixes home left-to-right orientation. The same logic uses raw locations
preserved in extra to match fixture rounding (including out-of-pitch endpoints).
"""

import math
from collections import defaultdict

import pandas as pd

from matchmind.metrics.turning import find_turning_points
from matchmind.teams import match_colors, short_name, team_short

PITCH_L, PITCH_W, FINAL_THIRD = 105.0, 68.0, 70.0


def r(v: float | None, n: int = 3) -> float | None:
    return None if v is None else round(v, n)


def to_spadl(loc: list | None, flip: bool) -> tuple:
    if not loc:
        return None, None
    x = loc[0] * PITCH_L / 120.0
    y = (80.0 - loc[1]) * PITCH_W / 80.0
    if flip:
        x, y = PITCH_L - x, PITCH_W - y
    return r(x, 2), r(y, 2)


def threat(x: float, y: float) -> float:
    """Distance-to-goal zone value in the acting team's attacking frame."""
    d = math.hypot(PITCH_L - x, PITCH_W / 2 - y)
    return 0.32 * math.exp(-d / 16.0)


# ---------------------------------------------------------------- event mapping


def map_type(ev: dict) -> str | None:
    t = ev["type"]["name"]
    if t == "Pass":
        p = ev["pass"]
        kind = (p.get("type") or {}).get("name")
        return {
            "Corner": "corner",
            "Free Kick": "freekick",
            "Throw-in": "throw_in",
            "Goal Kick": "goalkick",
            "Kick Off": "kickoff",
        }.get(kind, "cross" if p.get("cross") else "pass")
    if t == "Shot":
        kind = ev["shot"]["type"]["name"]
        return {"Penalty": "shot_penalty", "Free Kick": "shot_freekick"}.get(
            kind, "shot"
        )
    return {
        "Carry": "carry",
        "Dribble": "take_on",
        "Interception": "interception",
        "Clearance": "clearance",
        "Ball Recovery": "recovery",
        "Block": "block",
        "Foul Committed": "foul",
        "Miscontrol": "bad_touch",
        "Dispossessed": "dispossessed",
        "Goal Keeper": "keeper_action",
    }.get(t) or (
        "tackle"
        if t == "Duel" and ev["duel"].get("type", {}).get("name") == "Tackle"
        else None
    )


def result_of(ev: dict, typ: str) -> str:
    t = ev["type"]["name"]
    if t == "Pass":
        o = (ev["pass"].get("outcome") or {}).get("name")
        return (
            "success" if o is None else ("offside" if o == "Pass Offside" else "fail")
        )
    if t == "Shot":
        return "goal" if ev["shot"]["outcome"]["name"] == "Goal" else "fail"
    if t == "Dribble":
        return "success" if ev["dribble"]["outcome"]["name"] == "Complete" else "fail"
    if t == "Duel":
        o = (ev["duel"].get("outcome") or {}).get("name", "")
        return "success" if o in ("Won", "Success In Play", "Success Out") else "fail"
    if typ in ("bad_touch", "dispossessed", "foul"):
        return "fail"
    return "success"


def bodypart(ev: dict) -> str | None:
    bp = (ev.get("shot") or ev.get("pass") or {}).get("body_part", {}).get("name")
    if not bp:
        return None
    return "head" if bp == "Head" else ("foot" if "Foot" in bp else "other")


def clock_label(period: int, minute: int) -> str:
    caps = {1: 45, 2: 90, 3: 105, 4: 120}
    shown = minute + 1
    cap = caps.get(period)
    return f"{cap}+{shown - cap}'" if cap and shown > cap else f"{shown}'"


def compute_match(frame: pd.DataFrame, cat: dict, meta_raw: dict | None = None) -> dict:
    """Compute all GET representations from raw events and current model columns."""
    mid = cat["match_id"]
    records = frame.where(pd.notnull(frame), None).to_dict("records")
    raw = [row["extra"] for row in records]
    model_values = {
        row["event_id"]: {
            k: (None if pd.isna(row.get(k)) else row.get(k))
            for k in ("xg", "vaep", "vaep_off", "vaep_def", "xt")
        }
        for row in records
    }
    lineups = {t["team_name"]: t for t in cat["lineups"]}
    home_name, away_name = cat["home"]["name"], cat["away"]["name"]
    side = {home_name: "home", away_name: "away"}

    # elapsed-time offsets so t is monotonic across periods
    period_len = defaultdict(float)
    for ev in raw:
        mm, ss = ev["minute"], ev["second"]
        period_len[ev["period"]] = max(period_len[ev["period"]], 60 * mm + ss)
    starts = {1: 0, 2: 45 * 60, 3: 90 * 60, 4: 105 * 60, 5: 120 * 60}
    offsets, acc = {}, 0.0
    for p in sorted(period_len):
        offsets[p] = acc
        acc += period_len[p] - starts.get(p, 0) + 1

    def elapsed(ev):
        return (
            offsets[ev["period"]]
            + (60 * ev["minute"] + ev["second"])
            - starts.get(ev["period"], 0)
        )

    players_info = {}
    for tname, t in lineups.items():
        for p in t["lineup"]:
            players_info[p["player_id"]] = {
                "player_id": p["player_id"],
                "name": p.get("player_nickname") or p["player_name"],
                "short_name": short_name(p.get("player_nickname"), p["player_name"]),
                "jersey": p["jersey_number"],
                "team": side.get(tname),
                "position": p["positions"][0]["position"] if p["positions"] else None,
                "starter": bool(p["positions"])
                and p["positions"][0].get("start_reason") == "Starting XI",
            }

    events, markers, shootout = [], [], {"home": 0, "away": 0}
    poss_team = {}
    for ev in raw:
        tname = ev.get("team", {}).get("name")
        team = side.get(tname)
        if ev["type"]["name"] == "Shot" and ev["period"] == 5:
            if ev["shot"]["outcome"]["name"] == "Goal":
                shootout[team] += 1
            continue
        if ev["period"] == 5:
            continue
        pid = ev.get("player", {}).get("id")
        base = {
            "period": ev["period"],
            "minute": ev["minute"],
            "second": ev["second"],
            "t": r(elapsed(ev), 1),
            "team": team,
        }
        eid = f"{mid}:{ev['index']}"
        # markers
        tn = ev["type"]["name"]
        if tn == "Shot" and ev["shot"]["outcome"]["name"] == "Goal":
            markers.append(
                {
                    **base,
                    "type": "goal",
                    "event_id": eid,
                    "player_id": pid,
                    "detail": "penalty"
                    if ev["shot"]["type"]["name"] == "Penalty"
                    else None,
                }
            )
        if tn == "Own Goal For":
            markers.append(
                {
                    **base,
                    "type": "goal",
                    "event_id": eid,
                    "player_id": None,
                    "detail": "own_goal",
                }
            )
        if tn == "Substitution":
            markers.append(
                {
                    **base,
                    "type": "sub",
                    "event_id": eid,
                    "player_id": ev["substitution"]["replacement"]["id"],
                    "player_off_id": pid,
                    "detail": ev["substitution"].get("outcome", {}).get("name"),
                }
            )
        card = (
            (ev.get("foul_committed") or ev.get("bad_behaviour") or {})
            .get("card", {})
            .get("name")
        )
        if card:
            markers.append(
                {
                    **base,
                    "type": "card",
                    "event_id": eid,
                    "player_id": pid,
                    "detail": "red"
                    if "Red" in card
                    else ("second_yellow" if "Second" in card else "yellow"),
                }
            )

        typ = map_type(ev)
        if not typ or team is None:
            continue
        flip = team == "away"
        x, y = to_spadl(ev.get("location"), flip)
        end = (ev.get("pass") or ev.get("carry") or ev.get("shot") or {}).get(
            "end_location"
        )
        ex, ey = to_spadl(end[:2] if end else None, flip)
        if ex is None:
            ex, ey = x, y
        sb_xg = ev.get("shot", {}).get("statsbomb_xg")
        res = result_of(ev, typ)
        # threat-gain proxy, in the acting team's frame
        gain = 0.0
        if (
            x is not None
            and typ
            in ("pass", "cross", "carry", "take_on", "freekick", "corner", "throw_in")
            and res == "success"
        ):
            ax, ay, bx, by = (
                (x, y, ex, ey)
                if not flip
                else (PITCH_L - x, PITCH_W - y, PITCH_L - ex, PITCH_W - ey)
            )
            gain = threat(bx, by) - threat(ax, ay)
        elif typ.startswith("shot"):
            gain = (sb_xg or 0) * (1.0 if res == "goal" else 0.6)
        elif typ in ("bad_touch", "dispossessed") or res == "fail":
            gain = -0.01
        model = model_values.get(eid, {})
        metric_xg = model.get("xg") if model.get("xg") is not None else sb_xg
        metric_vaep = model.get("vaep") if model.get("vaep") is not None else gain
        seq = f"{mid}:s{ev['possession']}"
        poss_team[seq] = side.get(ev["possession_team"]["name"])
        events.append(
            {
                "id": eid,
                **base,
                "player_id": pid,
                "player": players_info.get(pid, {}).get("short_name") if pid else None,
                "type": typ,
                "result": res,
                "bodypart": bodypart(ev),
                "x": x,
                "y": y,
                "end_x": ex,
                "end_y": ey,
                "xg": r(metric_xg, 4),
                "sb_xg": r(sb_xg, 4),
                "vaep": r(metric_vaep, 4),
                "sequence_id": seq,
                "under_pressure": bool(ev.get("under_pressure")),
            }
        )

    # ---------------- timeline (per period+minute bucket)
    buckets = {}
    for e in events:
        k = (e["period"], e["minute"])
        b = buckets.setdefault(
            k, {"home": defaultdict(float), "away": defaultdict(float)}
        )
        s = b[e["team"]]
        if e["type"] in ("pass", "cross"):
            s["passes"] += 1
            s["passes_ok"] += e["result"] == "success"
        if e["type"].startswith("shot"):
            s["shots"] += 1
        s["xg"] += e["xg"] or 0
        s["vaep"] += e["vaep"] or 0
        ax = (
            e["end_x"]
            if e["team"] == "home" or e["end_x"] is None
            else PITCH_L - e["end_x"]
        )
        if (
            e["type"] in ("pass", "cross", "carry", "take_on", "shot", "shot_penalty")
            and ax is not None
            and ax > FINAL_THIRD
        ):
            s["final_third"] += 1
    keys = sorted(buckets)
    minutes, cum = [], {"home": 0.0, "away": 0.0}
    raw_mom = []
    for i, k in enumerate(keys):
        b = buckets[k]
        h, a = b["home"], b["away"]
        tot_p = h["passes"] + a["passes"]
        tot_f = h["final_third"] + a["final_third"]
        row = {"index": i, "period": k[0], "minute": k[1], "label": clock_label(*k)}
        for s_name, s in (("home", h), ("away", a)):
            cum[s_name] += s["xg"]
            row[s_name] = {
                "possession": r(s["passes"] / tot_p if tot_p else 0.5),
                "field_tilt": r(s["final_third"] / tot_f if tot_f else 0.5),
                "xg": r(s["xg"], 4),
                "xg_cum": r(cum[s_name], 4),
                "passes": int(s["passes"]),
                "shots": int(s["shots"]),
                "vaep": r(s["vaep"], 4),
            }
        raw_mom.append(h["vaep"] - a["vaep"])
        minutes.append(row)
    for i, row in enumerate(minutes):  # rolling five clock minutes, same period only
        win = [
            raw_mom[j]
            for j in range(max(0, i - 4), i + 1)
            if minutes[j]["period"] == row["period"]
            and row["minute"] - minutes[j]["minute"] < 5
        ]
        row["momentum"] = r(sum(win) / len(win), 4)

    # ---------------- sequences
    seqs = defaultdict(list)
    for e in events:
        seqs[e["sequence_id"]].append(e)
    seq_rows = []
    for sid, evs in seqs.items():
        team = poss_team.get(sid) or evs[0]["team"]
        own = [e for e in evs if e["team"] == team]
        if len(own) < 3:
            continue
        danger = sum(max(e["vaep"] or 0, 0) for e in own)
        shots = [e for e in own if e["type"].startswith("shot")]
        outcome = (
            "goal"
            if any(e["result"] == "goal" for e in shots)
            else ("shot" if shots else "lost")
        )
        names = []
        for e in own:
            if e["player"] and (not names or names[-1] != e["player"]):
                names.append(e["player"])
        seq_rows.append(
            {
                "id": sid,
                "team": team,
                "start": {
                    "t": evs[0]["t"],
                    "period": evs[0]["period"],
                    "minute": evs[0]["minute"],
                    "second": evs[0]["second"],
                    "label": clock_label(evs[0]["period"], evs[0]["minute"]),
                },
                "end": {
                    "t": evs[-1]["t"],
                    "period": evs[-1]["period"],
                    "minute": evs[-1]["minute"],
                    "second": evs[-1]["second"],
                },
                "duration": r(evs[-1]["t"] - evs[0]["t"], 1),
                "n_events": len(evs),
                "event_ids": [e["id"] for e in evs],
                "danger": r(danger, 4),
                "xg": r(sum(e["xg"] or 0 for e in shots), 3),
                "outcome": outcome,
                "players": names[:8],
            }
        )
    seq_rows.sort(key=lambda s: -s["danger"])

    # ---------------- players
    total_min = (
        max(
            (
                offsets[p] + period_len[p] - starts.get(p, 0)
                for p in period_len
                if p < 5
            ),
            default=5400,
        )
        / 60
    )
    subs_on = {m["player_id"]: m["t"] / 60 for m in markers if m["type"] == "sub"}
    subs_off = {m["player_off_id"]: m["t"] / 60 for m in markers if m["type"] == "sub"}
    stats = defaultdict(lambda: defaultdict(float))
    for e in events:
        if not e["player_id"]:
            continue
        s = stats[e["player_id"]]
        s["vaep"] += e["vaep"] or 0
        model = model_values.get(e["id"], {})
        defensive = e["type"] in (
            "tackle",
            "interception",
            "clearance",
            "recovery",
            "block",
        )
        s["vaep_off"] += (
            model["vaep_off"]
            if model.get("vaep_off") is not None
            else (max(e["vaep"] or 0, 0) if not defensive else 0)
        )
        s["vaep_def"] += (
            model["vaep_def"]
            if model.get("vaep_def") is not None
            else (0.01 if defensive and e["result"] == "success" else 0)
        )
        if e["type"] in ("tackle", "interception", "clearance", "recovery", "block"):
            s[e["type"]] += 1
        if e["type"] in ("pass", "cross"):
            s["passes"] += 1
            s["passes_ok"] += e["result"] == "success"
        ax0 = e["x"] if e["team"] == "home" else PITCH_L - (e["x"] or 0)
        ax1 = e["end_x"] if e["team"] == "home" else PITCH_L - (e["end_x"] or 0)
        if (
            e["type"] in ("pass", "cross", "carry")
            and e["result"] == "success"
            and e["x"] is not None
        ):
            d0, d1 = PITCH_L - ax0, PITCH_L - ax1
            if d1 <= 0.75 * d0 and ax1 > PITCH_L / 2:
                s["prog_" + ("carries" if e["type"] == "carry" else "passes")] += 1
                s["prog_distance"] += ax1 - ax0
        if e["type"].startswith("shot"):
            s["shots"] += 1
            s["xg"] += e["xg"] or 0
    players = []
    for pid, info in players_info.items():
        if pid not in stats and not info["starter"] and pid not in subs_on:
            continue
        on = 0 if info["starter"] else subs_on.get(pid)
        if on is None:
            continue
        red_times = [
            m["t"] / 60
            for m in markers
            if m["type"] == "card"
            and m["player_id"] == pid
            and m["detail"] in ("red", "second_yellow")
        ]
        off = min([subs_off.get(pid, total_min), *red_times])
        s = stats.get(pid, defaultdict(float))
        played = max(off - on, 1)
        players.append(
            {
                **{
                    k: info[k]
                    for k in (
                        "player_id",
                        "name",
                        "short_name",
                        "jersey",
                        "team",
                        "position",
                        "starter",
                    )
                },
                "minutes": int(round(played)),
                "vaep": r(s["vaep"], 4),
                "vaep_off": r(s["vaep_off"], 4),
                "vaep_def": r(s["vaep_def"], 4),
                "vaep_per90": r(s["vaep"] * 90 / played, 4),
                "passes": int(s["passes"]),
                "pass_pct": r(s["passes_ok"] / s["passes"] if s["passes"] else None),
                "progression": {
                    "passes": int(s["prog_passes"]),
                    "carries": int(s["prog_carries"]),
                    "distance": r(s["prog_distance"], 1),
                },
                "defending": {
                    k: int(s[k])
                    for k in (
                        "tackle",
                        "interception",
                        "clearance",
                        "recovery",
                        "block",
                    )
                },
                "shots": int(s["shots"]),
                "xg": r(s["xg"], 3),
            }
        )
    players.sort(key=lambda p: -(p["vaep"] or 0))

    # ---------------- match meta
    pair = dict(zip(("home", "away"), match_colors(home_name, away_name), strict=True))
    teams = {
        s: {
            "id": cat[s]["id"],
            "name": cat[s]["name"],
            "short": team_short(cat[s]["name"]),
            "color": pair[s],
        }
        for s in ("home", "away")
    }
    lineup_out = {"home": [], "away": []}
    for info in players_info.values():
        if info["team"]:
            lineup_out[info["team"]].append(
                {
                    k: info[k]
                    for k in (
                        "player_id",
                        "name",
                        "short_name",
                        "jersey",
                        "position",
                        "starter",
                    )
                }
            )
    for s in lineup_out:
        lineup_out[s].sort(key=lambda p: (not p["starter"], p["jersey"]))
    periods = []
    for p in sorted(period_len):
        if p == 5:
            continue
        rows = [m for m in minutes if m["period"] == p]
        if not rows:
            continue
        periods.append(
            {
                "period": p,
                "start_index": rows[0]["index"],
                "end_index": rows[-1]["index"],
                "start_t": offsets[p],
                "end_t": r(offsets[p] + period_len[p] - starts[p], 1),
            }
        )
    score = {"home": cat["home_score"], "away": cat["away_score"]}
    if any(shootout.values()):
        score["penalties"] = shootout
    match = {
        "match_id": mid,
        "competition": cat["competition"],
        "season": cat["season"],
        "stage": cat["stage"],
        "match_date": cat["match_date"],
        "kick_off": cat["kick_off"],
        "reconstructed": cat["reconstructed"],
        "venue": (meta_raw or {}).get("stadium", {}).get("name"),
        "referee": (meta_raw or {}).get("referee", {}).get("name"),
        "teams": teams,
        "score": score,
        "periods": periods,
        "duration_t": periods[-1]["end_t"] if periods else 0.0,
        "lineups": lineup_out,
        "markers": sorted(markers, key=lambda m: m["t"]),
    }

    return {
        "match": match,
        "events": events,
        "minutes": minutes,
        "sequences": seq_rows,
        "players": players,
        "turning_points": find_turning_points(
            pd.DataFrame(minutes), pd.DataFrame(events), markers, mid
        ),
        "model_values": model_values,
    }
