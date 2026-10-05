"""Data access and bounded per-match cache. Metrics and model modules stay pure."""

import json
import time
from functools import lru_cache
from typing import Any

import pandas as pd
import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row

from matchpulse.config import get_settings
from matchpulse.metrics.match import compute_match
from matchpulse.teams import match_colors, team_short


def connect() -> psycopg.Connection:
    """Connect through central configuration, with a bounded statement timeout."""
    return psycopg.connect(
        get_settings().database_url,
        row_factory=dict_row,
        options="-c statement_timeout=30000",
    )


@lru_cache(maxsize=1)
def catalogue() -> dict[str, dict]:
    """Read the complete catalogue, including reconstructed matches."""
    return {
        m["match_id"]: m
        for m in json.loads(
            (get_settings().data_dir / "catalogue/matches.json").read_text()
        )
        if m["demo"]
    }


@lru_cache(maxsize=1)
def source_metadata() -> dict[int, dict]:
    """Supplement DB catalogue with source stadium/referee names when available."""
    matches = {}
    for p in (get_settings().data_dir / "raw/statsbomb/data/matches").glob("*/*.json"):
        matches.update({m["match_id"]: m for m in json.loads(p.read_text())})
    return matches


def require_match(match_id: str) -> dict:
    """Constrain demo routes to available matches."""
    if match_id not in catalogue():
        raise HTTPException(404, "Match not found")
    return catalogue()[match_id]


@lru_cache(maxsize=128)
def _bundle(match_id: str, epoch: int) -> dict[str, Any]:
    require_match(match_id)
    with connect() as conn:
        meta = conn.execute(
            "SELECT meta FROM matches WHERE match_id=%s", (match_id,)
        ).fetchone()
        if not meta:
            raise HTTPException(404, "Match not loaded")
        rows = conn.execute(
            "SELECT event_id, extra, xg, vaep, vaep_off, vaep_def, xt "
            "FROM events WHERE match_id=%s "
            "ORDER BY period, (extra->>'index')::integer",
            (match_id,),
        ).fetchall()
    if not rows:
        raise HTTPException(503, "Match events not loaded")
    result = compute_match(
        pd.DataFrame(rows),
        meta["meta"],
        source_metadata().get(meta["meta"]["native_id"]),
    )
    # Raw extras are discarded; retain model values for window features.
    return result


def bundle(match_id: str) -> dict[str, Any]:
    """Five-minute cache TTL picks up model backfills without an API change.

    Use clear_cache immediately after a backfill when embedding windows are rebuilt.
    """
    return _bundle(match_id, int(time.monotonic() // 300))


def clear_cache() -> None:
    """Invalidate cached model results after DB backfills."""
    _bundle.cache_clear()


def match_cards(competition: str | None = None) -> list[dict]:
    """Serve all demo cards with real detail available, including null dates."""
    cards = []
    for m in catalogue().values():
        key = f"{m['competition_id']}-{m['season_id']}"
        if competition and competition not in (key, m["competition"]):
            continue
        hc, ac = match_colors(m["home"]["name"], m["away"]["name"])
        cards.append(
            {
                **{
                    k: m[k]
                    for k in (
                        "match_id",
                        "competition",
                        "season",
                        "stage",
                        "match_date",
                        "reconstructed",
                        "home_score",
                        "away_score",
                    )
                },
                "competition_key": key,
                "home": {
                    **m["home"],
                    "short": team_short(m["home"]["name"]),
                    "color": hc,
                },
                "away": {
                    **m["away"],
                    "short": team_short(m["away"]["name"]),
                    "color": ac,
                },
                "has_detail": True,
            }
        )
    return cards


def competitions() -> list[dict]:
    """Catalogue counts, using fixture competition keys."""
    comps = {}
    for m in catalogue().values():
        key = f"{m['competition_id']}-{m['season_id']}"
        row = comps.setdefault(
            key,
            {
                "id": key,
                **{k: m[k] for k in ("competition", "season", "country", "gender")},
                "n_matches": 0,
            },
        )
        row["n_matches"] += 1
    return list(comps.values())
