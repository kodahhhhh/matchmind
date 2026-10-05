import { create } from "zustand";
import { api } from "../api/client";
import type {
  CommentaryLine, MarketSeries, MatchDetail, MatchEvent, PlayerRow, Sequence, TimelineMinute, TurningPoint,
} from "../api/types";
import { clock, isShot } from "../lib/format";

export type RightTab = "story" | "ask" | "players" | "whatif";

/** Inclusive range of timeline bucket indices. */
export interface Window {
  from: number;
  to: number;
}

export type Focus =
  | { kind: "event"; id: string }
  | { kind: "sequence"; id: string }
  | { kind: "turning"; id: string }
  | null;

/** One tool call the analyst made: what it asked for and what came back (in plain English). */
export interface AgentStep {
  name: string;
  args: Record<string, unknown>;
  state: "running" | "done" | "error";
  summary?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  steps: AgentStep[];
  /** The model's own thinking summary, streamed before and between tool calls. */
  reasoning: string;
  /** Citation labels from the backend, keyed "ev:<id>" / "seq:<id>". */
  labels: Record<string, string>;
  streaming: boolean;
}

interface MatchData {
  match: MatchDetail;
  events: MatchEvent[];
  timeline: TimelineMinute[];
  sequences: Sequence[];
  players: PlayerRow[];
  turningPoints: TurningPoint[];
  /** "period:minute" → timeline index */
  bucketOf: Map<string, number>;
  eventById: Map<string, MatchEvent>;
  eventsBySeq: Map<string, MatchEvent[]>;
  seqCache: Map<string, Sequence>;
  /** Which sections loaded. "Lite" matches (no event stream) have only the match detail. */
  has: {
    /** A full event stream: pitch replay, every touch, What if. */
    events: boolean;
    /** At least a shot map (lite matches send shots only). */
    shots: boolean;
    timeline: boolean;
    /** Per-minute possession and territory (lite timelines carry only chances). */
    possession: boolean;
    momentum: boolean;
    sequences: boolean;
    players: boolean;
    turningPoints: boolean;
    lite: boolean;
  };
}

/** Top sequences come from the API; any other sequence is rebuilt from its events. */
export function resolveSequence(d: MatchData | null, id: string): Sequence | undefined {
  if (!d) return undefined;
  const top = d.sequences.find((s) => s.id === id);
  if (top) return top;
  const cached = d.seqCache.get(id);
  if (cached) return cached;
  const evs = d.eventsBySeq.get(id);
  if (!evs?.length) return undefined;
  // the possessing team starts the sequence; only override it when the other side clearly dominates
  const counts = { home: 0, away: 0 };
  for (const e of evs) counts[e.team]++;
  const starter = evs[0].team;
  const other = starter === "home" ? "away" : "home";
  const team = counts[other] > 2 * counts[starter] ? other : starter;
  const own = evs.filter((e) => e.team === team);
  const shots = own.filter((e) => isShot(e.type));
  const names: string[] = [];
  for (const e of own) if (e.player && names[names.length - 1] !== e.player) names.push(e.player);
  const first = evs[0];
  const last = evs[evs.length - 1];
  const seq: Sequence = {
    id, team,
    start: { t: first.t, period: first.period, minute: first.minute, second: first.second, label: clock(first.period, first.minute) },
    end: { t: last.t, period: last.period, minute: last.minute, second: last.second },
    duration: last.t - first.t, n_events: evs.length, event_ids: evs.map((e) => e.id),
    danger: own.reduce((a, e) => a + Math.max(e.vaep ?? 0, 0), 0),
    xg: shots.reduce((a, e) => a + (e.xg ?? 0), 0),
    outcome: shots.some((e) => e.result === "goal") ? "goal" : shots.length ? "shot" : "lost",
    players: names.slice(0, 8),
  };
  d.seqCache.set(id, seq);
  return seq;
}

interface State {
  matchId: string | null;
  status: "idle" | "loading" | "ready" | "error";
  error: string | null;
  data: MatchData | null;

  window: Window | null;
  focus: Focus;
  hoverIndex: number | null;
  replay: { sequenceId: string; step: number; playing: boolean; ms: number } | null;
  reel: { items: ReelItem[]; index: number } | null;
  rightTab: RightTab;
  chat: ChatMessage[];
  commentary: CommentaryLine[];
  commentaryBySeq: Map<string, CommentaryLine>;
  commentaryStatus: "loading" | "ready" | "none";
  pendingFocus: { seq?: string; ev?: string } | null;
  market: MarketSeries | null;
  /** A moment handed to the What if tab (from the moment card or the analyst). */
  whatIfPick: { eventId: string; n: number } | null;
  /** Bumped when the user picks a moment from a panel, so phones scroll the pitch into view. */
  pitchPing: number;
  /** Bumped when an action needs the side panel (asking, What if), so phones scroll down to it. */
  panelPing: number;

  load: (id: string) => Promise<void>;
  setWindow: (w: Window | null) => void;
  setFocus: (f: Focus) => void;
  focusEvent: (id: string) => void;
  focusSequence: (id: string) => void;
  focusTurningPoint: (id: string) => void;
  setHoverIndex: (i: number | null) => void;
  setRightTab: (t: RightTab) => void;
  startReplay: (sequenceId: string, opts?: { tail?: number; ms?: number }) => void;
  playHighlights: () => void;
  nextHighlight: () => void;
  stopHighlights: () => void;
  stepReplay: () => void;
  stopReplay: () => void;
  ask: (question: string) => Promise<void>;
  stopAsking: () => void;
  setPendingFocus: (f: { seq?: string; ev?: string } | null) => void;
  /** Focus a moment because the user asked to see it: also brings the pitch into view on phones. */
  showMoment: (ref: { ev?: string; seq?: string; replay?: boolean }) => void;
  openWhatIf: (eventId: string) => void;
  pingPitch: () => void;
  /** Ask the analyst from anywhere: switches to the Ask tab and sends. */
  askAbout: (question: string) => void;
}

export interface ReelItem {
  sequenceId: string;
  kind: "goal" | "chance";
  label: string;
  team: "home" | "away";
}

/** Goals plus the most dangerous non-goal moves, in match order. */
function buildReel(d: MatchData): ReelItem[] {
  const names = new Map([...d.match.lineups.home, ...d.match.lineups.away].map((p) => [p.player_id, p.short_name]));
  const items = new Map<string, ReelItem>();
  for (const m of d.match.markers) {
    if (m.type !== "goal") continue;
    const ev = d.eventById.get(m.event_id);
    if (!ev) continue;
    items.set(ev.sequence_id, {
      sequenceId: ev.sequence_id, kind: "goal", team: m.team,
      label: `${clock(m.period, m.minute)} ${names.get(m.player_id ?? -1) ?? "Goal"}${m.detail === "penalty" ? " (pen)" : ""}`,
    });
  }
  for (const s of [...d.sequences].sort((a, b) => b.danger - a.danger).slice(0, 4)) {
    if (!items.has(s.id) && s.outcome !== "goal") {
      items.set(s.id, { sequenceId: s.id, kind: "chance", team: s.team, label: `${s.start.label} ${s.players[s.players.length - 1] ?? ""} chance`.trim() });
    }
  }
  const t = (id: string) => resolveSequence(d, id)?.start.t ?? 0;
  return [...items.values()].sort((a, b) => t(a.sequenceId) - t(b.sequenceId));
}

export type { MatchData };

export const bucketKey = (period: number, minute: number) => `${period}:${minute}`;

let askAbort: AbortController | null = null;

/** crypto.randomUUID only exists on HTTPS/localhost; the app is also opened over plain HTTP (Tailscale IP). */
let idSeq = 0;
const newId = () => `m${Date.now().toString(36)}${(idSeq++).toString(36)}${Math.random().toString(36).slice(2, 8)}`;

export const useMatch = create<State>((set, get) => ({
  matchId: null,
  status: "idle",
  error: null,
  data: null,
  window: null,
  focus: null,
  hoverIndex: null,
  replay: null,
  reel: null,
  rightTab: "story",
  chat: [],
  commentary: [],
  commentaryBySeq: new Map(),
  commentaryStatus: "loading",
  pendingFocus: null,
  market: null,
  whatIfPick: null,
  pitchPing: 0,
  panelPing: 0,

  async load(id) {
    if (get().matchId === id && get().status !== "error") return;
    askAbort?.abort();
    set({ matchId: id, status: "loading", error: null, data: null, window: null, focus: null, replay: null, reel: null, chat: [], commentary: [], commentaryBySeq: new Map(), commentaryStatus: "loading", market: null, rightTab: "story", whatIfPick: null });
    try {
      // the match detail is required; every other section is optional and hides when it's missing
      const opt = <T,>(p: Promise<T[]>) => p.then((v) => ({ ok: true, v }), () => ({ ok: false, v: [] as T[] }));
      const [match, events, timeline, sequences, players, turningPoints] = await Promise.all([
        api.match(id), opt(api.events(id)), opt(api.timeline(id)), opt(api.sequences(id)), opt(api.players(id)), opt(api.turningPoints(id)),
      ]);
      if (get().matchId !== id) return;
      const bucketOf = new Map(timeline.v.map((m) => [bucketKey(m.period, m.minute), m.index]));
      const eventById = new Map(events.v.map((e) => [e.id, e]));
      const eventsBySeq = new Map<string, MatchEvent[]>();
      for (const e of events.v) {
        const list = eventsBySeq.get(e.sequence_id);
        if (list) list.push(e);
        else eventsBySeq.set(e.sequence_id, [e]);
      }
      const caps = match.capabilities ?? {};
      const lite = match.data_tier === "lite" || caps.full_events === false;
      // lite timelines may send nulls for series they can't measure: keep the numbers numeric, flag what's missing
      const num = (v: number | null | undefined) => (typeof v === "number" && Number.isFinite(v) ? v : 0);
      const known = (pick: (m: TimelineMinute) => unknown) => timeline.v.some((m) => typeof pick(m) === "number");
      const possession = known((m) => m.home.possession);
      const momentum = known((m) => m.momentum);
      for (const m of timeline.v) {
        m.momentum = num(m.momentum);
        for (const side of [m.home, m.away]) {
          side.possession = num(side.possession); side.field_tilt = num(side.field_tilt); side.xg = num(side.xg);
          side.xg_cum = num(side.xg_cum); side.shots = num(side.shots); side.passes = num(side.passes); side.vaep = num(side.vaep);
        }
      }
      const has = {
        events: events.v.length > 0 && !lite, shots: events.v.some((e) => isShot(e.type)),
        timeline: timeline.v.length > 0, possession, momentum,
        sequences: sequences.v.length > 0 && !lite, players: players.v.length > 0 && caps.vaep !== false,
        turningPoints: turningPoints.v.length > 0, lite,
      };
      set({
        status: "ready",
        data: { match, events: events.v, timeline: timeline.v, sequences: sequences.v, players: players.v, turningPoints: turningPoints.v, bucketOf, eventById, eventsBySeq, seqCache: new Map(), has },
      });
      const pf = get().pendingFocus;
      if (pf?.seq) get().focusSequence(pf.seq);
      else if (pf?.ev) get().focusEvent(pf.ev);
      set({ pendingFocus: null });
      api.market(id).then((m) => { if (get().matchId === id && m?.series.length) set({ market: m }); });
      // commentary is optional: load in the background, ignore failures
      api.commentary(id).then((lines) => {
        if (get().matchId === id) set({ commentary: lines, commentaryBySeq: new Map(lines.map((l) => [l.sequence_id, l])), commentaryStatus: lines.length ? "ready" : "none" });
      }).catch(() => { if (get().matchId === id) set({ commentaryStatus: "none" }); });
    } catch (e) {
      set({ status: "error", error: e instanceof Error ? e.message : String(e) });
    }
  },

  setWindow: (w) => set({ window: w, replay: null, reel: null }),
  setFocus: (f) => set({ focus: f }),

  focusEvent(id) {
    const d = get().data;
    const ev = d?.eventById.get(id);
    if (!d) return;
    if (!ev) {
      // substitutions and some cards aren't in the event stream: show the minutes around them instead
      const mk = d.match.markers.find((m) => m.event_id === id);
      const j = mk ? d.bucketOf.get(bucketKey(mk.period, mk.minute)) : undefined;
      if (j != null) set({ focus: null, window: { from: Math.max(0, j - 2), to: Math.min(d.timeline.length - 1, j + 2) }, replay: null });
      return;
    }
    const i = d.bucketOf.get(bucketKey(ev.period, ev.minute)) ?? 0;
    set({ focus: { kind: "event", id }, window: d.timeline.length ? { from: Math.max(0, i - 2), to: Math.min(d.timeline.length - 1, i + 1) } : null, replay: null });
  },

  focusSequence(id) {
    const d = get().data;
    const s = resolveSequence(d, id);
    if (!d || !s) return;
    const a = d.bucketOf.get(bucketKey(s.start.period, s.start.minute)) ?? 0;
    const b = d.bucketOf.get(bucketKey(s.end.period, s.end.minute)) ?? a;
    set({ focus: { kind: "sequence", id }, window: d.timeline.length ? { from: a, to: b } : null, replay: null });
  },

  focusTurningPoint(id) {
    const tp = get().data?.turningPoints.find((x) => x.id === id);
    if (!tp) return;
    set({ focus: { kind: "turning", id }, window: { from: tp.start.index, to: tp.end.index }, replay: null });
  },

  setHoverIndex: (i) => set({ hoverIndex: i }),
  setPendingFocus: (f) => set({ pendingFocus: f }),

  showMoment({ ev, seq, replay }) {
    set({ reel: null });
    if (seq && replay) get().startReplay(seq);
    else if (seq) get().focusSequence(seq);
    else if (ev) get().focusEvent(ev);
    set((s) => ({ pitchPing: s.pitchPing + 1 }));
  },
  pingPitch: () => set((s) => ({ pitchPing: s.pitchPing + 1 })),
  openWhatIf: (eventId) => set((s) => ({ rightTab: "whatif", whatIfPick: { eventId, n: (s.whatIfPick?.n ?? 0) + 1 }, panelPing: s.panelPing + 1 })),
  askAbout(question) {
    set((s) => ({ rightTab: "ask", panelPing: s.panelPing + 1 }));
    void get().ask(question);
  },
  setRightTab: (t) => set({ rightTab: t }),

  startReplay(sequenceId, opts) {
    const reel = get().reel;
    get().focusSequence(sequenceId);
    const n = resolveSequence(get().data, sequenceId)?.event_ids.length ?? 1;
    const step = opts?.tail ? Math.max(0, n - opts.tail) : 0;
    set({ replay: { sequenceId, step, playing: true, ms: opts?.ms ?? 700 }, reel });
  },

  playHighlights() {
    const d = get().data;
    if (!d) return;
    const items = buildReel(d);
    if (!items.length) return;
    set({ reel: { items, index: 0 }, rightTab: get().rightTab });
    get().startReplay(items[0].sequenceId, { tail: 10, ms: 520 });
  },
  nextHighlight() {
    const r = get().reel;
    if (!r) return;
    const index = r.index + 1;
    if (index >= r.items.length) {
      set({ reel: null, replay: null, focus: null, window: null });
      return;
    }
    set({ reel: { ...r, index } });
    get().startReplay(r.items[index].sequenceId, { tail: 10, ms: 520 });
  },
  stopHighlights: () => set({ reel: null, replay: null, focus: null, window: null }),
  stepReplay() {
    const r = get().replay;
    const s = r ? resolveSequence(get().data, r.sequenceId) : undefined;
    if (!r || !s) return;
    if (r.step >= s.event_ids.length - 1) set({ replay: { ...r, playing: false } });
    else set({ replay: { ...r, step: r.step + 1 } });
  },
  stopReplay: () => set({ replay: null }),

  async ask(question) {
    const id = get().matchId;
    if (!id) return;
    askAbort?.abort();
    askAbort = new AbortController();
    const signal = askAbort.signal;
    const history = get().chat.filter((m) => !m.streaming).map((m) => ({ role: m.role, content: m.content }));
    const uid = newId();
    const aid = newId();
    set((s) => ({
      rightTab: "ask",
      chat: [...s.chat, { id: uid, role: "user", content: question, steps: [], reasoning: "", labels: {}, streaming: false },
        { id: aid, role: "assistant", content: "", steps: [], reasoning: "", labels: {}, streaming: true }],
    }));
    const patch = (fn: (m: ChatMessage) => ChatMessage) =>
      set((s) => ({ chat: s.chat.map((m) => (m.id === aid ? fn(m) : m)) }));
    try {
      // follow the analyst: each newly completed citation jumps the pitch there (paced so it reads as narration)
      let text = "";
      let seen = 0;
      let lastJump = 0;
      const follow = () => {
        const refs = [...text.matchAll(/\[\[(ev|seq):([^\]]+)\]\]/g)];
        if (refs.length <= seen || Date.now() - lastJump < 1200) return;
        const [, kind, ref] = refs[refs.length - 1];
        seen = refs.length;
        lastJump = Date.now();
        if (get().reel || get().replay) return;
        if (kind === "ev") get().focusEvent(ref);
        else get().focusSequence(ref);
      };
      for await (const chunk of api.ask(id, question, history, signal)) {
        if (chunk.type === "text") {
          text += chunk.delta;
          patch((m) => ({ ...m, content: m.content + chunk.delta }));
          follow();
        }
        else if (chunk.type === "tool") patch((m) => ({ ...m, steps: [...m.steps, { name: chunk.name, args: chunk.args, state: "running" }] }));
        else if (chunk.type === "tool_result") {
          patch((m) => {
            const i = m.steps.findLastIndex((st) => st.name === chunk.name && st.state === "running");
            if (i < 0) return m;
            const steps = [...m.steps];
            steps[i] = { ...steps[i], state: chunk.ok ? "done" : "error", summary: chunk.summary };
            return { ...m, steps };
          });
        }
        else if (chunk.type === "reasoning") patch((m) => ({ ...m, reasoning: m.reasoning + chunk.delta }));
        else if (chunk.type === "citation") patch((m) => ({ ...m, labels: { ...m.labels, [chunk.ref]: chunk.label } }));
        else if (chunk.type === "done") break;
      }
    } catch {
      if (!signal.aborted) patch((m) => ({ ...m, content: m.content + "\n\n_Unable to finish the answer. Check your connection and ask again._" }));
    } finally {
      patch((m) => ({ ...m, streaming: false, steps: m.steps.map((st) => (st.state === "running" ? { ...st, state: "done" } : st)) }));
    }
  },
  stopAsking: () => askAbort?.abort(),
}));
