"""Thin player routes; negative identifiers address Transfermarkt-only profiles."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException, Query

from matchmind.players import schemas, service


@asynccontextmanager
async def player_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Warm artifacts/search before accepting requests in every consuming app."""
    service.search_index()
    service.search_postings()
    yield


router = APIRouter(lifespan=player_lifespan)


@router.get("/players", response_model=schemas.Search)
def search(
    q: str = Query("", max_length=200), limit: int = Query(20, ge=1, le=100)
) -> dict:
    return service.search_players(q, limit)


# Static routes must precede the integer player identifier route.
@router.get("/players/leaderboard", response_model=schemas.Leaderboard)
def leaderboard(
    metric: schemas.Metric = "vaep_per90",
    min_minutes: float = Query(900, ge=0),
    competition: str | None = None,
    season: str | None = None,
    limit: int = Query(50, ge=1, le=100),
) -> dict:
    return service.leaderboard(metric, min_minutes, competition, season, limit)


@router.get("/players/{sb_player_id}", response_model=schemas.Profile)
def profile(sb_player_id: int, match_id: str | None = None) -> dict:
    try:
        return service.get_player_profile(sb_player_id, match_id)
    except service.PlayerNotFound as exc:
        raise HTTPException(404, str(exc)) from exc


def create_player_app() -> FastAPI:
    """Isolated verification app; shared :8000 process is never modified/restarted."""
    app = FastAPI(title="MatchMind player API")
    app.include_router(router, prefix="/api")
    return app
