"""Thin counterfactual request boundary."""

from fastapi import APIRouter

from matchpulse.api.counterfactual import run_counterfactual
from matchpulse.api.schemas import (
    Counterfactual,
    CounterfactualRequest,
    ShotAlternatives,
)
from matchpulse.api.shot_alternatives import shot_alternatives

router = APIRouter()


@router.post("/matches/{match_id}/counterfactual", response_model=Counterfactual)
def counterfactual(match_id: str, request: CounterfactualRequest) -> dict:
    return run_counterfactual(match_id, request.event_id, request.change)


@router.get(
    "/matches/{match_id}/shots/{event_id}/alternatives",
    response_model=ShotAlternatives,
)
def alternatives(match_id: str, event_id: str) -> dict:
    return shot_alternatives(match_id, event_id)
