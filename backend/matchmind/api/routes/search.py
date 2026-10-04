"""Thin search route; W8 can populate commentary without API changes."""

from fastapi import APIRouter, Query

from matchmind.api.routes.commentary import router as commentary_router
from matchmind.api.schemas import Search
from matchmind.api.search import search_moments

router = APIRouter()
router.include_router(commentary_router)


@router.get("/search", response_model=Search)
def search(
    q: str = Query(..., min_length=1, max_length=2000),
    match_id: str | None = None,
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    return search_moments(q, match_id, limit)
