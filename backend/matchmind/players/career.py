"""Precompute held-out career values over every training match, without training."""

import json
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import numpy as np
import pandas as pd
import psycopg

from matchmind.config import get_settings
from matchmind.metrics.match import clock_label
from matchmind.players.sources import save_frame

PASS_TYPES = {
    "pass",
    "cross",
    "freekick_short",
    "freekick_crossed",
    "corner_short",
    "corner_crossed",
    "throw_in",
    "goalkick",
}
SUM_FIELDS = [
    "minutes",
    "vaep",
    "vaep_off",
    "vaep_def",
    "xg",
    "goals",
    "shots",
    "progressive_passes",
    "progressive_carries",
]


def event_seconds(event: dict) -> float:
    h, m, s = event["timestamp"].split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def playing_minutes(events: list[dict], lineups: list[dict]) -> dict[int, float]:
    """Actual period-clock exposure, with substitutions and dismissals.

    Lineup Starting XI records establish starters; raw events establish changes.
    Stoppage/extra time count, breaks and shootouts do not. Temporary Player Off /
    On pairs also remove absence time. Never replace missing dates with DB dates.
    """
    events = [e for e in events if e["period"] < 5]
    lengths = {}
    for e in events:
        lengths[e["period"]] = max(lengths.get(e["period"], 0), event_seconds(e))
    offsets, total = {}, 0.0
    for period in sorted(lengths):
        offsets[period] = total
        total += lengths[period]
    active, seconds, dismissed = {}, defaultdict(float), set()
    for team in lineups:
        for p in team["lineup"]:
            if any(
                pos.get("start_reason") == "Starting XI"
                for pos in p.get("positions", [])
            ):
                active[p["player_id"]] = 0.0
    for event in events:
        time = offsets[event["period"]] + event_seconds(event)
        kind = event["type"]["name"]
        pid = event.get("player", {}).get("id")
        if kind == "Starting XI":
            for p in event["tactics"]["lineup"]:
                active.setdefault(p["player"]["id"], 0.0)
        card = (
            event.get("bad_behaviour", {})
            .get("card", event.get("foul_committed", {}).get("card", {}))
            .get("name")
        )
        red = card in {"Red Card", "Second Yellow"}
        if kind in {"Substitution", "Player Off"} or red:
            if pid in active:
                seconds[pid] += max(0, time - active.pop(pid))
            if red:
                dismissed.add(pid)
            if kind == "Substitution":
                active[event["substitution"]["replacement"]["id"]] = time
        if kind == "Player On" and pid not in active and pid not in dismissed:
            active[pid] = time
    for pid, start in active.items():
        seconds[pid] += max(0, total - start)
    return {pid: duration / 60 for pid, duration in seconds.items()}


def match_career(match: dict) -> tuple[list[dict], dict, dict]:
    """Aggregate OOF actions and attach only real source event/sequence IDs."""
    root = get_settings().data_dir
    native = match["native_id"]
    events = json.loads((root / f"raw/statsbomb/data/events/{native}.json").read_text())
    lineups = json.loads(
        (root / f"raw/statsbomb/data/lineups/{native}.json").read_text()
    )
    minutes = playing_minutes(events, lineups)
    raw = {e["id"]: e for e in events if e["period"] < 5}
    actions = pd.read_parquet(root / f"processed/vaep/{native}.parquet")
    actions = actions[(actions.period_id < 5) & actions.player_id.notna()].copy()
    actions["player_id"] = actions.player_id.astype(int)
    away = actions.team_id != actions.home_team_id
    actions.loc[away, "start_x"] = 105 - actions.loc[away, "start_x"]
    actions.loc[away, "start_y"] = 68 - actions.loc[away, "start_y"]
    metrics = (
        actions.groupby("player_id")
        .agg(
            vaep=("vaep_value", "sum"),
            vaep_off=("offensive_value", "sum"),
            vaep_def=("defensive_value", "sum"),
        )
        .to_dict("index")
    )
    teams = {
        p["player_id"]: team["team_id"] for team in lineups for p in team["lineup"]
    }
    heatmaps = {}
    for pid, group in actions.groupby("player_id"):
        hist, _, _ = np.histogram2d(
            group.start_y, group.start_x, bins=(8, 12), range=((0, 68), (0, 105))
        )
        heatmaps[int(pid)] = hist.astype(int).ravel().tolist()
    shots = pd.read_parquet(
        root / "processed/xg/shots.parquet",
        filters=[("game_id", "==", native), ("period", "<", 5)],
        columns=["original_event_id", "xg"],
    )
    xg = shots.set_index("original_event_id").xg.to_dict()
    for event in raw.values():
        pid = event.get("player", {}).get("id")
        if pid is None:
            continue
        m = metrics.setdefault(pid, {"vaep": 0.0, "vaep_off": 0.0, "vaep_def": 0.0})
        if event["type"]["name"] == "Shot":
            m["shots"] = m.get("shots", 0) + 1
            m["goals"] = m.get("goals", 0) + int(
                event["shot"]["outcome"]["name"] == "Goal"
            )
            if event["id"] not in xg:
                raise ValueError(f"Missing own-model xG for {native}:{event['index']}")
            m["xg"] = m.get("xg", 0.0) + float(xg[event["id"]])
        kind = event["type"]["name"]
        if kind in {"Pass", "Carry"}:
            successful = kind == "Carry" or not event.get("pass", {}).get("outcome")
            start = event.get("location")
            end = event.get(kind.lower(), {}).get("end_location")
            if successful and start and end and (end[0] - start[0]) * 105 / 120 >= 10:
                key = "progressive_passes" if kind == "Pass" else "progressive_carries"
                m[key] = m.get(key, 0) + 1
    rows = []
    for pid in sorted(set(minutes) | set(metrics)):
        if pid not in teams:
            continue
        if minutes.get(pid, 0) == 0 and not any(metrics.get(pid, {}).values()):
            # Bench cards are not playing appearances or model actions.
            continue
        side = "home" if teams[pid] == match["home"]["id"] else "away"
        opponent = "away" if side == "home" else "home"
        rows.append(
            {
                "player_id": pid,
                "match_id": match["match_id"],
                "date": match["match_date"],
                "competition": match["competition"],
                "season": match["season"],
                "team": match[side]["name"],
                "opponent": match[opponent]["name"],
                "in_db": bool(match["demo"]),
                **{
                    f: float(minutes.get(pid, 0))
                    if f == "minutes"
                    else metrics.get(pid, {}).get(f, 0)
                    for f in SUM_FIELDS
                },
            }
        )
    moments = defaultdict(list)
    real = actions[actions.original_event_id.notna()]
    # Split interception+pass components sum to one source action.
    values = (
        real.groupby(["player_id", "original_event_id"]).vaep_value.sum().reset_index()
    )
    for pid, group in values.groupby("player_id"):
        for row in group.nlargest(10, "vaep_value").to_dict("records"):
            e = raw.get(row["original_event_id"])
            if e is None:
                continue
            moments[int(pid)].append(
                {
                    "match_id": match["match_id"],
                    "match_label": (
                        f"{match['home']['name']} vs {match['away']['name']}"
                    ),
                    "minute_label": clock_label(e["period"], e["minute"]),
                    "event_id": f"sb:{native}:{e['index']}",
                    "sequence_id": f"sb:{native}:s{e['possession']}"
                    if e.get("possession") is not None
                    else None,
                    "vaep": float(row["vaep_value"]),
                    "text": None,
                }
            )
    return rows, heatmaps, dict(moments)


def aggregate(frame: pd.DataFrame) -> dict[str, Any]:
    """Sums and per-90 rates weighted by observed exposure, never mean-of-rates."""
    totals = {field: float(frame[field].sum()) for field in SUM_FIELDS}
    minutes = totals["minutes"]
    totals["matches"] = int((frame.minutes > 0).sum())
    totals["vaep_per90"] = totals["vaep"] * 90 / minutes if minutes else 0.0
    totals["vaep_off_per90"] = totals["vaep_off"] * 90 / minutes if minutes else 0.0
    totals["vaep_def_per90"] = totals["vaep_def"] * 90 / minutes if minutes else 0.0
    totals["prog_per90"] = (
        (totals["progressive_passes"] + totals["progressive_carries"]) * 90 / minutes
        if minutes
        else 0.0
    )
    totals["progressive_passes_per90"] = (
        totals["progressive_passes"] * 90 / minutes if minutes else 0.0
    )
    totals["progressive_carries_per90"] = (
        totals["progressive_carries"] * 90 / minutes if minutes else 0.0
    )
    for field in ("goals", "shots", "progressive_passes", "progressive_carries"):
        totals[field] = int(totals[field])
    return totals


def build_careers(workers: int = 8) -> dict:
    """Publish per-match, per-season and all-corpus summaries plus coverage."""
    root = get_settings().data_dir
    output = root / "processed/players"
    catalogue = [
        m
        for m in json.loads((root / "catalogue/matches.json").read_text())
        if m["training"]
    ]
    rows, heatmaps, moments = [], {}, defaultdict(list)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for index, (group, histograms, top) in enumerate(
            pool.map(match_career, catalogue)
        ):
            rows.extend(group)
            for pid, hist in histograms.items():
                heatmaps[pid] = np.array(heatmaps.get(pid, [0] * 96)) + np.array(hist)
            for pid, values in top.items():
                moments[pid] = sorted(moments[pid] + values, key=lambda r: -r["vaep"])[
                    :10
                ]
            if index % 100 == 0:
                print(f"Career {index + 1}/{len(catalogue)}", flush=True)
    frame = pd.DataFrame(rows)
    # Actual DB membership, rather than assuming demo flag means successfully loaded.
    with psycopg.connect(get_settings().database_url) as conn:
        db_matches = {
            row[0]
            for row in conn.execute(
                "SELECT match_id FROM matches m WHERE EXISTS "
                "(SELECT 1 FROM events e WHERE e.match_id=m.match_id)"
            )
        }
        commentary = dict(conn.execute("SELECT sequence_id,text FROM commentary"))
    frame["in_db"] = frame.match_id.isin(db_matches)
    save_frame(frame, output / "matches.parquet")
    seasons, summaries = [], {}
    for pid, group in frame.groupby("player_id"):
        by_competition = []
        for (competition, season, team), part in group.groupby(
            ["competition", "season", "team"]
        ):
            stats = aggregate(part)
            seasons.append(
                {
                    "player_id": int(pid),
                    "competition": competition,
                    "season": season,
                    "team": team,
                    **stats,
                }
            )
            by_competition.append(
                {
                    "competition": competition,
                    "season": season,
                    "team": team,
                    **{
                        f: stats[f]
                        for f in ("matches", "minutes", "vaep_per90", "xg", "goals")
                    },
                }
            )
        totals = aggregate(group)
        hist = heatmaps.get(pid, np.zeros(96))
        normalised = (hist / hist.max()).tolist() if hist.max() else [0.0] * 96
        top = moments[pid]
        for moment in top:
            moment["text"] = commentary.get(moment["sequence_id"])
        summaries[str(pid)] = {
            "career": {
                **{
                    f: totals[f]
                    for f in (
                        "matches",
                        "minutes",
                        "vaep",
                        "vaep_per90",
                        "vaep_off",
                        "vaep_def",
                        "xg",
                        "goals",
                        "shots",
                        "prog_per90",
                    )
                },
                "by_competition": by_competition,
            },
            "heatmap": {"nx": 12, "ny": 8, "values": normalised},
            "top_moments": top,
            "matches": group.sort_values(
                ["date", "match_id"], ascending=False, na_position="last"
            )[
                [
                    "match_id",
                    "date",
                    "competition",
                    "season",
                    "team",
                    "opponent",
                    "minutes",
                    "vaep",
                    "xg",
                    "goals",
                    "in_db",
                ]
            ].to_dict("records"),
        }
    save_frame(pd.DataFrame(seasons), output / "career.parquet")
    temporary = output / "career.tmp.json"
    temporary.write_text(json.dumps(summaries, allow_nan=False))
    temporary.replace(output / "career.json")
    build_coverage()
    print(
        f"Career complete: {len(catalogue)} matches, "
        f"{len(summaries)} players, {len(frame)} appearances",
        flush=True,
    )
    return summaries


def build_coverage() -> list[dict]:
    """Rebuild identity coverage without rereading the corpus event files."""
    output = get_settings().data_dir / "processed/players"
    frame = pd.read_parquet(output / "matches.parquet")
    mapping = pd.read_parquet(output / "player_map.parquet")
    matched = set(mapping.loc[mapping.tm_player_id.notna(), "sb_player_id"])
    coverage = []
    for (competition, season), group in frame.groupby(["competition", "season"]):
        players = set(group.player_id)
        coverage.append(
            {
                "competition": competition,
                "season": season,
                "players": len(players),
                "matched_players": len(players & matched),
                "player_share": len(players & matched) / len(players),
                "minutes": float(group.minutes.sum()),
                "matched_minutes": float(
                    group[group.player_id.isin(matched)].minutes.sum()
                ),
                "minute_share": float(
                    group[group.player_id.isin(matched)].minutes.sum()
                    / group.minutes.sum()
                ),
            }
        )
    (output / "coverage.json").write_text(json.dumps(coverage, indent=2))
    return coverage


if __name__ == "__main__":
    build_careers()
