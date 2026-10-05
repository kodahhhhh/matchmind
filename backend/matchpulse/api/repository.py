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
def _catalogue(epoch: int) -> dict[str, dict]:
    """Read the complete catalogue, including reconstructed matches."""
    result = {
        m["match_id"]: m
        for m in json.loads(
            (get_settings().data_dir / "catalogue/matches.json").read_text()
        )
        if m["demo"]
    }
    # Source discovery is enabled by a sources directory in DATA_DIR. An isolated
    # StatsBomb-only DATA_DIR still serves exactly its original reference contract.
    if (get_settings().data_dir / "sources").is_dir():
        with connect() as conn:
            rows = conn.execute(
                "SELECT meta FROM matches WHERE source <> 'sb' "
                "AND meta->>'data_tier' IN ('full','lite')"
            ).fetchall()
        result.update({row["meta"]["match_id"]: row["meta"] for row in rows})
    from matchpulse.sources.reconcile import canonical_matches

    preferred = canonical_matches(list(result.values()))
    return {
        mid: m for mid, m in result.items() if mid.startswith("sb:") or mid in preferred
    }


def catalogue() -> dict[str, dict]:
    """Refresh discovery every five minutes after incremental source loads."""
    return _catalogue(int(time.monotonic() // 300))


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


def require_full(match_id: str, capability: str = "full_events") -> dict:
    """Reject analytics that require actions the source does not provide."""
    match = require_match(match_id)
    if match.get("data_tier") == "lite":
        raise HTTPException(422, "This feature requires a full event stream")
    if match.get("capabilities", {}).get(capability) is False:
        raise HTTPException(422, f"This source does not support {capability}")
    return match


@lru_cache(maxsize=128)
def _bundle(match_id: str, epoch: int) -> dict[str, Any]:
    require_match(match_id)
    with connect() as conn:
        meta = conn.execute(
            "SELECT meta FROM matches WHERE match_id=%s", (match_id,)
        ).fetchone()
        if not meta:
            raise HTTPException(404, "Match not loaded")
        if meta["meta"].get("data_tier") == "lite":
            lite = conn.execute(
                "SELECT payload FROM source_lite_matches WHERE match_id=%s", (match_id,)
            ).fetchone()
            if not lite:
                raise HTTPException(503, "Lite payload not loaded")
            from matchpulse.api.lite import compute_lite

            return compute_lite(lite["payload"])
        rows = conn.execute(
            "SELECT event_id, extra, xg, vaep, vaep_off, vaep_def, xt "
            "FROM events WHERE match_id=%s "
            "ORDER BY period, (extra->>'index')::integer",
            (match_id,),
        ).fetchall()
    if not rows:
        raise HTTPException(503, "Match events not loaded")
    if meta["meta"].get("source", "sb") != "sb":
        from matchpulse.sources.common import decode_name

        for row in rows:
            extra = row["extra"]
            if "player" in extra:
                extra["player"]["name"] = decode_name(extra["player"]["name"])
            extra["team"]["name"] = decode_name(extra["team"]["name"])
            if extra["type"]["name"] == "Own Goal Against":
                # Retain the observed ball action in replay; the separate source
                # Own Goal For marker supplies its benefiting team.
                extra["type"] = {"name": "Miscontrol"}
    result = compute_match(
        pd.DataFrame(rows),
        meta["meta"],
        source_metadata().get(meta["meta"]["native_id"])
        if meta["meta"].get("source", "sb") == "sb"
        else None,
    )
    if meta["meta"].get("source", "sb") != "sb":
        result["match"].update(
            data_tier="full",
            source=meta["meta"]["source"],
            capabilities=meta["meta"].get("capabilities", {}),
        )
        source_match = meta["meta"].get("source_match", {})
        if (
            meta["meta"]["source"] == "wy"
            and source_match.get("duration") == "Penalties"
        ):
            shootout = {
                team["side"]: team.get("scoreP")
                for team in source_match.get("teamsData", {}).values()
            }
            if set(shootout) == {"home", "away"} and all(
                isinstance(value, int) for value in shootout.values()
            ):
                result["match"]["score"]["penalties"] = shootout
        unknown_jerseys = {
            p["player_id"]
            for t in meta["meta"].get("lineups", [])
            for p in t["lineup"]
            if p.get("jersey_known") is False
        }
        for roster in [*result["match"]["lineups"].values(), result["players"]]:
            for player in roster:
                if player["player_id"] in unknown_jerseys:
                    player["jersey"] = None
        pressure = {row["event_id"]: row["extra"].get("under_pressure") for row in rows}
        for event in result["events"]:
            event["under_pressure"] = pressure[event["id"]]
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
    _catalogue.cache_clear()


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
                **(
                    {"data_tier": "lite", "capabilities": m.get("capabilities", {})}
                    if m.get("data_tier") == "lite"
                    else {}
                ),
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
