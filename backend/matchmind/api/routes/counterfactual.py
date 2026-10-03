"""Thin counterfactual request boundary."""

from fastapi import APIRouter

from matchmind.api.counterfactual import run_counterfactual
from matchmind.api.schemas import Counterfactual, CounterfactualRequest

router = APIRouter()


@router.post("/matches/{match_id}/counterfactual", response_model=Counterfactual)
def counterfactual(match_id: str, request: CounterfactualRequest) -> dict:
    return run_counterfactual(match_id, request.event_id, request.change)
