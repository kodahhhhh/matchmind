"""Thin search route; W8 can populate commentary without API changes."""

from fastapi import APIRouter, Query

from matchmind.api.schemas import Search
from matchmind.api.search import search_moments

router = APIRouter()


@router.get("/search", response_model=Search)
def search(
    q: str = Query(..., min_length=1, max_length=2000), match_id: str | None = None
) -> dict:
    return search_moments(q, match_id)
