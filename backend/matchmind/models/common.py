"""Shared local artifact and reproducible match split utilities."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.model_selection import KFold

from matchmind.config import get_settings


def data_dir() -> Path:
    return get_settings().data_dir


def catalogue() -> list[dict[str, Any]]:
    return [
        m
        for m in json.loads((data_dir() / "catalogue/matches.json").read_text())
        if m["training"]
    ]


def raw_events(native_id: int) -> list[dict[str, Any]]:
    return json.loads(
        (data_dir() / f"raw/statsbomb/data/events/{native_id}.json").read_text()
    )


def save_json(name: str, value: dict[str, Any]) -> None:
    path = data_dir() / "models" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str, allow_nan=False) + "\n")


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def fold_map() -> dict[int, int]:
    ids = np.array(sorted(m["native_id"] for m in catalogue()))
    return {
        int(ids[i]): fold
        for fold, (_, test) in enumerate(
            KFold(5, shuffle=True, random_state=2026).split(ids)
        )
        for i in test
    }


def event_seconds(event: dict[str, Any]) -> float:
    h, m, s = event["timestamp"].split(":")
    return float(h) * 3600 + float(m) * 60 + float(s)


def event_clock(
    events: list[dict[str, Any]],
) -> tuple[dict[int, float], dict[int, float]]:
    lengths = {
        p: max(event_seconds(e) for e in events if e["period"] == p)
        for p in sorted({e["period"] for e in events if e["period"] < 5})
    }
    offset, total = {}, 0.0
    for period, length in lengths.items():
        offset[period] = total
        total += length
    return offset, lengths
