// Mirrors fixtures/ exactly (fixtures are the API contract, see AGENTS.md).

export type Side = "home" | "away";

export interface Competition {
  id: string;
  competition: string;
  season: string;
  country: string;
  gender: string;
  n_matches: number;
}

export interface TeamRef {
  id: number;
  name: string;
  short: string;
  color: string;
}

export interface MatchCard {
  match_id: string;
  competition_key: string;
  competition: string;
  season: string;
  stage: string | null;
  match_date: string | null;
  reconstructed: boolean;
  home: TeamRef;
  away: TeamRef;
  home_score: number;
  away_score: number;
  has_detail: boolean;
}

export interface LineupPlayer {
  player_id: number;
  name: string;
  short_name: string;
  jersey: number;
  position: string | null;
  starter: boolean;
}

export type MarkerType = "goal" | "sub" | "card";

export interface Marker {
  type: MarkerType;
  event_id: string;
  period: number;
  minute: number;
  second: number;
  t: number;
  team: Side;
  player_id: number | null;
  player_off_id?: number;
  detail: string | null;
}

export interface Period {
  period: number;
  start_index: number;
  end_index: number;
  start_t: number;
  end_t: number;
}

export interface MatchDetail {
  match_id: string;
  competition: string;
  season: string;
  stage: string | null;
  match_date: string | null;
  kick_off: string | null;
  reconstructed: boolean;
  venue: string | null;
  referee: string | null;
  teams: Record<Side, TeamRef>;
  score: { home: number; away: number; penalties?: { home: number; away: number } };
  periods: Period[];
  duration_t: number;
  lineups: Record<Side, LineupPlayer[]>;
  markers: Marker[];
}

export type ActionType =
  | "pass" | "cross" | "corner" | "freekick" | "throw_in" | "goalkick" | "kickoff"
  | "carry" | "take_on" | "shot" | "shot_penalty" | "shot_freekick"
  | "tackle" | "interception" | "clearance" | "recovery" | "block"
  | "foul" | "bad_touch" | "dispossessed" | "keeper_action";

export interface MatchEvent {
  id: string;
  period: number;
  minute: number;
  second: number;
  t: number;
  team: Side;
  player_id: number | null;
  player: string | null;
  type: ActionType;
  result: "success" | "fail" | "goal" | "offside";
  bodypart: "foot" | "head" | "other" | null;
  x: number | null;
  y: number | null;
  end_x: number | null;
  end_y: number | null;
  xg: number | null;
  sb_xg: number | null;
  vaep: number | null;
  sequence_id: string;
  under_pressure: boolean;
}

export interface SideMinute {
  possession: number;
  field_tilt: number;
  xg: number;
  xg_cum: number;
  passes: number;
  shots: number;
  vaep: number;
}

export interface TimelineMinute {
  index: number;
  period: number;
  minute: number;
  label: string;
  home: SideMinute;
  away: SideMinute;
  momentum: number;
}

export interface ClockRef {
  index?: number;
  t?: number;
  period: number;
  minute: number;
  second?: number;
  label?: string;
}

export interface Sequence {
  id: string;
  team: Side;
  start: ClockRef & { t: number; label: string };
  end: ClockRef & { t: number };
  duration: number;
  n_events: number;
  event_ids: string[];
  danger: number;
  xg: number;
  outcome: "goal" | "shot" | "lost";
  players: string[];
}

export interface PlayerRow {
  player_id: number;
  name: string;
  short_name: string;
  jersey: number;
  team: Side;
  position: string | null;
  starter: boolean;
  minutes: number;
  vaep: number;
  vaep_off: number;
  vaep_def: number;
  vaep_per90: number;
  passes: number;
  pass_pct: number | null;
  progression: { passes: number; carries: number; distance: number };
  defending: Record<"tackle" | "interception" | "clearance" | "recovery" | "block", number>;
  shots: number;
  xg: number;
}

export interface WindowStats {
  home: { possession: number; field_tilt: number; xg: number; shots: number };
  away: { possession: number; field_tilt: number; xg: number; shots: number };
  momentum: number;
}

export interface TurningPoint {
  id: string;
  rank: number;
  start: ClockRef & { index: number; label: string };
  end: ClockRef & { index: number; label: string };
  team_gaining: Side;
  magnitude: number;
  before: WindowStats;
  after: WindowStats;
  key_event_ids: string[];
}

export interface Band {
  p10: number;
  p50: number;
  p90: number;
}

export interface Counterfactual {
  match_id: string;
  event_id: string;
  change: "remove_goal" | "no_sub" | "remove_red_card";
  label: string;
  horizon_minutes: number;
  anchor: ClockRef & { label: string };
  actual: Record<Side, { xg: number; possession: number; goals: number }>;
  modelled: Record<Side, { xg: Band; possession: Band }>;
  series: { offset_min: number; actual: Record<Side, number>; modelled: Record<Side, Band> }[];
  analogs: {
    match_id: string;
    competition: string;
    season: string;
    home: string;
    away: string;
    minute: number;
    score_state: string;
    similarity: number;
    next15: { xg_for: number; xg_against: number; goals_for: number; goals_against: number };
  }[];
  n_analogs: number;
  caveat: string;
}

export interface SearchResult {
  sequence_id: string;
  match_id: string;
  minute: number;
  label: string;
  team: Side;
  text: string;
  score: number;
}

export type AskChunk =
  | { type: "tool"; name: string; args: Record<string, unknown> }
  | { type: "text"; delta: string }
  | { type: "citation"; ref: string; label: string }
  | { type: "done" };
