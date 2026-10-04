import { create } from "zustand";
import { api } from "../api/client";
import type {
  CommentaryLine, MarketSeries, MatchDetail, MatchEvent, PlayerRow, Sequence, TimelineMinute, TurningPoint,
} from "../api/types";
import { clock, isShot } from "../lib/format";

export type RightTab = "analyst" | "sequences" | "players" | "whatif";

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

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  tools: string[];
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
  replay: { sequenceId: string; step: number; playing: boolean } | null;
  rightTab: RightTab;
  chat: ChatMessage[];
  commentary: CommentaryLine[];
  commentaryBySeq: Map<string, CommentaryLine>;
  pendingFocus: { seq?: string; ev?: string } | null;
  market: MarketSeries | null;

  load: (id: string) => Promise<void>;
  setWindow: (w: Window | null) => void;
  setFocus: (f: Focus) => void;
  focusEvent: (id: string) => void;
  focusSequence: (id: string) => void;
  focusTurningPoint: (id: string) => void;
  setHoverIndex: (i: number | null) => void;
  setRightTab: (t: RightTab) => void;
  startReplay: (sequenceId: string) => void;
  stepReplay: () => void;
  stopReplay: () => void;
  ask: (question: string) => Promise<void>;
  setPendingFocus: (f: { seq?: string; ev?: string } | null) => void;
}

export const bucketKey = (period: number, minute: number) => `${period}:${minute}`;

let askAbort: AbortController | null = null;

export const useMatch = create<State>((set, get) => ({
  matchId: null,
  status: "idle",
  error: null,
  data: null,
  window: null,
  focus: null,
  hoverIndex: null,
  replay: null,
  rightTab: "analyst",
  chat: [],
  commentary: [],
  commentaryBySeq: new Map(),
  pendingFocus: null,
  market: null,

  async load(id) {
    if (get().matchId === id && get().status !== "error") return;
    askAbort?.abort();
    set({ matchId: id, status: "loading", error: null, data: null, window: null, focus: null, replay: null, chat: [], commentary: [], commentaryBySeq: new Map(), market: null });
    try {
      const [match, events, timeline, sequences, players, turningPoints] = await Promise.all([
        api.match(id), api.events(id), api.timeline(id), api.sequences(id), api.players(id), api.turningPoints(id),
      ]);
      if (get().matchId !== id) return;
      const bucketOf = new Map(timeline.map((m) => [bucketKey(m.period, m.minute), m.index]));
      const eventById = new Map(events.map((e) => [e.id, e]));
      const eventsBySeq = new Map<string, MatchEvent[]>();
      for (const e of events) {
        const list = eventsBySeq.get(e.sequence_id);
        if (list) list.push(e);
        else eventsBySeq.set(e.sequence_id, [e]);
      }
      set({ status: "ready", data: { match, events, timeline, sequences, players, turningPoints, bucketOf, eventById, eventsBySeq, seqCache: new Map() } });
      const pf = get().pendingFocus;
      if (pf?.seq) get().focusSequence(pf.seq);
      else if (pf?.ev) get().focusEvent(pf.ev);
      set({ pendingFocus: null });
      api.market(id).then((m) => { if (get().matchId === id && m?.series.length) set({ market: m }); });
      // commentary is optional: load in the background, ignore failures
      api.commentary(id).then((lines) => {
        if (get().matchId === id) set({ commentary: lines, commentaryBySeq: new Map(lines.map((l) => [l.sequence_id, l])) });
      }).catch(() => {});
    } catch (e) {
      set({ status: "error", error: e instanceof Error ? e.message : String(e) });
    }
  },

  setWindow: (w) => set({ window: w, replay: null }),
  setFocus: (f) => set({ focus: f }),

  focusEvent(id) {
    const d = get().data;
    const ev = d?.eventById.get(id);
    if (!d || !ev) return;
    const i = d.bucketOf.get(bucketKey(ev.period, ev.minute)) ?? 0;
    set({ focus: { kind: "event", id }, window: { from: Math.max(0, i - 2), to: Math.min(d.timeline.length - 1, i + 1) }, replay: null });
  },

  focusSequence(id) {
    const d = get().data;
    const s = resolveSequence(d, id);
    if (!d || !s) return;
    const a = d.bucketOf.get(bucketKey(s.start.period, s.start.minute)) ?? 0;
    const b = d.bucketOf.get(bucketKey(s.end.period, s.end.minute)) ?? a;
    set({ focus: { kind: "sequence", id }, window: { from: a, to: b }, replay: null });
  },

  focusTurningPoint(id) {
    const tp = get().data?.turningPoints.find((x) => x.id === id);
    if (!tp) return;
    set({ focus: { kind: "turning", id }, window: { from: tp.start.index, to: tp.end.index }, replay: null });
  },

  setHoverIndex: (i) => set({ hoverIndex: i }),
  setPendingFocus: (f) => set({ pendingFocus: f }),
  setRightTab: (t) => set({ rightTab: t }),

  startReplay(sequenceId) {
    get().focusSequence(sequenceId);
    set({ replay: { sequenceId, step: 0, playing: true } });
  },
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
    const uid = crypto.randomUUID();
    const aid = crypto.randomUUID();
    set((s) => ({
      rightTab: "analyst",
      chat: [...s.chat, { id: uid, role: "user", content: question, tools: [], streaming: false },
        { id: aid, role: "assistant", content: "", tools: [], streaming: true }],
    }));
    const patch = (fn: (m: ChatMessage) => ChatMessage) =>
      set((s) => ({ chat: s.chat.map((m) => (m.id === aid ? fn(m) : m)) }));
    try {
      for await (const chunk of api.ask(id, question, history, signal)) {
        if (chunk.type === "text") patch((m) => ({ ...m, content: m.content + chunk.delta }));
        else if (chunk.type === "tool") patch((m) => ({ ...m, tools: [...m.tools, chunk.name] }));
        else if (chunk.type === "done") break;
      }
    } catch (e) {
      if (!signal.aborted) patch((m) => ({ ...m, content: m.content + `\n\n_Something went wrong: ${e instanceof Error ? e.message : e}_` }));
    } finally {
      patch((m) => ({ ...m, streaming: false }));
    }
  },
}));
