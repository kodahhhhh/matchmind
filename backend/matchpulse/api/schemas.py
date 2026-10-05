"""Strict public API models matching fixtures and frontend/src/api/types.ts."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Side = Literal["home", "away"]
ActionType = Literal[
    "pass",
    "cross",
    "corner",
    "freekick",
    "throw_in",
    "goalkick",
    "kickoff",
    "carry",
    "take_on",
    "shot",
    "shot_penalty",
    "shot_freekick",
    "tackle",
    "interception",
    "clearance",
    "recovery",
    "block",
    "foul",
    "bad_touch",
    "dispossessed",
    "keeper_action",
]
Change = Literal["remove_goal", "no_sub", "remove_red_card"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Sides[T](Contract):
    home: T
    away: T


class Competition(Contract):
    id: str
    competition: str
    season: str
    country: str
    gender: str
    n_matches: int


class Competitions(Contract):
    competitions: list[Competition]


class TeamRef(Contract):
    id: int
    name: str
    short: str
    color: str


class MatchCard(Contract):
    match_id: str
    competition_key: str
    competition: str
    season: str
    stage: str | None
    match_date: str | None
    reconstructed: bool
    home: TeamRef
    away: TeamRef
    home_score: int
    away_score: int
    has_detail: bool


class Matches(Contract):
    matches: list[MatchCard]


class LineupPlayer(Contract):
    player_id: int
    name: str
    short_name: str
    jersey: int
    position: str | None
    starter: bool


class Marker(Contract):
    type: Literal["goal", "sub", "card"]
    event_id: str
    period: int
    minute: int
    second: int
    t: float
    team: Side
    player_id: int | None
    detail: str | None
    player_off_id: int | None = None


class Period(Contract):
    period: int
    start_index: int
    end_index: int
    start_t: float
    end_t: float


class Score(Contract):
    home: int
    away: int
    penalties: Sides[int] | None = None


class MatchDetail(Contract):
    match_id: str
    competition: str
    season: str
    stage: str | None
    match_date: str | None
    kick_off: str | None
    reconstructed: bool
    venue: str | None
    referee: str | None
    teams: Sides[TeamRef]
    score: Score
    periods: list[Period]
    duration_t: float
    lineups: Sides[list[LineupPlayer]]
    markers: list[Marker]


class MatchEvent(Contract):
    id: str
    period: int
    minute: int
    second: int
    t: float
    team: Side
    player_id: int | None
    player: str | None
    type: ActionType
    result: Literal["success", "fail", "goal", "offside"]
    bodypart: Literal["foot", "head", "other"] | None
    x: float | None
    y: float | None
    end_x: float | None
    end_y: float | None
    xg: float | None
    sb_xg: float | None
    vaep: float | None
    sequence_id: str
    under_pressure: bool


class Events(Contract):
    match_id: str
    events: list[MatchEvent]


class SideMinute(Contract):
    possession: float = Field(ge=0, le=1)
    field_tilt: float = Field(ge=0, le=1)
    xg: float
    xg_cum: float
    passes: int
    shots: int
    vaep: float


class TimelineMinute(Contract):
    index: int
    period: int
    minute: int
    label: str
    home: SideMinute
    away: SideMinute
    momentum: float


class Timeline(Contract):
    match_id: str
    minutes: list[TimelineMinute]


class SequenceStart(Contract):
    t: float
    period: int
    minute: int
    second: int
    label: str


class SequenceEnd(Contract):
    t: float
    period: int
    minute: int
    second: int


class Sequence(Contract):
    id: str
    team: Side
    start: SequenceStart
    end: SequenceEnd
    duration: float
    n_events: int
    event_ids: list[str]
    danger: float
    xg: float
    outcome: Literal["goal", "shot", "lost"]
    players: list[str]


class Sequences(Contract):
    match_id: str
    sequences: list[Sequence]


class Progression(Contract):
    passes: int
    carries: int
    distance: float


class Defending(Contract):
    tackle: int
    interception: int
    clearance: int
    recovery: int
    block: int


class PlayerRow(LineupPlayer):
    team: Side
    minutes: int
    vaep: float
    vaep_off: float
    vaep_def: float
    vaep_per90: float
    passes: int
    pass_pct: float | None
    progression: Progression
    defending: Defending
    shots: int
    xg: float


class Players(Contract):
    match_id: str
    players: list[PlayerRow]


class WindowSide(Contract):
    possession: float
    field_tilt: float
    xg: float
    shots: int


class WindowStats(Sides[WindowSide]):
    momentum: float


class TurningRef(Contract):
    index: int
    period: int
    minute: int
    label: str


class TurningPoint(Contract):
    id: str
    rank: int
    start: TurningRef
    end: TurningRef
    team_gaining: Side
    magnitude: float
    before: WindowStats
    after: WindowStats
    key_event_ids: list[str]


class TurningPoints(Contract):
    match_id: str
    turning_points: list[TurningPoint]


class Band(Contract):
    p10: float
    p50: float
    p90: float


class Anchor(Contract):
    period: int
    minute: int
    label: str


class Actual(Contract):
    xg: float
    possession: float
    goals: int


class Modelled(Contract):
    xg: Band
    possession: Band


class BranchPoint(Contract):
    offset_min: int
    actual: Sides[float]
    modelled: None


class AnalogOutcome(Contract):
    xg_for: float
    xg_against: float
    goals_for: int
    goals_against: int


class Analog(Contract):
    match_id: str
    competition: str
    season: str
    home: str
    away: str
    minute: int
    score_state: str
    similarity: float
    next15: AnalogOutcome


class CounterfactualRequest(Contract):
    event_id: str
    change: Change


class ModelCoverage(Contract):
    xg: float
    possession: float


class ForecastModel(Contract):
    name: str
    trained_matches: int
    coverage_p10_p90: ModelCoverage
    skill_vs_constant: ModelCoverage


class Effect(Contract):
    xg: float
    possession: float


class LineupPlayer(Contract):
    player_id: int
    name: str
    vaep_per90: float


class LineupChange(Contract):
    restored: LineupPlayer
    removed: LineupPlayer | None


class AnalogXg(Contract):
    xg: Band


class AnalogSummary(Contract):
    n: int
    home: AnalogXg
    away: AnalogXg


class ResultProbs(Contract):
    home: float
    level: float
    away: float


class Score(Contract):
    home: int
    away: int


class ScorePair(Contract):
    factual: Score
    modelled: Score


class ResultOutlook(Contract):
    block: Literal["normal_time", "extra_time"]
    level_means: Literal["draw", "extra_time", "penalties"]
    score: ScorePair
    factual: ResultProbs
    modelled: ResultProbs


class ChancePair(Contract):
    factual: Sides[float]
    modelled: Sides[float]


class Counterfactual(Contract):
    match_id: str
    event_id: str
    change: Change
    label: Literal["Modelled hypothetical"]
    horizon_minutes: Literal[15]
    method: Literal["trained_model", "analogs"]
    model: ForecastModel
    analog_summary: AnalogSummary
    anchor: Anchor
    actual: Sides[Actual]
    modelled: Sides[Modelled]
    factual: Sides[Modelled]
    effect: Sides[Effect]
    negligible: bool
    lineup_change: LineupChange | None
    result: ResultOutlook
    scoring_chance: ChancePair
    series: list[BranchPoint]
    analogs: list[Analog]
    n_analogs: int
    caveat: str


class ShotMoment(Contract):
    event_id: str
    team: Side
    player_id: int | None
    player: str
    period: int
    minute: int
    label: str
    x: float
    y: float
    xg: float
    outcome: str


class PassOption(Contract):
    player_id: int | None
    player: str
    x: float
    y: float
    p_complete: float
    xg_if_shot: float
    xt: float
    value: float


class PassModel(Contract):
    name: str
    trained_passes: int
    trained_matches: int
    auc: float
    brier: float
    baseline_auc: float


class ShotAlternatives(Contract):
    match_id: str
    event_id: str
    label: Literal["Modelled hypothetical"]
    shot: ShotMoment
    options: list[PassOption]
    comparison: Literal["pass_higher", "shot_higher", "similar", "no_teammates"]
    margin: float | None
    model: PassModel
    assumptions: list[str]
    caveat: str


class SearchMatch(Contract):
    home: str
    away: str
    competition: str
    season: str
    home_color: str
    away_color: str


class SearchResult(Contract):
    sequence_id: str
    match_id: str
    minute: int
    label: str
    team: Side
    text: str
    score: float
    match: SearchMatch


class Search(Contract):
    query: str
    results: list[SearchResult]


class CommentaryLine(Contract):
    sequence_id: str
    team: Side
    start: SequenceStart
    text: str
    danger: float
    outcome: Literal["goal", "shot", "lost"]


class Commentary(Contract):
    match_id: str
    lines: list[CommentaryLine]


class Message(Contract):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=16000)


class AskRequest(Contract):
    question: str = Field(min_length=1, max_length=4000)
    history: list[Message] = Field(default_factory=list, max_length=30)


class ToolChunk(Contract):
    type: Literal["tool"]
    name: str
    args: dict


class TextChunk(Contract):
    type: Literal["text"]
    delta: str


class CitationChunk(Contract):
    type: Literal["citation"]
    ref: str
    label: str


class ReasoningChunk(Contract):
    type: Literal["reasoning"]
    delta: str


class ToolResultChunk(Contract):
    type: Literal["tool_result"]
    name: str
    summary: str
    ok: bool


class DoneChunk(Contract):
    type: Literal["done"]


AskChunk = Annotated[
    ToolChunk
    | ToolResultChunk
    | ReasoningChunk
    | TextChunk
    | CitationChunk
    | DoneChunk,
    Field(discriminator="type"),
]
