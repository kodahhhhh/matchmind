import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { motion } from "motion/react";
import { CaretDown } from "@phosphor-icons/react";
import type { Competition, MatchCard } from "../../api/types";
import { useCatalogue } from "../../store/catalogue";
import { matchDate, matchPath } from "../../lib/matchSearch";

const PAGE = 24;
const ALL = "all";
const PILLS = 8;
/** Headline tournaments and the big five leagues lead; anything else follows by match count. */
const ORDER = ["FIFA World Cup", "UEFA Euro", "Champions League", "Premier League", "La Liga", "Copa America", "African Cup of Nations",
  "Serie A", "1. Bundesliga", "Ligue 1"];
const rank = (name: string) => (ORDER.includes(name) ? ORDER.indexOf(name) : ORDER.length);

interface Group { name: string; total: number; seasons: Competition[] }

/** One pill per competition, newest season first. */
function groupComps(comps: Competition[]): Group[] {
  const by = new Map<string, Group>();
  for (const c of comps) {
    const g = by.get(c.competition) ?? { name: c.competition, total: 0, seasons: [] };
    g.total += c.n_matches;
    g.seasons.push(c);
    by.set(c.competition, g);
  }
  const groups = [...by.values()];
  for (const g of groups) g.seasons.sort((a, b) => b.season.localeCompare(a.season));
  return groups.sort((a, b) => rank(a.name) - rank(b.name) || b.total - a.total || a.name.localeCompare(b.name));
}

/** Small competitions open on all seasons; big ones on their newest full season. */
const defaultSeason = (g: Group | undefined) =>
  !g || g.seasons.length === 1 || g.total <= 120 ? ALL : (g.seasons.find((s) => s.n_matches >= 20) ?? g.seasons[0]).id;
const newestFirst = (a: MatchCard, b: MatchCard) => (b.match_date ?? "").localeCompare(a.match_date ?? "") || b.season.localeCompare(a.season);

/** Browse by competition and season. Filters live in the URL (?comp=&season=) so links and the back button work. */
export function MatchGrid() {
  const { competitions, matches, status, load } = useCatalogue();
  const groups = useMemo(() => groupComps(competitions), [competitions]);
  const [params, setParams] = useSearchParams();
  const [limit, setLimit] = useState(PAGE);
  const group = groups.find((g) => g.name === params.get("comp")) ?? groups[0];
  const activeSeason = params.get("season") ?? defaultSeason(group);
  const pills = groups.slice(0, PILLS);
  const more = groups.slice(PILLS);
  // a competition picked from "More" (or a search link) gets its own pill while it's active
  const shownPills = group && !pills.includes(group) ? [...pills, group] : pills;

  const filtered = useMemo(
    () => matches.filter((m) => m.competition === group?.name && (activeSeason === ALL || m.competition_key === activeSeason)).sort(newestFirst),
    [matches, group, activeSeason],
  );
  const shown = filtered.slice(0, limit);
  const seasonRow = useRef<HTMLDivElement>(null);
  const pillRow = useRef<HTMLDivElement>(null);

  // On narrow screens the rows scroll sideways; keep the active pills in view without moving the page.
  useEffect(() => {
    for (const row of [pillRow.current, seasonRow.current]) {
      const on = row?.querySelector<HTMLElement>("[aria-pressed=true]");
      if (row && on) row.scrollLeft = on.offsetLeft - row.offsetLeft - 20;
    }
  }, [group, activeSeason]);
  const set = (next: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) if (v == null) p.delete(k); else p.set(k, v);
    setParams(p, { replace: true, preventScrollReset: true });
    setLimit(PAGE);
  };
  const pickGroup = (name: string) => set({ comp: name, season: null });

  return (
    <section id="matches" aria-labelledby="matches-title" className="mx-auto max-w-[1280px] scroll-mt-20 px-4 pt-4 sm:px-5 md:px-8">
      <h2 id="matches-title" className="text-[22px] font-semibold tracking-[-0.025em] text-ink md:text-[26px]">All matches</h2>
      <p className="mt-1 text-[14.5px] text-ink-3">Pick a competition and season. Every match opens on the pitch with its story.</p>

      <div className="relative -mx-4 mt-5 sm:-mx-5 md:mx-0">
        <div ref={pillRow} role="group" aria-label="Competition"
          className="scroll-thin flex items-center gap-1.5 overflow-x-auto px-4 pb-1 [mask-image:linear-gradient(to_right,black_calc(100%-32px),transparent)] sm:px-5 md:flex-wrap md:overflow-visible md:px-0 md:[mask-image:none]">
          {status !== "ready" && Array.from({ length: 6 }, (_, i) => <span key={i} className="h-9 w-28 shrink-0 rounded-full bg-surface-1 motion-safe:animate-pulse" aria-hidden />)}
          {shownPills.map((g) => {
            const on = group?.name === g.name;
            return (
              <button key={g.name} type="button" aria-pressed={on} onClick={() => pickGroup(g.name)}
                className={`relative shrink-0 whitespace-nowrap rounded-full px-4 py-2 text-[13.5px] font-medium transition-colors duration-150 active:scale-[0.97] ${on ? "text-bg" : "text-ink-2 hover:bg-surface-2 hover:text-ink"}`}>
                {on && <motion.span layoutId="comp-pill" className="absolute inset-0 rounded-full bg-ink" transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }} />}
                <span className="relative">{g.name} <span className={`tabular ${on ? "text-bg/60" : "text-ink-4"}`}>{g.total}</span></span>
              </button>
            );
          })}
          {more.length > 0 && (
            <label className="relative inline-flex shrink-0 items-center">
              <span className="sr-only">More competitions</span>
              <select value="" onChange={(e) => e.target.value && pickGroup(e.target.value)}
                className="cursor-pointer appearance-none rounded-full bg-transparent py-2 pl-4 pr-9 text-base font-medium text-ink-2 ring-1 ring-line transition-[background-color,box-shadow] duration-150 hover:bg-surface-2 hover:ring-line-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-ink sm:text-[13.5px]">
                <option value="">More competitions</option>
                {more.map((g) => <option key={g.name} value={g.name}>{g.name} ({g.total})</option>)}
              </select>
              <CaretDown size={13} weight="bold" className="pointer-events-none absolute right-3.5 text-ink-3" aria-hidden />
            </label>
          )}
        </div>
      </div>

      {group && group.seasons.length > 1 && (
        <div ref={seasonRow} className="scroll-thin -mx-4 mt-3 flex gap-1 overflow-x-auto px-4 pb-1 sm:-mx-5 sm:px-5 md:mx-0 md:flex-wrap md:overflow-visible md:px-0" role="group" aria-label="Season">
          {[{ id: ALL, season: "All seasons", n_matches: group.total }, ...group.seasons].map((c) => {
            const on = activeSeason === c.id;
            return (
              <button key={c.id} type="button" aria-pressed={on} onClick={() => set({ season: c.id })}
                className={`shrink-0 whitespace-nowrap rounded-full px-3 py-1.5 text-[12.5px] font-medium ring-1 transition-colors duration-150 active:scale-[0.97] ${on ? "bg-surface-3 text-ink ring-line-strong" : "text-ink-3 ring-transparent hover:bg-surface-2 hover:text-ink"}`}>
                {c.season} <span className="tabular text-ink-4">{c.n_matches}</span>
              </button>
            );
          })}
        </div>
      )}

      <p role="status" className="sr-only">{status === "ready" ? `${filtered.length} matches` : ""}</p>

      {(status === "loading" || status === "idle") && (
        <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" aria-hidden>
          {Array.from({ length: 8 }, (_, i) => <div key={i} className="h-[104px] rounded-2xl bg-surface-1 ring-1 ring-line motion-safe:animate-pulse" />)}
        </div>
      )}

      {status === "error" && (
        <div role="alert" className="mt-6 rounded-2xl bg-surface-1 px-6 py-12 text-center ring-1 ring-line">
          <p className="text-[15px] font-medium text-ink">Unable to load matches</p>
          <p className="mt-1.5 text-[14px] text-ink-3">Check your connection, then try again.</p>
          <button type="button" onClick={() => void load(true)}
            className="mt-5 rounded-full bg-surface-3 px-4 py-2 text-[13.5px] font-medium text-ink transition-[background-color,transform] duration-150 hover:bg-surface-4 active:scale-[0.97]">Try again</button>
        </div>
      )}

      {status === "ready" && (
        <div key={`${group?.name}:${activeSeason}`} className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {shown.map((m, i) => <Card key={m.match_id} m={m} i={i % PAGE} />)}
        </div>
      )}

      {status === "ready" && filtered.length > shown.length && (
        <div className="mt-6 flex flex-col items-center gap-2">
          <button type="button" onClick={() => setLimit((n) => n + PAGE * 2)}
            className="rounded-full bg-surface-3 px-5 py-2.5 text-[13.5px] font-medium text-ink transition-[background-color,transform] duration-150 hover:bg-surface-4 active:scale-[0.97]">Show more matches</button>
          <p className="tabular text-[13px] text-ink-3">Showing {shown.length} of {filtered.length}</p>
        </div>
      )}
    </section>
  );
}

function Card({ m, i }: { m: MatchCard; i: number }) {
  const winner = m.home_score > m.away_score ? "home" : m.away_score > m.home_score ? "away" : null;
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: Math.min(i * 0.02, 0.24), ease: [0.22, 1, 0.36, 1] }}>
      <Link to={matchPath(m.match_id)}
        className="block rounded-2xl bg-surface-1 px-4 pb-4 pt-3.5 ring-1 ring-line transition-[background-color,box-shadow,transform] duration-150 hover:bg-surface-2 hover:ring-line-strong active:scale-[0.98]">
        <div className="mb-3 flex items-baseline justify-between gap-3 text-[12.5px] text-ink-3">
          <span className="truncate">{m.stage ?? m.competition}</span>
          <span className="tabular shrink-0">{matchDate(m)}</span>
        </div>
        {(["home", "away"] as const).map((s) => (
          <div key={s} className="flex items-center gap-2.5 py-[3px]">
            <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: m[s].color }} aria-hidden />
            <span className={`flex-1 truncate text-[14.5px] ${winner === s ? "font-semibold text-ink" : "text-ink-2"}`}>{m[s].name}</span>
            <span className={`numeral text-[22px] leading-none ${winner === s ? "text-ink" : "text-ink-3"}`}>{s === "home" ? m.home_score : m.away_score}</span>
          </div>
        ))}
      </Link>
    </motion.div>
  );
}
