"""Strict additive player endpoint contracts (golden examples live in tests)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Valuation(Contract):
    date: str
    value_eur: int
    club: str | None


class CompetitionCareer(Contract):
    competition: str
    season: str
    team: str
    matches: int
    minutes: float
    vaep_per90: float
    xg: float
    goals: int


class Career(Contract):
    matches: int
    minutes: float
    vaep: float
    vaep_per90: float
    vaep_off: float
    vaep_def: float
    xg: float
    goals: int
    shots: int
    prog_per90: float
    by_competition: list[CompetitionCareer]


class Heatmap(Contract):
    nx: Literal[12]
    ny: Literal[8]
    values: list[float] = Field(min_length=96, max_length=96)


class Moment(Contract):
    match_id: str
    match_label: str
    minute_label: str
    event_id: str
    sequence_id: str | None
    vaep: float
    text: str | None


class PlayerMatch(Contract):
    match_id: str
    date: str | None
    competition: str
    season: str
    team: str
    opponent: str
    minutes: float
    vaep: float
    xg: float
    goals: int
    in_db: bool


class InMatch(Contract):
    age: int | None
    market_value_eur: int | None
    minutes: float
    vaep: float
    rank_in_match: int


class Profile(Contract):
    player_id: int
    name: str
    short_name: str
    nickname: str | None
    photo_url: str | None
    photo_credit: str | None
    photo_license: str | None
    date_of_birth: str | None
    height_cm: int | None
    foot: str | None
    position: str | None
    nationality: str | None
    transfermarkt_id: int | None
    wikidata_id: str | None
    current_club: str | None
    market_value_eur: int | None
    peak_market_value_eur: int | None
    caps: int | None
    match_confidence: float
    valuations: list[Valuation]
    career: Career
    heatmap: Heatmap
    top_moments: list[Moment]
    matches: list[PlayerMatch]
    in_match: InMatch | None


class SearchResult(Contract):
    player_id: int
    name: str
    short_name: str
    nationality: str | None
    position: str | None
    photo_url: str | None
    teams: list[str]
    matches: int
    vaep_per90: float


class Search(Contract):
    results: list[SearchResult]


Metric = Literal["vaep_per90", "vaep", "xg", "prog_per90"]


class LeaderboardRow(Contract):
    player_id: int
    name: str
    short_name: str
    team: str
    competition: str
    season: str
    minutes: float
    value: float
    market_value_eur: int | None
    value_rank: float | None
    metric_rank: float
    underrated_score: float | None


class Leaderboard(Contract):
    metric: Metric
    rows: list[LeaderboardRow]
