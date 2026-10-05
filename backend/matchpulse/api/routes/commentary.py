"""Thin commentary route; window values are inclusive timeline bucket indices."""

from fastapi import APIRouter, HTTPException, Query

from matchpulse.analyst.commentary_store import get_commentary
from matchpulse.api.schemas import Commentary

router = APIRouter()


@router.get("/matches/{match_id}/commentary", response_model=Commentary)
def commentary(
    match_id: str,
    from_index: int | None = Query(None, alias="from", ge=0),
    to_index: int | None = Query(None, alias="to", ge=0),
) -> dict:
    if from_index is not None and to_index is not None and from_index > to_index:
        raise HTTPException(422, "from must be <= to (timeline bucket indices)")
    return get_commentary(match_id, from_index, to_index)
