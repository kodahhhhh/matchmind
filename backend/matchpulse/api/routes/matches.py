"""Thin catalogue and match routes; all computations live in metrics."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from matchpulse.api import repository as repo
from matchpulse.api import schemas as s

router = APIRouter()


@router.get("/competitions", response_model=s.Competitions)
def competitions() -> dict:
    return {"competitions": repo.competitions()}


@router.get("/matches", response_model=s.Matches, response_model_exclude_unset=True)
def matches(competition: str | None = None) -> dict:
    return {"matches": repo.match_cards(competition)}


@router.get(
    "/matches/{match_id}",
    response_model=s.MatchDetail,
    response_model_exclude_unset=True,
)
def match(match_id: str) -> dict:
    return repo.bundle(match_id)["match"]


@router.get(
    "/matches/{match_id}/events",
    response_model=s.Events,
    response_model_exclude_unset=True,
)
def events(
    match_id: str,
    from_t: float | None = Query(None, alias="from", ge=0),
    to_t: float | None = Query(None, alias="to", ge=0),
) -> dict:
    if from_t is not None and to_t is not None and from_t > to_t:
        raise HTTPException(422, "from must be <= to (elapsed seconds)")
    rows = repo.bundle(match_id)["events"]
    if (from_t is not None or to_t is not None) and any(e["t"] is None for e in rows):
        raise HTTPException(
            422, "Elapsed-time filtering requires an observed precise clock"
        )
    return {
        "match_id": match_id,
        "events": [
            e
            for e in rows
            if (from_t is None or e["t"] >= from_t) and (to_t is None or e["t"] <= to_t)
        ],
    }


@router.get("/matches/{match_id}/timeline", response_model=s.Timeline)
def timeline(match_id: str) -> dict:
    return {"match_id": match_id, "minutes": repo.bundle(match_id)["minutes"]}


@router.get("/matches/{match_id}/sequences", response_model=s.Sequences)
def sequences(
    match_id: str,
    sort: Literal["danger", "time", "xg"] = "danger",
    limit: int = Query(5, ge=1, le=500),
) -> dict:
    rows = repo.bundle(match_id)["sequences"]
    if sort == "time":
        rows = sorted(rows, key=lambda x: x["start"]["t"])
    elif sort == "xg":
        rows = sorted(rows, key=lambda x: -x["xg"])
    return {"match_id": match_id, "sequences": rows[:limit]}


@router.get("/matches/{match_id}/players", response_model=s.Players)
def players(match_id: str) -> dict:
    return {"match_id": match_id, "players": repo.bundle(match_id)["players"]}


@router.get("/matches/{match_id}/turning-points", response_model=s.TurningPoints)
def turning_points(match_id: str) -> dict:
    return {
        "match_id": match_id,
        "turning_points": repo.bundle(match_id)["turning_points"],
    }
