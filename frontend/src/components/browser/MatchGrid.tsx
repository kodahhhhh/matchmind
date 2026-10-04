import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { motion } from "motion/react";
import { MagnifyingGlass } from "@phosphor-icons/react";
import type { Competition, MatchCard } from "../../api/types";

const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
const PAGE = 48;
const ALL = "all";
/** Headline tournaments and the big five leagues lead; anything else follows by match count. */
const ORDER = ["FIFA World Cup", "UEFA Euro", "Copa America", "African Cup of Nations", "Champions League", "Premier League",
  "La Liga", "Serie A", "1. Bundesliga", "Ligue 1"];
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

/** Small competitions open on all seasons; big ones on their fullest season (newest wins a tie). */
const defaultSeason = (g: Group | undefined) =>
  !g || g.seasons.length === 1 || g.total <= 120 ? ALL : g.seasons.reduce((a, b) => (b.n_matches > a.n_matches ? b : a)).id;
const newestFirst = (a: MatchCard, b: MatchCard) => (b.match_date ?? "").localeCompare(a.match_date ?? "") || b.season.localeCompare(a.season);

/** The match browser: competition and season filters, team search, and the card grid with its loading, empty and error states. */
export function MatchGrid({ comps, matches, status, onRetry }: {
  comps: Competition[]; matches: MatchCard[]; status: "loading" | "ready" | "error"; onRetry: () => void;
}) {
  const groups = useMemo(() => groupComps(comps), [comps]);
  const [picked, setPicked] = useState<string | null>(null);
  const [season, setSeason] = useState<string | null>(null);
  const [limit, setLimit] = useState(PAGE);
  const [q, setQ] = useState("");
  const group = groups.find((g) => g.name === picked) ?? groups[0];
  const activeSeason = season ?? defaultSeason(group);
  const needle = q.trim().toLowerCase();

  const filtered = useMemo(
    () => matches
      .filter((m) => needle
        ? `${m.home.name} ${m.away.name}`.toLowerCase().includes(needle)
        : m.competition === group?.name && (activeSeason === ALL || m.competition_key === activeSeason))
      .sort(newestFirst),
    [matches, group, activeSeason, needle],
  );
  const shown = filtered.slice(0, limit);
  const seasonRow = useRef<HTMLDivElement>(null);

  // On narrow screens the season row scrolls sideways; keep the active season in view without moving the page.
  useEffect(() => {
    const row = seasonRow.current;
    const on = row?.querySelector<HTMLElement>("[aria-pressed=true]");
    if (row && on) row.scrollLeft = on.offsetLeft - row.offsetLeft - 20;
  }, [group, activeSeason]);
  const pickGroup = (g: Group) => { setPicked(g.name); setSeason(null); setLimit(PAGE); setQ(""); };
  const pickSeason = (id: string) => { setSeason(id); setLimit(PAGE); };

  return (
    <section id="matches" aria-labelledby="matches-title" className="mx-auto max-w-[1280px] scroll-mt-20 px-5 pb-28 pt-28 md:px-8">
      <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 id="matches-title" className="text-[30px] font-semibold leading-[1.1] tracking-[-0.03em] text-ink md:text-[38px]">Browse matches</h2>
          <p className="mt-3 text-[15.5px] text-ink-3">Every match opens on the tactical pitch, with the timeline and analyst beside it.</p>
        </div>
        <div className="relative w-full md:w-72">
          <label htmlFor="team-search" className="sr-only">Search by team</label>
          <MagnifyingGlass size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-ink-3" aria-hidden />
          <input id="team-search" type="search" value={q} onChange={(e) => { setQ(e.target.value); setLimit(PAGE); }}
            onKeyDown={(e) => e.key === "Escape" && setQ("")} placeholder="Search by team, e.g. Spain"
            className="w-full rounded-full bg-surface-1 py-2.5 pl-11 pr-4 text-base text-ink ring-1 ring-line transition-[box-shadow,background-color] duration-150 placeholder:text-ink-3 hover:ring-line-strong focus:bg-surface-2 focus:outline-none focus:ring-2 focus:ring-ink-3 sm:text-[14px]" />
        </div>
      </div>

      <div className="relative -mx-5 mt-8 md:mx-0">
        <div className="scroll-thin flex gap-1.5 overflow-x-auto px-5 pb-1 [mask-image:linear-gradient(to_right,black_calc(100%-40px),transparent)] md:flex-wrap md:overflow-visible md:px-0 md:[mask-image:none]">
          {groups.map((g) => {
            const on = group?.name === g.name && !needle;
            return (
              <button key={g.name} type="button" aria-pressed={on} onClick={() => pickGroup(g)}
                className={`relative shrink-0 whitespace-nowrap rounded-full px-4 py-2 text-[13.5px] font-medium transition-colors duration-150 active:scale-[0.97] ${on ? "text-bg" : "text-ink-3 hover:bg-surface-2 hover:text-ink"}`}>
                {on && <motion.span layoutId="comp-pill" className="absolute inset-0 rounded-full bg-ink" transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }} />}
                <span className="relative">{g.name} <span className={`tabular ${on ? "text-bg/60" : "text-ink-4"}`}>{g.total}</span></span>
              </button>
            );
          })}
        </div>
      </div>

      {group && group.seasons.length > 1 && !needle && (
        <div ref={seasonRow} className="scroll-thin -mx-5 mt-3 flex gap-1 overflow-x-auto px-5 pb-1 md:mx-0 md:flex-wrap md:overflow-visible md:px-0" role="group" aria-label="Season">
          {[{ id: ALL, season: "All seasons", n_matches: group.total }, ...group.seasons].map((c) => {
            const on = activeSeason === c.id;
            return (
              <button key={c.id} type="button" aria-pressed={on} onClick={() => pickSeason(c.id)}
                className={`shrink-0 whitespace-nowrap rounded-full px-3 py-1.5 text-[12.5px] font-medium ring-1 transition-colors duration-150 active:scale-[0.97] ${on ? "bg-surface-3 text-ink ring-line-strong" : "text-ink-3 ring-transparent hover:bg-surface-2 hover:text-ink"}`}>
                {c.season} <span className="tabular text-ink-4">{c.n_matches}</span>
              </button>
            );
          })}
        </div>
      )}

      <p role="status" className="sr-only">{status === "ready" ? `${filtered.length} matches` : ""}</p>

      {status === "loading" && (
        <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" aria-hidden>
          {Array.from({ length: 8 }, (_, i) => (
            <div key={i} className="h-[104px] rounded-2xl bg-surface-1 ring-1 ring-line motion-safe:animate-pulse" />
          ))}
        </div>
      )}

      {status === "error" && (
        <div className="mt-6 rounded-2xl bg-surface-1 px-6 py-12 text-center ring-1 ring-line">
          <p className="text-[15px] font-medium text-ink">Unable to load matches</p>
          <p className="mt-1.5 text-[14px] text-ink-3">Check that the API is running, then try again.</p>
          <button type="button" onClick={onRetry}
            className="mt-5 rounded-full bg-surface-3 px-4 py-2 text-[13.5px] font-medium text-ink transition-[background-color,transform] duration-150 hover:bg-surface-4 active:scale-[0.97]">Try again</button>
        </div>
      )}

      {status === "ready" && shown.length > 0 && (
        <div key={needle || `${group?.name}:${activeSeason}`} className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {shown.map((m, i) => <Card key={m.match_id} m={m} i={i % PAGE} />)}
        </div>
      )}

      {status === "ready" && filtered.length > shown.length && (
        <div className="mt-6 flex flex-col items-center gap-2">
          <button type="button" onClick={() => setLimit((n) => n + PAGE)}
            className="rounded-full bg-surface-3 px-5 py-2.5 text-[13.5px] font-medium text-ink transition-[background-color,transform] duration-150 hover:bg-surface-4 active:scale-[0.97]">Show more matches</button>
          <p className="tabular text-[13px] text-ink-3">Showing {shown.length} of {filtered.length}</p>
        </div>
      )}

      {status === "ready" && shown.length === 0 && (
        <div className="mt-6 rounded-2xl px-6 py-14 text-center ring-1 ring-line">
          <p className="text-[15px] font-medium text-ink">No matches for “{q.trim()}”</p>
          <p className="mt-1.5 text-[14px] text-ink-3">Try a country or club name.</p>
          <button type="button" onClick={() => setQ("")}
            className="mt-5 rounded-full bg-surface-3 px-4 py-2 text-[13.5px] font-medium text-ink transition-[background-color,transform] duration-150 hover:bg-surface-4 active:scale-[0.97]">Clear search</button>
        </div>
      )}
    </section>
  );
}

function Card({ m, i }: { m: MatchCard; i: number }) {
  const winner = m.home_score > m.away_score ? "home" : m.away_score > m.home_score ? "away" : null;
  const date = m.match_date ? dateFmt.format(new Date(m.match_date)) : m.season;
  return (
    <motion.div initial={{ opacity: 0, y: 6, filter: "blur(2px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      transition={{ duration: 0.25, delay: Math.min(i * 0.02, 0.24), ease: [0.22, 1, 0.36, 1] }}>
      <Link to={`/match/${encodeURIComponent(m.match_id)}`}
        className="block rounded-2xl bg-surface-1 px-4 pb-4 pt-3.5 ring-1 ring-line transition-[background-color,box-shadow,transform] duration-150 hover:bg-surface-2 hover:ring-line-strong active:scale-[0.98]">
        <div className="mb-3 flex items-baseline justify-between gap-3 text-[12.5px] text-ink-3">
          <span className="truncate">{m.stage ?? m.competition}</span>
          <span className="tabular shrink-0">{date}</span>
        </div>
        {(["home", "away"] as const).map((s) => (
          <div key={s} className="flex items-center gap-2.5 py-[3px]">
            <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: m[s].color }} />
            <span className={`flex-1 truncate text-[14.5px] ${winner === s ? "font-semibold text-ink" : "text-ink-2"}`}>{m[s].name}</span>
            <span className={`numeral text-[22px] leading-none ${winner === s ? "text-ink" : "text-ink-3"}`}>{s === "home" ? m.home_score : m.away_score}</span>
          </div>
        ))}
      </Link>
    </motion.div>
  );
}
