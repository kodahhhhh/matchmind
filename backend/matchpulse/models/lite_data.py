"""Read frozen local lite snapshots; never fetch, load a DB or write source data."""

import json
from pathlib import Path

import pandas as pd

from matchpulse.models.common import data_dir


def source_files() -> dict[str, list[Path]]:
    """Discover local payloads without using provider network clients."""
    root = data_dir()
    fm = []
    for p in sorted((root / "raw/fotmob").glob("*.body")):
        try:
            d = json.loads(p.read_text())
        except (ValueError, UnicodeError):
            continue
        if (
            isinstance(d, dict)
            and "content" in d
            and d.get("general", {}).get("finished")
        ):
            fm.append(p)
    return {
        "understat": sorted((root / "sources/understat/lite").glob("*.json")),
        "fotmob": fm,
    }


def read_source(name: str, paths: list[Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return metadata and shots; retain unknown clocks and original evidence IDs."""
    matches, rows = [], []
    for path in paths:
        d = json.loads(path.read_text())
        if name == "understat":
            meta = d["meta"]
            matches.append(meta)
            shots = d["shots"]
        elif name == "fotmob":
            g = d["general"]
            teams = d["header"]["teams"]
            meta = {
                "match_id": f"fm:{g['matchId']}",
                "competition": g["leagueName"],
                "match_date": g["matchTimeUTCDate"][:10],
                "home_score": teams[0]["score"],
                "away_score": teams[1]["score"],
                "home": g["homeTeam"],
                "away": g["awayTeam"],
            }
            matches.append(meta)
            shots = [
                {
                    "id": f"{meta['match_id']}:{i}",
                    "team": "home" if s["teamId"] == g["homeTeam"]["id"] else "away",
                    "minute": int(s["min"]) + int(s.get("minAdded") or 0),
                    "period": {"FirstHalf": 1, "SecondHalf": 2}.get(s.get("period")),
                    "second": None,
                    "time_precision": "minute",
                    "x": s["x"],
                    "y": s["y"],
                    "body_part": s.get("shotType"),
                    "situation": s.get("situation"),
                    "result": s["eventType"],
                    "is_own_goal": bool(s.get("isOwnGoal", False)),
                    "provider_xg": s.get("expectedGoals"),
                }
                for i, s in enumerate(d["content"].get("shotmap", {}).get("shots", []))
            ]
        else:
            raise ValueError(f"Unsupported local source: {name}")
        rows.extend(
            {**s, "match_id": meta["match_id"], "competition": meta["competition"]}
            for s in shots
        )
    return pd.DataFrame(matches), pd.DataFrame(rows)
