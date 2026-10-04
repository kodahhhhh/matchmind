"""Serve immutable W10 artifacts. No model fitting or source requests at runtime.

Orchestrator: import router and app.include_router(router, prefix='/api').
For isolated integration testing: uvicorn matchmind.api.routes.backtest:app --port 8030.
"""

import json
import re

from fastapi import APIRouter, FastAPI, HTTPException

from matchmind.backtest.contracts import Backtest, Market
from matchmind.config import get_settings

router = APIRouter()


def artifact(filename: str) -> dict:
    directory = get_settings().data_dir / "processed/backtest"
    candidate = directory / "w12" / filename
    path = candidate if candidate.is_file() else directory / filename
    if not path.is_file():
        raise HTTPException(404, "Backtest artifact is not available")
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "Backtest artifact cannot be read") from exc


@router.get("/backtest", response_model=Backtest, response_model_exclude_unset=True)
def backtest() -> dict:
    return artifact("backtest.json")


@router.get(
    "/matches/{match_id}/market",
    response_model=Market,
    response_model_exclude_unset=True,
)
def market(match_id: str) -> dict:
    if not re.fullmatch(r"sb:\d+", match_id):
        raise HTTPException(404, "Market not found")
    return artifact(f"market_{match_id.replace(':', '_')}.json")


# Dedicated W10 app; shared main.py and the running :8000 process are untouched.
app = FastAPI(title="MatchMind W10 backtest")
app.include_router(router, prefix="/api")
