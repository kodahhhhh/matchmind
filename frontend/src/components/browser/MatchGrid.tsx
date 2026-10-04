import { useMemo, useState } from "react";
import { Link } from "react-router";
import { motion } from "motion/react";
import { MagnifyingGlass } from "@phosphor-icons/react";
import type { Competition, MatchCard } from "../../api/types";

const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });

/** The match browser: competition filter, team search, and the card grid with its loading, empty and error states. */
export function MatchGrid({ comps, matches, status, onRetry }: {
  comps: Competition[]; matches: MatchCard[]; status: "loading" | "ready" | "error"; onRetry: () => void;
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const active = picked ?? comps[0]?.id ?? "";
  const needle = q.trim().toLowerCase();

  const shown = useMemo(
    () => matches.filter((m) => (needle ? `${m.home.name} ${m.away.name}`.toLowerCase().includes(needle) : m.competition_key === active)),
    [matches, active, needle],
  );

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
          <input id="team-search" type="search" value={q} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Escape" && setQ("")} placeholder="Search by team, e.g. Spain"
            className="w-full rounded-full bg-surface-1 py-2.5 pl-11 pr-4 text-base text-ink ring-1 ring-line transition-[box-shadow,background-color] duration-150 placeholder:text-ink-3 hover:ring-line-strong focus:bg-surface-2 focus:outline-none focus:ring-2 focus:ring-ink-3 sm:text-[14px]" />
        </div>
      </div>

      <div className="relative -mx-5 mt-8 md:mx-0">
        <div className="scroll-thin flex gap-1.5 overflow-x-auto px-5 pb-1 [mask-image:linear-gradient(to_right,black_calc(100%-40px),transparent)] md:flex-wrap md:overflow-visible md:px-0 md:[mask-image:none]">
          {comps.map((c) => {
            const on = active === c.id && !needle;
            return (
              <button key={c.id} type="button" aria-pressed={on} onClick={() => { setPicked(c.id); setQ(""); }}
                className={`relative shrink-0 whitespace-nowrap rounded-full px-4 py-2 text-[13.5px] font-medium transition-colors duration-150 active:scale-[0.97] ${on ? "text-bg" : "text-ink-3 hover:bg-surface-2 hover:text-ink"}`}>
                {on && <motion.span layoutId="comp-pill" className="absolute inset-0 rounded-full bg-ink" transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }} />}
                <span className="relative">{c.competition} <span className={on ? "text-bg/60" : "text-ink-4"}>{c.season}</span></span>
              </button>
            );
          })}
        </div>
      </div>

      <p role="status" className="sr-only">{status === "ready" ? `${shown.length} matches shown` : ""}</p>

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
        <div key={needle || active} className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {shown.map((m, i) => <Card key={m.match_id} m={m} i={i} />)}
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
