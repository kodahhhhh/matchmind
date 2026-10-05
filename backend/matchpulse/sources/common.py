"""Source identities, conservative match dedupe and SPADL normalization."""

import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

NOMINAL = {1: 0, 2: 45, 3: 90, 4: 105, 5: 120}


def numeric_id(source: str, native: object) -> int:
    """Stable bigint namespace outside StatsBomb and within JS safe integers."""
    digest = hashlib.sha256(f"{source}:{native}".encode()).digest()
    return (1 << 48) + int.from_bytes(digest[:6], "big")


def normal_name(name: str) -> str:
    """Accent/case normalization only; no fuzzy automatic identity merges."""
    text = unicodedata.normalize("NFKD", name).casefold()
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def dedupe(
    matches: list[dict], existing: list[dict], aliases: dict[str, str] | None = None
) -> tuple[list[dict], list[dict]]:
    """Prefer StatsBomb for dated team pairs; retain undated matches.

    Ambiguous rematches and score conflicts are quarantined rather than silently
    discarded. Reviewed aliases are explicit; team-name similarity is insufficient.
    """
    aliases = aliases or {}

    def key(m: dict) -> tuple | None:
        if not m.get("match_date"):
            return None
        teams = [normal_name(m[s]["name"]) for s in ("home", "away")]
        return (
            m["match_date"],
            m.get("gender"),
            *sorted(aliases.get(t, t) for t in teams),
        )

    def scores(m: dict) -> dict:
        return {
            aliases.get(
                normal_name(m[side]["name"]), normal_name(m[side]["name"])
            ): m.get(f"{side}_score")
            for side in ("home", "away")
        }

    seen: dict[tuple, list[dict]] = {}
    for m in sorted(existing, key=lambda m: not m["match_id"].startswith("sb:")):
        if (k := key(m)) is not None:
            seen.setdefault(k, []).append(m)
    accepted, duplicates = [], []
    for m in sorted(matches, key=lambda m: not m["match_id"].startswith("sb:")):
        k = key(m)
        same = seen.get(k, []) if k is not None else []
        if same:
            candidate = same[0]
            reason = "duplicate"
            if len(same) > 1:
                reason = "ambiguous_same_day"
            elif scores(m) != scores(candidate):
                reason = "score_conflict"
            duplicates.append(
                {
                    "match_id": m["match_id"],
                    "preferred": candidate["match_id"],
                    "reason": reason,
                }
            )
        else:
            accepted.append(m)
            if k is not None:
                seen[k] = [m]
    return accepted, duplicates


def save_json(path: Path, value: Any) -> None:
    """Atomically replace generated local artifacts; never write model files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def coordinates(x: float, y: float, length: float, width: float) -> tuple[float, float]:
    """Top-left source coordinates to clipped SPADL metres, bottom-left origin."""
    if not np.isfinite([x, y, length, width]).all() or min(length, width) <= 0:
        raise ValueError("Invalid source coordinates")
    return float(np.clip(x / length * 105, 0, 105)), float(
        np.clip(68 - y / width * 68, 0, 68)
    )


def spadl(match: dict, events: list[dict]) -> pd.DataFrame:
    """Convert explicitly classified actions to the existing home-oriented schema.

    Unlike socceraction's source converters, do not infer extra carries from gaps
    in a partially observed stream. Unknown/non-ball actions stay in raw metadata.
    """
    from socceraction.spadl import add_names, config

    rows = []
    for event in events:
        kind = event.get("spadl_type")
        if kind is None or event.get("location") is None:
            continue
        start = coordinates(*event["location"][:2], 120, 80)
        detail = event.get("pass") or event.get("carry") or event.get("shot") or {}
        end = coordinates(*detail.get("end_location", event["location"])[:2], 120, 80)
        if event["team"]["id"] != match["home"]["id"]:
            start = (105 - start[0], 68 - start[1])
            end = (105 - end[0], 68 - end[1])
        rows.append(
            {
                "game_id": numeric_id(match["source"], match["native_id"]),
                "original_event_id": event["id"],
                "action_id": len(rows),
                "period_id": event["period"],
                "time_seconds": (event["minute"] - NOMINAL[event["period"]]) * 60
                + event["second"],
                "team_id": event["team"]["id"],
                "player_id": event.get("player", {}).get("id", 0),
                "start_x": start[0],
                "start_y": start[1],
                "end_x": end[0],
                "end_y": end[1],
                "type_id": config.actiontypes.index(kind),
                "result_id": config.results.index(event.get("spadl_result", "success")),
                "bodypart_id": config.bodyparts.index(
                    event.get("spadl_bodypart", "other")
                ),
                "home_team_id": match["home"]["id"],
            }
        )
    if not rows:
        raise ValueError("No classified full-stream actions")
    return add_names(pd.DataFrame(rows))


def identify_events(match: dict, events: list[dict]) -> list[dict]:
    """Assign stable chronological source-local indices and observed-team sequences.

    Sequences are inferred team-control runs, not provider possession annotations.
    Retain that provenance so downstream copy does not overclaim their quality.
    """
    ordered = sorted(
        events, key=lambda e: (e["period"], e["minute"], e["second"], e["id"])
    )
    previous, period, possession = None, None, 0
    for index, event in enumerate(ordered, 1):
        team = event["team"]
        if previous != team["id"] or period != event["period"]:
            possession += 1
        previous, period = team["id"], event["period"]
        event.update(index=index, possession=possession, possession_team=team)
    return ordered
