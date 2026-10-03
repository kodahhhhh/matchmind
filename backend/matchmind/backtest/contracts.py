"""W10 response models, local to this workstream until orchestrator integration."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Bet(StrictModel):
    match_id: str
    label: str
    outcome: Literal["home", "draw", "away"]
    side: Literal["YES", "NO"]
    price_or_odds: float = Field(gt=0)
    model_prob: float = Field(ge=0, le=1)
    market_prob: float = Field(ge=0, le=1)
    stake: float = Field(gt=0)
    pnl: float
    minute: int | None = None
    clv: float | None = None


class Equity(StrictModel):
    i: int
    label: str
    bankroll: float


class Source(StrictModel):
    name: str
    matches: int
    notes: str


class Strategy(StrictModel):
    id: str
    name: str
    market: Literal["pinnacle", "polymarket"]
    description: str
    eval_period: str
    n_matches: int
    n_bets: int
    staked: float
    pnl: float
    roi: float
    roi_ci95: tuple[float, float]
    hit_rate: float
    max_drawdown: float
    clv: float | None = None
    brier_model: float | None
    brier_market: float | None
    equity: list[Equity]
    bets: list[Bet]


class Backtest(StrictModel):
    generated_at: str
    sources: list[Source]
    strategies: list[Strategy]
    caveats: list[str]


class Probabilities(StrictModel):
    home: float = Field(ge=0, le=1)
    draw: float = Field(ge=0, le=1)
    away: float = Field(ge=0, le=1)


class Minute(StrictModel):
    index: int
    label: str
    minute: int
    period: int
    market: Probabilities
    model: Probabilities


class Market(StrictModel):
    match_id: str
    source: Literal["polymarket"]
    market_url: str | None = None
    volume: float | None = None
    aligned: bool
    offset_seconds: float | None = None
    series: list[Minute]
    bets: list[Bet]
