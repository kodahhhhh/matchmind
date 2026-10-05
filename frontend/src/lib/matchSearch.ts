import type { Competition, MatchCard } from "../api/types";

/** Lowercase, accents stripped: "Atlético" matches "atletico". */
export const fold = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

const FILLER = new Set(["v", "vs", "versus", "against", "and", "the", "match", "game", "of", "-", "x"]);
const ALIAS: Record<string, string> = {
  wc: "world cup", euros: "euro", cl: "champions league", ucl: "champions league",
  epl: "premier league", afcon: "african cup", mls: "major league soccer",
};

function tokens(q: string): string[] {
  let s = fold(q).trim();
  for (const [k, v] of Object.entries(ALIAS)) s = s.replace(new RegExp(`\\b${k}\\b`, "g"), v);
  return s.split(/[\s,/]+/).filter((t) => t && !FILLER.has(t));
}

const words = (s: string) => fold(s).split(/[\s\-./()]+/).filter(Boolean);

export interface MatchHit { m: MatchCard; score: number }

/** Matches by team, competition, season, year or stage. Every word must match something; team hits rank highest. */
export function searchMatches(all: MatchCard[], q: string, limit = 8): MatchHit[] {
  const ts = tokens(q);
  if (!ts.length) return [];
  const hits: MatchHit[] = [];
  for (const m of all) {
    const home = words(m.home.name), away = words(m.away.name);
    const comp = words(m.competition), stage = words(m.stage ?? "");
    const year = m.match_date?.slice(0, 4) ?? "";
    const season = fold(m.season);
    let score = 0;
    let teamsHit = 0;
    let ok = true;
    for (const t of ts) {
      const pre = (ws: string[]) => ws.some((w) => w.startsWith(t));
      if (pre(home) || pre(away)) { score += 10; teamsHit++; }
      else if (pre(comp)) score += 4;
      else if (pre(stage)) score += 3;
      else if (year === t || season.includes(t)) score += 3;
      else { ok = false; break; }
    }
    if (!ok) continue;
    if (teamsHit >= 2 && home.some((w) => ts.some((t) => w.startsWith(t))) && away.some((w) => ts.some((t) => w.startsWith(t)))) score += 8;
    if (m.stage === "Final") score += 2;
    // newer first among equals
    score += (Number(year) || 1950) / 10000;
    hits.push({ m, score });
  }
  return hits.sort((a, b) => b.score - a.score).slice(0, limit);
}

export interface CompHit { name: string; total: number; seasons: number }

/** Competitions whose name matches every word of the query. */
export function searchCompetitions(comps: Competition[], q: string, limit = 4): CompHit[] {
  const ts = tokens(q);
  if (!ts.length) return [];
  const by = new Map<string, CompHit>();
  for (const c of comps) {
    const ws = words(c.competition);
    if (!ts.every((t) => ws.some((w) => w.startsWith(t)))) continue;
    const h = by.get(c.competition) ?? { name: c.competition, total: 0, seasons: 0 };
    h.total += c.n_matches;
    h.seasons += 1;
    by.set(c.competition, h);
  }
  return [...by.values()].sort((a, b) => b.total - a.total).slice(0, limit);
}

/** Curated matches a fan would look for first, each with a one-line hook. */
export const FAMOUS: { id: string; hook: string }[] = [
  { id: "sb:3869685", hook: "Messi against Mbappé, settled on penalties" },
  { id: "sb:2302764", hook: "Liverpool come back from 3-0 down at half-time" },
  { id: "sb:3943043", hook: "Oyarzabal's late winner in Berlin" },
  { id: "sb:8658", hook: "A six-goal World Cup final in Moscow" },
  { id: "sb:3795506", hook: "Shaw scores early, Italy win on penalties" },
  { id: "sb:3943077", hook: "Lautaro wins it in extra time" },
  { id: "sb:18245", hook: "Bale's overhead kick in Kyiv" },
  { id: "sb:3888702", hook: "Pelé's Brazil at their best" },
];

export const matchPath = (id: string) => `/match/${encodeURIComponent(id)}`;

const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
export const matchDate = (m: { match_date: string | null; season: string }) => (m.match_date ? dateFmt.format(new Date(m.match_date)) : m.season);

/** "World Cup 2022", "Champions League 2004/05": the short label fans use. */
export function compLabel(competition: string, season: string): string {
  const name = competition.replace(/^FIFA /, "").replace(/^UEFA /, "").replace(/^1\. /, "");
  const s = /^\d{4}\/\d{4}$/.test(season) ? `${season.slice(0, 4)}/${season.slice(7)}` : season;
  return `${name} ${s}`;
}
