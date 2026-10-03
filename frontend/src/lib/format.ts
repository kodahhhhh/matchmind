import type { ActionType, MatchEvent } from "../api/types";

const PERIOD_CAP: Record<number, number> = { 1: 45, 2: 90, 3: 105, 4: 120 };

/** Broadcast clock label: minute 79 (0-based) → 80', stoppage → 45+2'. */
export function clock(period: number, minute: number): string {
  const shown = minute + 1;
  const cap = PERIOD_CAP[period];
  return cap && shown > cap ? `${cap}+${shown - cap}'` : `${shown}'`;
}

export const pct = (v: number | null | undefined, digits = 0) =>
  v == null ? "–" : `${(v * 100).toFixed(digits)}%`;

export const xg = (v: number | null | undefined) => (v == null ? "–" : v.toFixed(2));

export const signed = (v: number, digits = 2) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(digits)}`;

const ACTION_LABEL: Partial<Record<ActionType, string>> = {
  pass: "pass", cross: "cross", corner: "corner", freekick: "free kick", throw_in: "throw-in",
  goalkick: "goal kick", kickoff: "kick-off", carry: "carry", take_on: "take-on",
  shot: "shot", shot_penalty: "penalty", shot_freekick: "free-kick shot", tackle: "tackle",
  interception: "interception", clearance: "clearance", recovery: "recovery", block: "block",
  foul: "foul", bad_touch: "heavy touch", dispossessed: "dispossessed", keeper_action: "keeper",
};

export function describe(e: MatchEvent): string {
  const what = e.result === "goal" ? (e.type === "shot_penalty" ? "penalty goal" : "goal") : ACTION_LABEL[e.type] ?? e.type;
  return `${clock(e.period, e.minute)} ${e.player ?? ""} ${what}`.replace(/\s+/g, " ").trim();
}

export const isShot = (t: ActionType) => t === "shot" || t === "shot_penalty" || t === "shot_freekick";
export const isMove = (t: ActionType) =>
  ["pass", "cross", "corner", "freekick", "throw_in", "goalkick", "kickoff"].includes(t);
export const isDefensive = (t: ActionType) =>
  ["tackle", "interception", "clearance", "recovery", "block"].includes(t);
