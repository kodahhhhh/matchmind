"""Generate API fixtures (the frontend contract) from raw StatsBomb data.

Usage: python3 scripts/make_fixtures.py [native_match_id ...]   (default: 3869685, the 2022 World Cup final)

Shapes are the contract (AGENTS.md: fixtures/ outranks PLAN.md). Values are real where the
raw data has them (events, coordinates, lineups, scores, StatsBomb xG) and *proxies* where
our models don't exist yet: `xg` = StatsBomb xG, `vaep` / momentum / danger = a simple
threat-gain proxy, counterfactual + analog numbers = placeholders. Stdlib only.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/statsbomb/data"
CATALOGUE = ROOT / "data/catalogue/matches.json"
COLORS = ROOT / "shared/team_colors.json"
OUT = ROOT / "fixtures"

PITCH_L, PITCH_W = 105.0, 68.0
FINAL_THIRD = 70.0
DEMO_KEYS = {}


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")


def r(v, n=3):
    return None if v is None else round(v, n)


# ---------------------------------------------------------------- teams & names

def team_colors(name: str, table: dict) -> dict:
    c = table.get(name) or table["_default"]
    return {"primary": c[0], "alt": c[1]}


def _oklab(hex_: str):
    rgb = [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    l = 0.4122214708 * lin[0] + 0.5363325363 * lin[1] + 0.0514459929 * lin[2]
    m = 0.2119034982 * lin[0] + 0.6806995451 * lin[1] + 0.1073969566 * lin[2]
    s = 0.0883024619 * lin[0] + 0.2817188376 * lin[1] + 0.6299787005 * lin[2]
    l, m, s = (v ** (1 / 3) for v in (l, m, s))
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def match_colors(home: str, away: str, table: dict) -> tuple[str, str]:
    """Home keeps its primary; away switches to its alt when the two would be hard to tell apart."""
    h, a = team_colors(home, table), team_colors(away, table)
    dist = lambda x, y: 100 * math.dist(_oklab(x), _oklab(y))
    away_c = a["primary"] if dist(h["primary"], a["primary"]) >= 25 else a["alt"]
    if dist(h["primary"], away_c) < 25:  # both away options clash: home falls back too
        return h["alt"], a["primary"]
    return h["primary"], away_c


def short_name(nick: str | None, full: str) -> str:
    base = nick or full
    parts = base.split()
    if nick and len(parts) >= 2:
        return " ".join(parts[1:])
    return parts[-1] if parts else base


def team_short(name: str) -> str:
    return name.replace(" ", "")[:3].upper()


# ---------------------------------------------------------------- geometry

def to_spadl(loc, flip: bool):
    if not loc:
        return None, None
    x = loc[0] * PITCH_L / 120.0
    y = (80.0 - loc[1]) * PITCH_W / 80.0
    if flip:
        x, y = PITCH_L - x, PITCH_W - y
    return r(x, 2), r(y, 2)


def threat(x: float, y: float) -> float:
    """Crude zone value in the acting team's attacking frame (proxy for xT until W3 lands)."""
    d = math.hypot(PITCH_L - x, PITCH_W / 2 - y)
    return 0.32 * math.exp(-d / 16.0)


# ---------------------------------------------------------------- event mapping

def map_type(ev) -> str | None:
    t = ev["type"]["name"]
    if t == "Pass":
        p = ev["pass"]
        kind = (p.get("type") or {}).get("name")
        return {"Corner": "corner", "Free Kick": "freekick", "Throw-in": "throw_in",
                "Goal Kick": "goalkick", "Kick Off": "kickoff"}.get(kind, "cross" if p.get("cross") else "pass")
    if t == "Shot":
        kind = ev["shot"]["type"]["name"]
        return {"Penalty": "shot_penalty", "Free Kick": "shot_freekick"}.get(kind, "shot")
    return {"Carry": "carry", "Dribble": "take_on", "Interception": "interception",
            "Clearance": "clearance", "Ball Recovery": "recovery", "Block": "block",
            "Foul Committed": "foul", "Miscontrol": "bad_touch", "Dispossessed": "dispossessed",
            "Goal Keeper": "keeper_action"}.get(t) or ("tackle" if t == "Duel" and ev["duel"].get("type", {}).get("name") == "Tackle" else None)


def result_of(ev, typ: str) -> str:
    t = ev["type"]["name"]
    if t == "Pass":
        o = (ev["pass"].get("outcome") or {}).get("name")
        return "success" if o is None else ("offside" if o == "Pass Offside" else "fail")
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


def bodypart(ev) -> str | None:
    bp = (ev.get("shot") or ev.get("pass") or {}).get("body_part", {}).get("name")
    if not bp:
        return None
    return "head" if bp == "Head" else ("foot" if "Foot" in bp else "other")


def clock_label(period: int, minute: int) -> str:
    caps = {1: 45, 2: 90, 3: 105, 4: 120}
    shown = minute + 1
    cap = caps.get(period)
    return f"{cap}+{shown - cap}'" if cap and shown > cap else f"{shown}'"


# ---------------------------------------------------------------- build one match

def build_match(native: int, cat: dict, colors: dict) -> None:
    mid = f"sb:{native}"
    raw = json.loads((RAW / f"events/{native}.json").read_text())
    lineups = {t["team_name"]: t for t in json.loads((RAW / f"lineups/{native}.json").read_text())}
    meta_raw = next((m for f in (RAW / "matches").glob("*/*.json") for m in json.loads(f.read_text()) if m["match_id"] == native), None)

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
        return offsets[ev["period"]] + (60 * ev["minute"] + ev["second"]) - starts.get(ev["period"], 0)

    players_info = {}
    for tname, t in lineups.items():
        for p in t["lineup"]:
            players_info[p["player_id"]] = {
                "player_id": p["player_id"], "name": p.get("player_nickname") or p["player_name"],
                "short_name": short_name(p.get("player_nickname"), p["player_name"]),
                "jersey": p["jersey_number"], "team": side.get(tname),
                "position": p["positions"][0]["position"] if p["positions"] else None,
                "starter": bool(p["positions"]) and p["positions"][0].get("start_reason") == "Starting XI",
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
        base = {"period": ev["period"], "minute": ev["minute"], "second": ev["second"], "t": r(elapsed(ev), 1), "team": team}
        eid = f"{mid}:{ev['index']}"
        # markers
        tn = ev["type"]["name"]
        if tn == "Shot" and ev["shot"]["outcome"]["name"] == "Goal":
            markers.append({**base, "type": "goal", "event_id": eid, "player_id": pid,
                            "detail": "penalty" if ev["shot"]["type"]["name"] == "Penalty" else None})
        if tn == "Own Goal For":
            markers.append({**base, "type": "goal", "event_id": eid, "player_id": None, "detail": "own_goal"})
        if tn == "Substitution":
            markers.append({**base, "type": "sub", "event_id": eid, "player_id": ev["substitution"]["replacement"]["id"],
                            "player_off_id": pid, "detail": ev["substitution"].get("outcome", {}).get("name")})
        card = (ev.get("foul_committed") or ev.get("bad_behaviour") or {}).get("card", {}).get("name")
        if card:
            markers.append({**base, "type": "card", "event_id": eid, "player_id": pid,
                            "detail": "red" if "Red" in card else ("second_yellow" if "Second" in card else "yellow")})

        typ = map_type(ev)
        if not typ or team is None:
            continue
        flip = team == "away"
        x, y = to_spadl(ev.get("location"), flip)
        end = (ev.get("pass") or ev.get("carry") or ev.get("shot") or {}).get("end_location")
        ex, ey = to_spadl(end[:2] if end else None, flip)
        if ex is None:
            ex, ey = x, y
        sb_xg = ev.get("shot", {}).get("statsbomb_xg")
        res = result_of(ev, typ)
        # threat-gain proxy, in the acting team's frame
        gain = 0.0
        if x is not None and typ in ("pass", "cross", "carry", "take_on", "freekick", "corner", "throw_in") and res == "success":
            ax, ay, bx, by = (x, y, ex, ey) if not flip else (PITCH_L - x, PITCH_W - y, PITCH_L - ex, PITCH_W - ey)
            gain = threat(bx, by) - threat(ax, ay)
        elif typ.startswith("shot"):
            gain = (sb_xg or 0) * (1.0 if res == "goal" else 0.6)
        elif typ in ("bad_touch", "dispossessed") or res == "fail":
            gain = -0.01
        seq = f"{mid}:s{ev['possession']}"
        poss_team[seq] = side.get(ev["possession_team"]["name"])
        events.append({
            "id": eid, **base, "player_id": pid,
            "player": players_info.get(pid, {}).get("short_name") if pid else None,
            "type": typ, "result": res, "bodypart": bodypart(ev),
            "x": x, "y": y, "end_x": ex, "end_y": ey,
            "xg": r(sb_xg, 4), "sb_xg": r(sb_xg, 4), "vaep": r(gain, 4),
            "sequence_id": seq, "under_pressure": bool(ev.get("under_pressure")),
        })

    # ---------------- timeline (per period+minute bucket)
    buckets = {}
    for e in events:
        k = (e["period"], e["minute"])
        b = buckets.setdefault(k, {"home": defaultdict(float), "away": defaultdict(float)})
        s = b[e["team"]]
        if e["type"] in ("pass", "cross") :
            s["passes"] += 1
            s["passes_ok"] += e["result"] == "success"
        if e["type"].startswith("shot"):
            s["shots"] += 1
        s["xg"] += e["xg"] or 0
        s["vaep"] += e["vaep"] or 0
        ax = e["end_x"] if e["team"] == "home" else PITCH_L - e["end_x"]
        if e["type"] in ("pass", "cross", "carry", "take_on", "shot", "shot_penalty") and ax is not None and ax > FINAL_THIRD:
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
                "xg": r(s["xg"], 4), "xg_cum": r(cum[s_name], 4),
                "passes": int(s["passes"]), "shots": int(s["shots"]), "vaep": r(s["vaep"], 4),
            }
        raw_mom.append(h["vaep"] - a["vaep"])
        minutes.append(row)
    for i, row in enumerate(minutes):  # rolling 5-min momentum, same period only
        win = [raw_mom[j] for j in range(max(0, i - 4), i + 1) if minutes[j]["period"] == row["period"]]
        row["momentum"] = r(sum(win) / len(win), 4)

    # ---------------- turning points: biggest shift in mean momentum, 8-min windows
    W = 8
    cands = []
    for i in range(W, len(minutes) - W):
        before = [m["momentum"] for m in minutes[i - W:i]]
        after = [m["momentum"] for m in minutes[i:i + W]]
        cands.append((abs(sum(after) / W - sum(before) / W), i, sum(after) / W - sum(before) / W))
    cands.sort(reverse=True)
    chosen = []
    for mag, i, delta in cands:
        if all(abs(i - j) > 12 for _, j, _ in chosen):
            chosen.append((mag, i, delta))
        if len(chosen) == 3:
            break
    def window_stats(rows):
        out = {}
        for s in ("home", "away"):
            n = max(len(rows), 1)
            out[s] = {"possession": r(sum(x[s]["possession"] for x in rows) / n), "field_tilt": r(sum(x[s]["field_tilt"] for x in rows) / n),
                      "xg": r(sum(x[s]["xg"] for x in rows), 3), "shots": sum(x[s]["shots"] for x in rows)}
        out["momentum"] = r(sum(x["momentum"] for x in rows) / max(len(rows), 1), 4)
        return out
    turning = []
    for rank, (mag, i, delta) in enumerate(sorted(chosen, key=lambda c: -c[0])):
        b_rows, a_rows = minutes[i - W:i], minutes[i:i + W]
        lo, hi = a_rows[0], a_rows[-1]
        key_ids = [m["event_id"] for m in markers if m["type"] == "goal" and (lo["period"], lo["minute"]) <= (m["period"], m["minute"]) <= (hi["period"], hi["minute"])]
        key_ids += [e["id"] for e in sorted((e for e in events if (lo["period"], lo["minute"]) <= (e["period"], e["minute"]) <= (hi["period"], hi["minute"]) and e["type"].startswith("shot")), key=lambda e: -(e["xg"] or 0))[:3] if e["id"] not in key_ids]
        turning.append({
            "id": f"{mid}:tp{rank + 1}", "rank": rank + 1,
            "start": {"index": lo["index"], "period": lo["period"], "minute": lo["minute"], "label": lo["label"]},
            "end": {"index": hi["index"], "period": hi["period"], "minute": hi["minute"], "label": hi["label"]},
            "team_gaining": "home" if delta > 0 else "away", "magnitude": r(mag, 4),
            "before": window_stats(b_rows), "after": window_stats(a_rows), "key_event_ids": key_ids,
        })

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
        outcome = "goal" if any(e["result"] == "goal" for e in shots) else ("shot" if shots else "lost")
        names = []
        for e in own:
            if e["player"] and (not names or names[-1] != e["player"]):
                names.append(e["player"])
        seq_rows.append({
            "id": sid, "team": team,
            "start": {"t": evs[0]["t"], "period": evs[0]["period"], "minute": evs[0]["minute"], "second": evs[0]["second"], "label": clock_label(evs[0]["period"], evs[0]["minute"])},
            "end": {"t": evs[-1]["t"], "period": evs[-1]["period"], "minute": evs[-1]["minute"], "second": evs[-1]["second"]},
            "duration": r(evs[-1]["t"] - evs[0]["t"], 1), "n_events": len(evs), "event_ids": [e["id"] for e in evs],
            "danger": r(danger, 4), "xg": r(sum(e["xg"] or 0 for e in shots), 3), "outcome": outcome, "players": names[:8],
        })
    seq_rows.sort(key=lambda s: -s["danger"])

    # ---------------- players
    mins_played = {}
    total_min = minutes[-1]["minute"] + 1 if minutes else 90
    subs_on = {m["player_id"]: m["minute"] for m in markers if m["type"] == "sub"}
    subs_off = {m["player_off_id"]: m["minute"] for m in markers if m["type"] == "sub"}
    stats = defaultdict(lambda: defaultdict(float))
    for e in events:
        if not e["player_id"]:
            continue
        s = stats[e["player_id"]]
        s["vaep"] += e["vaep"] or 0
        s["vaep_off"] += max(e["vaep"] or 0, 0) if e["type"] not in ("tackle", "interception", "clearance", "recovery", "block") else 0
        if e["type"] in ("tackle", "interception", "clearance", "recovery", "block"):
            s["vaep_def"] += 0.01 if e["result"] == "success" else 0
            s[e["type"]] += 1
        if e["type"] in ("pass", "cross"):
            s["passes"] += 1
            s["passes_ok"] += e["result"] == "success"
        ax0 = e["x"] if e["team"] == "home" else PITCH_L - (e["x"] or 0)
        ax1 = e["end_x"] if e["team"] == "home" else PITCH_L - (e["end_x"] or 0)
        if e["type"] in ("pass", "cross", "carry") and e["result"] == "success" and e["x"] is not None:
            d0, d1 = PITCH_L - ax0, PITCH_L - ax1
            if d1 <= 0.75 * d0 and ax1 > PITCH_L / 2:
                s["prog_" + ("carries" if e["type"] == "carry" else "passes")] += 1
                s["prog_distance"] += ax1 - ax0
        if e["type"].startswith("shot"):
            s["shots"] += 1
            s["xg"] += e["xg"] or 0
    for pid, s in stats.items():
        s["vaep"] += s["vaep_def"]
    players = []
    for pid, info in players_info.items():
        if pid not in stats and not info["starter"] and pid not in subs_on:
            continue
        on = 0 if info["starter"] else subs_on.get(pid)
        if on is None:
            continue
        off = subs_off.get(pid, total_min)
        s = stats.get(pid, defaultdict(float))
        played = max(off - on, 1)
        players.append({
            **{k: info[k] for k in ("player_id", "name", "short_name", "jersey", "team", "position", "starter")},
            "minutes": int(played),
            "vaep": r(s["vaep"], 4), "vaep_off": r(s["vaep_off"], 4), "vaep_def": r(s["vaep_def"], 4),
            "vaep_per90": r(s["vaep"] * 90 / played, 4),
            "passes": int(s["passes"]), "pass_pct": r(s["passes_ok"] / s["passes"] if s["passes"] else None),
            "progression": {"passes": int(s["prog_passes"]), "carries": int(s["prog_carries"]), "distance": r(s["prog_distance"], 1)},
            "defending": {k: int(s[k]) for k in ("tackle", "interception", "clearance", "recovery", "block")},
            "shots": int(s["shots"]), "xg": r(s["xg"], 3),
        })
    players.sort(key=lambda p: -(p["vaep"] or 0))

    # ---------------- match meta
    pair = dict(zip(("home", "away"), match_colors(home_name, away_name, colors)))
    teams = {s: {"id": cat[s]["id"], "name": cat[s]["name"], "short": team_short(cat[s]["name"]), "color": pair[s]} for s in ("home", "away")}
    lineup_out = {"home": [], "away": []}
    for pid, info in players_info.items():
        if info["team"]:
            lineup_out[info["team"]].append({k: info[k] for k in ("player_id", "name", "short_name", "jersey", "position", "starter")})
    for s in lineup_out:
        lineup_out[s].sort(key=lambda p: (not p["starter"], p["jersey"]))
    periods = []
    for p in sorted(period_len):
        if p == 5:
            continue
        rows = [m for m in minutes if m["period"] == p]
        periods.append({"period": p, "start_index": rows[0]["index"], "end_index": rows[-1]["index"], "start_t": offsets[p], "end_t": r(offsets[p] + period_len[p] - starts[p], 1)})
    score = {"home": cat["home_score"], "away": cat["away_score"]}
    if any(shootout.values()):
        score["penalties"] = shootout
    match = {
        "match_id": mid, "competition": cat["competition"], "season": cat["season"], "stage": cat["stage"],
        "match_date": cat["match_date"], "kick_off": cat["kick_off"], "reconstructed": cat["reconstructed"],
        "venue": (meta_raw or {}).get("stadium", {}).get("name"), "referee": (meta_raw or {}).get("referee", {}).get("name"),
        "teams": teams, "score": score, "periods": periods, "duration_t": periods[-1]["end_t"],
        "lineups": lineup_out, "markers": sorted(markers, key=lambda m: m["t"]),
    }

    d = OUT / "matches" / mid.replace(":", "_")
    dump(d / "match.json", match)
    dump(d / "events.json", {"match_id": mid, "events": events})
    dump(d / "timeline.json", {"match_id": mid, "minutes": minutes})
    dump(d / "sequences.json", {"match_id": mid, "sequences": seq_rows[:5]})
    dump(d / "players.json", {"match_id": mid, "players": players})
    dump(d / "turning-points.json", {"match_id": mid, "turning_points": turning})
    build_llm_fixtures(d, mid, match, events, minutes, turning, seq_rows)
    print(f"{mid}: {len(events)} events, {len(minutes)} minutes, {len(seq_rows)} sequences, {len(players)} players, turning points at {[t['start']['label'] for t in turning]}")


def build_llm_fixtures(d: Path, mid: str, match: dict, events: list, minutes: list, turning: list, seqs: list) -> None:
    by_id = {e["id"]: e for e in events}
    tname = {s: match["teams"][s]["name"] for s in ("home", "away")}
    goal_markers = [m for m in match["markers"] if m["type"] == "goal"]

    # counterfactual: remove the first goal inside the top turning point (placeholder numbers)
    tp = turning[0]
    idx = {(x["period"], x["minute"]): x["index"] for x in minutes}
    in_tp = [m for m in goal_markers if tp["start"]["index"] <= idx[(m["period"], m["minute"])] <= tp["end"]["index"]]
    target = (in_tp or goal_markers)[0]
    cat = json.loads(CATALOGUE.read_text())
    analog_src = [m for m in cat if m["demo"] and m["match_id"] != mid and m["competition"] in ("FIFA World Cup", "UEFA Euro")][:40:8]
    cf = {
        "match_id": mid, "event_id": target["event_id"], "change": "remove_goal",
        "label": "Modelled hypothetical", "horizon_minutes": 15,
        "method": "trained_model",
        "model": {"name": "Game-state quantile model (LightGBM)", "trained_matches": 2924, "coverage_p10_p90": {"xg": 0.88, "possession": 0.79}},
        "anchor": {"period": target["period"], "minute": target["minute"], "label": clock_label(target["period"], target["minute"])},
        "actual": {s: {"xg": tp["after"][s]["xg"], "possession": tp["after"][s]["possession"], "goals": sum(1 for m in in_tp if m["team"] == s)} for s in ("home", "away")},
        "modelled": {
            "home": {"xg": {"p10": 0.12, "p50": 0.41, "p90": 0.93}, "possession": {"p10": 0.44, "p50": 0.53, "p90": 0.61}},
            "away": {"xg": {"p10": 0.05, "p50": 0.27, "p90": 0.71}, "possession": {"p10": 0.39, "p50": 0.47, "p90": 0.56}},
        },
        # the trained model forecasts 15-minute totals only, so per-minute modelled values are null
        "series": [{"offset_min": k, "actual": {"home": r(0.03 * k, 3), "away": r(0.06 * k, 3)}, "modelled": None} for k in range(0, 16)],
        "analog_summary": {"n": 40, "home": {"xg": {"p10": 0.05, "p50": 0.3, "p90": 0.81}}, "away": {"xg": {"p10": 0.02, "p50": 0.22, "p90": 0.64}}},
        "analogs": [{"match_id": a["match_id"], "competition": a["competition"], "season": a["season"], "home": a["home"]["name"], "away": a["away"]["name"],
                     "minute": 70 + i * 3, "score_state": "+1", "similarity": r(0.94 - i * 0.04, 2),
                     "next15": {"xg_for": r(0.22 + 0.1 * i, 2), "xg_against": r(0.35 - 0.05 * i, 2), "goals_for": i % 2, "goals_against": int(i == 1)}} for i, a in enumerate(analog_src)],
        "n_analogs": 40,
        "caveat": "Learned from observational data: teams change their approach because of the score, so effects are confounded. Shown as a range next to real comparable situations, not a prediction.",
    }
    dump(d / "counterfactual.json", cf)

    # search: commentary-like lines for the top sequences (placeholder text built from real data)
    def seq_line(s):
        who = " → ".join(s["players"][:4])
        end = {"goal": "and it ends in a goal", "shot": f"ending in a shot ({s['xg']:.2f} xG)", "lost": "before possession is lost"}[s["outcome"]]
        return f"{s['start']['label']} {tname[s['team']]} move the ball through {who}, {end}."
    dump(d / "search.json", {"query": "dangerous attacks down the left", "results": [
        {"sequence_id": s["id"], "match_id": mid, "minute": s["start"]["minute"], "label": s["start"]["label"], "team": s["team"], "text": seq_line(s), "score": r(0.91 - 0.07 * i, 2),
         "match": {"home": tname["home"], "away": tname["away"], "competition": match["competition"], "season": match["season"],
                   "home_color": match["teams"]["home"]["color"], "away_color": match["teams"]["away"]["color"]}}
        for i, s in enumerate(seqs[:5])]})

    # commentary: one broadcast line per sequence (Luna in production; template text here), in match order
    dump(d / "commentary.json", {"match_id": mid, "lines": [
        {"sequence_id": s["id"], "team": s["team"], "start": s["start"], "text": seq_line(s), "danger": s["danger"], "outcome": s["outcome"]}
        for s in sorted(seqs, key=lambda s: s["start"]["t"])]})

    # ask: an SSE transcript for "Find the turning point" built from computed numbers
    b, a = tp["before"], tp["after"]
    g = tp["team_gaining"]
    o = "away" if g == "home" else "home"
    k = [by_id[i] for i in tp["key_event_ids"] if i in by_id][:2]
    cites = " ".join(f"[[ev:{e['id']}]]" for e in k)
    text = (
        f"The match turned between {tp['start']['label']} and {tp['end']['label']}. "
        f"{tname[g]} went from {b[g]['field_tilt'] * 100:.0f}% to {a[g]['field_tilt'] * 100:.0f}% of final-third actions, "
        f"and their xG in that window was {a[g]['xg']:.2f} against {a[o]['xg']:.2f}. "
        f"The key moments: {cites}. "
        f"Before the shift, {tname[o]} had {b[o]['possession'] * 100:.0f}% of the passes; after it, {a[o]['possession'] * 100:.0f}%."
    )
    stream = [{"type": "tool", "name": "find_turning_points", "args": {"match_id": mid}},
              {"type": "tool", "name": "get_window_stats", "args": {"match_id": mid, "from": tp["start"]["label"], "to": tp["end"]["label"]}}]
    for i in range(0, len(text), 24):
        stream.append({"type": "text", "delta": text[i:i + 24]})
    for e in k:
        stream.append({"type": "citation", "ref": f"ev:{e['id']}", "label": f"{clock_label(e['period'], e['minute'])} {e['player']} {e['type'].replace('_', ' ')}"})
    stream.append({"type": "done"})
    dump(d / "ask.json", {"match_id": mid, "question": "Find the turning point", "stream": stream})


def main() -> None:
    ids = [int(x) for x in sys.argv[1:]] or [3869685]
    cat = json.loads(CATALOGUE.read_text())
    colors = json.loads(COLORS.read_text())
    demo = [m for m in cat if m["demo"]]
    comps = {}
    for m in demo:
        key = f"{m['competition_id']}-{m['season_id']}"
        c = comps.setdefault(key, {"id": key, "competition": m["competition"], "season": m["season"], "country": m["country"], "gender": m["gender"], "n_matches": 0})
        c["n_matches"] += 1
    dump(OUT / "competitions.json", {"competitions": list(comps.values())})
    have = set(ids)
    def card(m):
        hc, ac = match_colors(m["home"]["name"], m["away"]["name"], colors)
        return {
        "match_id": m["match_id"], "competition_key": f"{m['competition_id']}-{m['season_id']}", "competition": m["competition"], "season": m["season"],
        "stage": m["stage"], "match_date": m["match_date"], "reconstructed": m["reconstructed"],
        "home": {"id": m["home"]["id"], "name": m["home"]["name"], "short": team_short(m["home"]["name"]), "color": hc},
        "away": {"id": m["away"]["id"], "name": m["away"]["name"], "short": team_short(m["away"]["name"]), "color": ac},
        "home_score": m["home_score"], "away_score": m["away_score"], "has_detail": m["native_id"] in have,
        }
    dump(OUT / "matches.json", {"matches": [card(m) for m in demo]})
    by_native = {m["native_id"]: m for m in cat}
    for native in ids:
        build_match(native, by_native[native], colors)


if __name__ == "__main__":
    main()
