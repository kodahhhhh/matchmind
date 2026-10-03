// The only place the frontend talks to the backend. VITE_USE_FIXTURES=1 serves fixtures/ instead.
import type {
  AskChunk, Competition, Counterfactual, MatchCard, MatchDetail, MatchEvent,
  PlayerRow, SearchResult, Sequence, TimelineMinute, TurningPoint,
} from "./types";

const USE_FIXTURES = import.meta.env.VITE_USE_FIXTURES === "1";

const fixtureDir = (matchId: string) => `/fixtures/matches/${matchId.replace(":", "_")}`;

async function get<T>(apiPath: string, fixturePath: string): Promise<T> {
  const res = await fetch(USE_FIXTURES ? fixturePath : `/api${apiPath}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${apiPath}`);
  return res.json() as Promise<T>;
}

const enc = encodeURIComponent;

export const api = {
  competitions: () =>
    get<{ competitions: Competition[] }>("/competitions", "/fixtures/competitions.json").then((r) => r.competitions),

  matches: () => get<{ matches: MatchCard[] }>("/matches", "/fixtures/matches.json").then((r) => r.matches),

  match: (id: string) => get<MatchDetail>(`/matches/${enc(id)}`, `${fixtureDir(id)}/match.json`),

  events: (id: string) =>
    get<{ events: MatchEvent[] }>(`/matches/${enc(id)}/events`, `${fixtureDir(id)}/events.json`).then((r) => r.events),

  timeline: (id: string) =>
    get<{ minutes: TimelineMinute[] }>(`/matches/${enc(id)}/timeline`, `${fixtureDir(id)}/timeline.json`).then((r) => r.minutes),

  sequences: (id: string) =>
    get<{ sequences: Sequence[] }>(`/matches/${enc(id)}/sequences?sort=danger&limit=5`, `${fixtureDir(id)}/sequences.json`).then((r) => r.sequences),

  players: (id: string) =>
    get<{ players: PlayerRow[] }>(`/matches/${enc(id)}/players`, `${fixtureDir(id)}/players.json`).then((r) => r.players),

  turningPoints: (id: string) =>
    get<{ turning_points: TurningPoint[] }>(`/matches/${enc(id)}/turning-points`, `${fixtureDir(id)}/turning-points.json`).then((r) => r.turning_points),

  async counterfactual(id: string, eventId: string, change: Counterfactual["change"]): Promise<Counterfactual> {
    if (USE_FIXTURES) return get<Counterfactual>("", `${fixtureDir(id)}/counterfactual.json`);
    const res = await fetch(`/api/matches/${enc(id)}/counterfactual`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_id: eventId, change }),
    });
    if (!res.ok) throw new Error(`${res.status}: counterfactual`);
    return res.json();
  },

  search: (q: string, matchId?: string) =>
    get<{ results: SearchResult[] }>(
      `/search?q=${enc(q)}${matchId ? `&match_id=${enc(matchId)}` : ""}`,
      `${fixtureDir(matchId ?? "sb:3869685")}/search.json`,
    ).then((r) => r.results),

  /** Streams the analyst's answer. Fixture mode replays a recorded transcript with realistic pacing. */
  async *ask(id: string, question: string, history: { role: "user" | "assistant"; content: string }[], signal?: AbortSignal): AsyncGenerator<AskChunk> {
    if (USE_FIXTURES) {
      const { stream } = await get<{ stream: AskChunk[] }>("", `${fixtureDir(id)}/ask.json`);
      for (const chunk of stream) {
        if (signal?.aborted) return;
        await new Promise((r) => setTimeout(r, chunk.type === "tool" ? 450 : chunk.type === "text" ? 28 : 60));
        yield chunk;
      }
      return;
    }
    const res = await fetch(`/api/matches/${enc(id)}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ question, history }),
      signal,
    });
    if (!res.ok || !res.body) throw new Error(`${res.status}: ask`);
    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += value;
      let i: number;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const frame = buf.slice(0, i);
        buf = buf.slice(i + 2);
        const data = frame.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).join("");
        if (data) yield JSON.parse(data) as AskChunk;
      }
    }
  },
};
