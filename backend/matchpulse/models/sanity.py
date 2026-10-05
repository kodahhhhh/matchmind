"""Reproducible player-minute and flagship-match VAEP sanity reports."""

from concurrent.futures import ProcessPoolExecutor
from typing import Any

import pandas as pd

from matchpulse.models.common import (
    catalogue,
    data_dir,
    event_clock,
    event_seconds,
    raw_events,
    save_json,
)


def player_totals(match: dict[str, Any]) -> list[dict[str, Any]]:
    events = [e for e in raw_events(match["native_id"]) if e["period"] < 5]
    offsets, lengths = event_clock(events)
    full_time = sum(lengths.values())
    active, seconds, names = {}, {}, {}
    for event in events:
        t = offsets[event["period"]] + event_seconds(event)
        player = event.get("player", {})
        if player:
            names[player["id"]] = player["name"]
        kind = event["type"]["name"]
        if kind == "Starting XI":
            for item in event["tactics"]["lineup"]:
                p = item["player"]
                active[p["id"]] = 0.0
                names[p["id"]] = p["name"]
        card = (
            event.get("bad_behaviour", {})
            .get("card", event.get("foul_committed", {}).get("card", {}))
            .get("name")
        )
        if kind == "Substitution" or card in ["Red Card", "Second Yellow"]:
            pid = player.get("id")
            if pid in active:
                seconds[pid] = seconds.get(pid, 0) + t - active.pop(pid)
            if kind == "Substitution":
                replacement = event["substitution"]["replacement"]
                active[replacement["id"]] = t
                names[replacement["id"]] = replacement["name"]
    for pid, start in active.items():
        seconds[pid] = seconds.get(pid, 0) + full_time - start
    values = pd.read_parquet(
        data_dir() / f"processed/vaep/{match['native_id']}.parquet"
    )
    totals = values[values.period_id < 5].groupby("player_id").vaep_value.sum()
    return [
        {
            "player_id": pid,
            "name": names.get(pid, str(pid)),
            "minutes": duration / 60,
            "vaep": float(totals.get(pid, 0)),
        }
        for pid, duration in seconds.items()
    ]


def main() -> None:
    with ProcessPoolExecutor(max_workers=16) as pool:
        rows = [row for group in pool.map(player_totals, catalogue()) for row in group]
    players = (
        pd.DataFrame(rows)
        .groupby("player_id")
        .agg(name=("name", "last"), minutes=("minutes", "sum"), vaep=("vaep", "sum"))
        .reset_index()
    )
    players["vaep_per90"] = players.vaep * 90 / players.minutes
    top = (
        players[players.minutes >= 900]
        .sort_values("vaep_per90", ascending=False)
        .head(20)
    )
    players.to_parquet(data_dir() / "processed/player_vaep_totals.parquet", index=False)
    final = pd.read_parquet(data_dir() / "processed/vaep/3869685.parquet")
    events = {e["id"]: e for e in raw_events(3869685)}
    final["name"] = final.original_event_id.map(
        lambda v: events.get(v, {}).get("player", {}).get("name")
    )
    final["minute"] = final.original_event_id.map(
        lambda v: events.get(v, {}).get("minute")
    )
    final = final[final.period_id < 5]
    columns = [
        "action_id",
        "original_event_id",
        "name",
        "minute",
        "period_id",
        "type_name",
        "result_name",
        "offensive_value",
        "defensive_value",
        "vaep_value",
    ]
    report = {
        "minutes_definition": (
            "Actual playing-clock minutes including stoppage and extra time, "
            "excluding shootouts/breaks; starting XI, substitutions and "
            "dismissals."
        ),
        "top20_per90_min900": top.to_dict("records"),
        "final_top20_actions": final.nlargest(20, "vaep_value")[columns].to_dict(
            "records"
        ),
        "final_goals": final[
            final.type_name.str.startswith("shot") & (final.result_name == "success")
        ][columns].to_dict("records"),
    }
    save_json("vaep_sanity.json", report)
    print(top.to_string(index=False), flush=True)
    print(pd.DataFrame(report["final_goals"]).to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
