// Plain-language story of a match, computed from the data (never generated): the verdict, the key moments,
// and what any single moment was. Everything here is deterministic so the numbers always come from the API.
import type { Marker, MatchEvent, Sequence, Side } from "../api/types";
import { resolveSequence, type MatchData } from "../store/match";
import { clock, isShot, pct } from "./format";

const other = (s: Side): Side => (s === "home" ? "away" : "home");
const isRed = (m: Marker) => m.type === "card" && m.detail !== "yellow";

export function playerNames(d: MatchData): Map<number, string> {
  return new Map([...d.match.lineups.home, ...d.match.lineups.away].map((p) => [p.player_id, p.short_name]));
}

export interface Verdict { headline: string; lead: string | null; notes: string[] }

/** One headline sentence about the result, one about whether the chances back it up, then a note or two. */
export function matchVerdict(d: MatchData): Verdict {
  const { teams, score, periods, markers } = d.match;
  const name = (s: Side) => teams[s].name;
  const h = score.home, a = score.away;
  const pens = score.penalties;
  const extra = periods.some((p) => p.period >= 3);
  const winner: Side | null = h > a ? "home" : a > h ? "away" : pens ? (pens.home > pens.away ? "home" : "away") : null;

  let headline: string;
  if (pens && winner) headline = `${name(winner)} won on penalties after a ${h}-${a} draw.`;
  else if (winner) {
    const [w, l] = winner === "home" ? [h, a] : [a, h];
    headline = `${name(winner)} beat ${name(other(winner))} ${w}-${l}${extra ? " after extra time" : ""}.`;
  } else headline = h === 0 ? `A goalless draw between ${name("home")} and ${name("away")}.` : `${name("home")} and ${name("away")} drew ${h}-${a}.`;

  // comebacks: the biggest deficit each side overturned, from the goal markers in order
  let run = { home: 0, away: 0 };
  const worst: Record<Side, { gap: number; own: number; opp: number }> = { home: { gap: 0, own: 0, opp: 0 }, away: { gap: 0, own: 0, opp: 0 } };
  for (const m of [...markers].filter((k) => k.type === "goal" && k.period < 5).sort((x, y) => x.period - y.period || x.t - y.t)) {
    run = { ...run, [m.team]: run[m.team] + 1 };
    for (const side of ["home", "away"] as Side[]) {
      const gap = run[other(side)] - run[side];
      if (gap > worst[side].gap) worst[side] = { gap, own: run[side], opp: run[other(side)] };
    }
  }
  const comeback = (["home", "away"] as Side[]).find((side) => worst[side].gap >= 2);
  const notes: string[] = [];
  if (comeback) {
    const w = worst[comeback];
    const from = `${name(comeback)} came back from ${w.opp}-${w.own} down`;
    if (winner === comeback) headline = `${from} to win${pens ? " on penalties" : extra ? " after extra time" : ""}.`;
    else if (!winner) headline = `${from} to draw ${h}-${a}.`;
    else notes.push(`${from}, but ${pens ? "lost on penalties" : "still lost"}.`);
    if (pens && winner === comeback) notes.push(`It finished ${h}-${a} before the shoot-out.`);
  }

  let lead: string | null = null;
  const tl = d.timeline;
  if (tl.length) {
    const last = tl[tl.length - 1];
    const xg = { home: last.home.xg_cum, away: last.away.xg_cum };
    const better: Side = xg.home >= xg.away ? "home" : "away";
    const gap = Math.abs(xg.home - xg.away);
    const decidedInPlay = h !== a;
    if (gap < 0.3) lead = "Both sides made chances of about the same quality.";
    else if (decidedInPlay && winner === better) lead = `${name(better)} made the better chances, so the result was no fluke.`;
    else if (decidedInPlay && winner) lead = `${name(better)} made the better chances, but ${name(winner)} took theirs.`;
    else lead = `${name(better)} made the better chances but couldn't find a winner.`;

    const tilt = (s: Side) => !d.has.possession ? 0 : tl.reduce((sum, m) => sum + m[s].field_tilt, 0) / tl.length;
    const top: Side = tilt("home") >= tilt("away") ? "home" : "away";
    if (tilt(top) >= 0.6) notes.push(`${name(top)} spent most of the match in their opponent's half.`);
  }
  const tp = [...d.turningPoints].sort((x, y) => x.rank - y.rank)[0];
  if (tp) notes.push(`The biggest swing came from ${tp.start.label} to ${tp.end.label}, when ${name(tp.team_gaining)} took control.`);
  const names = playerNames(d);
  for (const r of markers.filter(isRed).slice(0, 2)) notes.push(`${names.get(r.player_id ?? -1) ?? "A player"} was sent off at ${clock(r.period, r.minute)}, leaving ${name(r.team)} with ten.`);
  return { headline, lead, notes };
}

export type MomentKind = "goal" | "red" | "swing" | "chance";

export interface KeyMoment {
  key: string;
  kind: MomentKind;
  order: number;
  clock: string;
  team: Side;
  title: string;
  sub: string | null;
  ev?: string;
  seq?: string;
  tp?: string;
  /** Score after a goal, "2-1". */
  score?: string;
}

/** Goals, red cards, the biggest swing and the best chances that didn't go in, in match order. */
export function keyMoments(d: MatchData): KeyMoment[] {
  const names = playerNames(d);
  const out: KeyMoment[] = [];
  let h = 0, a = 0;
  const ordered = [...d.match.markers].sort((x, y) => x.period - y.period || x.t - y.t);
  for (const m of ordered) {
    if (m.type === "goal" && m.period < 5) {
      if (m.team === "home") h++; else a++;
      const who = names.get(m.player_id ?? -1) ?? "Unknown";
      const ev = d.eventById.get(m.event_id);
      out.push({
        key: m.event_id, kind: "goal", order: m.period * 1000 + m.minute + m.second / 60, clock: clock(m.period, m.minute), team: m.team,
        title: m.detail === "own_goal" ? `Own goal, ${d.match.teams[m.team].name} score` : m.detail === "penalty" ? `${who} scores a penalty` : `${who} scores`,
        sub: null, ev: m.event_id, seq: ev?.sequence_id, score: `${h}-${a}`,
      });
    } else if (isRed(m)) {
      out.push({
        key: m.event_id + "r", kind: "red", order: m.period * 1000 + m.minute + m.second / 60, clock: clock(m.period, m.minute), team: m.team,
        title: `${names.get(m.player_id ?? -1) ?? "A player"} is sent off`, sub: null, ev: m.event_id,
      });
    }
  }
  const tp = [...d.turningPoints].sort((x, y) => x.rank - y.rank)[0];
  if (tp) {
    out.push({
      key: tp.id, kind: "swing", order: tp.start.period * 1000 + tp.start.minute, clock: tp.start.label, team: tp.team_gaining,
      title: `${d.match.teams[tp.team_gaining].name} take control`, sub: `The biggest swing of the match, from ${tp.start.label} to ${tp.end.label}.`, tp: tp.id,
    });
  }
  const chances = d.sequences.filter((s) => s.outcome === "shot" && s.xg >= 0.12).sort((x, y) => y.xg - x.xg).slice(0, 3);
  for (const s of chances) {
    const shot = lastShot(d, s);
    const who = shot?.player ?? s.players[s.players.length - 1] ?? d.match.teams[s.team].name;
    out.push({
      key: s.id, kind: "chance", order: s.start.period * 1000 + s.start.minute + (s.start.second ?? 0) / 60, clock: s.start.label, team: s.team,
      title: `Big chance for ${who}`, sub: `${pct(Math.min(s.xg, 0.99))} chance of scoring, no goal.`, seq: s.id, ev: shot?.id,
    });
  }
  return out.sort((x, y) => x.order - y.order);
}

function lastShot(d: MatchData, s: Sequence): MatchEvent | undefined {
  return s.event_ids.map((id) => d.eventById.get(id)).filter((e): e is MatchEvent => !!e && isShot(e.type) && e.team === s.team).pop();
}

const WHAT: Partial<Record<MatchEvent["type"], string>> = {
  pass: "plays a pass", cross: "crosses", corner: "takes a corner", freekick: "takes a free kick", throw_in: "takes a throw-in",
  goalkick: "takes a goal kick", kickoff: "kicks off", carry: "runs with the ball", take_on: "takes on a defender",
  tackle: "makes a tackle", interception: "intercepts", clearance: "clears", recovery: "wins the ball back", block: "blocks",
  foul: "commits a foul", bad_touch: "takes a heavy touch", dispossessed: "loses the ball", keeper_action: "makes a save",
};

export interface MomentInfo {
  team: Side;
  clock: string;
  title: string;
  sub: string | null;
  /** Chance of scoring, for shots and attacks that ended in one. */
  chance: number | null;
  seq: string | null;
  /** The event the What if tab can model, if any (goal, sub, red card, or an open-play shot). */
  whatIf: string | null;
  whatIfLabel: string | null;
  question: string;
}

/** Everything the moment card says about the focused event or attack. */
export function momentInfo(d: MatchData, ref: { ev?: string; seq?: string }, commentary?: (seq: string) => string | undefined): MomentInfo | null {
  const teamName = (s: Side) => d.match.teams[s].name;
  const whatIfFor = (e: MatchEvent | undefined): [string | null, string | null] => {
    if (!e) return [null, null];
    const mk = d.match.markers.find((m) => m.event_id === e.id && (m.type === "goal" || isRed(m)));
    if (mk) return [e.id, mk.type === "goal" ? "What if it didn't count?" : "What if they stayed on?"];
    if (e.type === "shot") return [e.id, "Should they have passed?"];
    return [null, null];
  };
  if (ref.ev) {
    const e = d.eventById.get(ref.ev);
    if (!e) return null;
    const goal = e.result === "goal" && isShot(e.type);
    const who = e.player ?? teamName(e.team);
    const title = goal ? `${who} scores${e.type === "shot_penalty" ? " a penalty" : ""}`
      : isShot(e.type) ? `${who} shoots${e.type === "shot_penalty" ? " from the spot" : ""}, no goal`
      : `${who} ${WHAT[e.type] ?? e.type.replace(/_/g, " ")}`;
    const [whatIf, whatIfLabel] = whatIfFor(e);
    return {
      team: e.team, clock: clock(e.period, e.minute), title, sub: commentary?.(e.sequence_id) ?? null,
      chance: isShot(e.type) && e.xg != null ? e.xg : null, seq: d.eventsBySeq.has(e.sequence_id) ? e.sequence_id : null,
      whatIf, whatIfLabel, question: `Tell me about ${who}'s ${goal ? "goal" : isShot(e.type) ? "shot" : "moment"} at ${clock(e.period, e.minute)}. Why did it matter?`,
    };
  }
  if (ref.seq) {
    const s = resolveSequence(d, ref.seq);
    if (!s) return null;
    const shot = lastShot(d, s);
    const [whatIf, whatIfLabel] = whatIfFor(shot);
    const pen = shot?.type === "shot_penalty";
    const title = shot?.player && s.outcome === "goal" ? `${shot.player} scores${pen ? " a penalty" : ""}`
      : shot?.player && s.outcome === "shot" ? `${shot.player} shoots${pen ? " from the spot" : ""}, no goal`
      : `${teamName(s.team)} attack ${s.outcome === "goal" ? "ends in a goal" : s.outcome === "shot" ? "ends in a shot" : "breaks down"}`;
    return {
      team: s.team, clock: s.start.label, title,
      sub: commentary?.(s.id) ?? (s.players.length ? s.players.slice(0, 5).join(", then ") : null),
      chance: s.xg > 0 ? Math.min(s.xg, 0.99) : null, seq: s.id, whatIf, whatIfLabel,
      question: `Talk me through the ${teamName(s.team)} attack at ${s.start.label}${shot?.player ? ` that ended with ${shot.player}` : ""}.`,
    };
  }
  return null;
}
