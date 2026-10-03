import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { motion } from "motion/react";
import { api } from "../../api/client";
import type { Competition, MatchCard, MatchEvent } from "../../api/types";
import { Logo } from "../ui/Logo";
import { PitchMarkings } from "../pitch/PitchMarkings";
import { PITCH, sy } from "../pitch/geometry";

const FEATURED = "sb:3869685";
const COMP_ORDER = ["FIFA World Cup", "UEFA Euro", "Copa America", "1. Bundesliga", "Major League Soccer"];

export function MatchBrowser() {
  const [comps, setComps] = useState<Competition[]>([]);
  const [matches, setMatches] = useState<MatchCard[]>([]);
  const [shots, setShots] = useState<MatchEvent[]>([]);
  const [active, setActive] = useState("");
  const [q, setQ] = useState("");

  useEffect(() => {
    void Promise.all([api.competitions(), api.matches()]).then(([c, m]) => {
      const sorted = [...c].sort((a, b) => COMP_ORDER.indexOf(a.competition) - COMP_ORDER.indexOf(b.competition) || b.season.localeCompare(a.season));
      setComps(sorted);
      setMatches(m);
      setActive(sorted[0]?.id ?? "");
    });
    api.events(FEATURED).then((ev) => setShots(ev.filter((e) => e.type.startsWith("shot") && e.x != null))).catch(() => {});
  }, []);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return matches.filter((m) => (needle ? `${m.home.name} ${m.away.name}`.toLowerCase().includes(needle) : m.competition_key === active));
  }, [matches, active, q]);
  const featured = matches.find((m) => m.match_id === FEATURED);

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <header className="mx-auto flex max-w-[1280px] items-center justify-between px-8 py-6">
        <Logo />
        <div className="flex items-center gap-2 text-[12.5px] text-ink-3">
          <span className="h-1.5 w-1.5 rounded-full bg-[#3ccf8e]" />
          {matches.length} matches · {comps.length} competitions
        </div>
      </header>

      <section className="mx-auto grid max-w-[1280px] grid-cols-1 items-center gap-10 px-8 pb-14 pt-6 lg:grid-cols-[1fr_560px]">
        <div>
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="eyebrow mb-4 flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-ai" /> AI football analyst
          </motion.div>
          <motion.h1 initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
            className="display text-[76px] leading-[0.9] text-ink">
            Stats say what<br />happened.<br /><span className="bg-gradient-to-r from-[#cfc4ff] to-[#8f7dff] bg-clip-text text-transparent">We show why.</span>
          </motion.h1>
          <motion.p initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
            className="mt-6 max-w-[480px] text-[16px] leading-relaxed text-ink-2">
            Replay any match on a tactical pitch, find the exact moment it turned, and ask an analyst that backs every claim with the events behind it.
          </motion.p>
        </div>
        {featured && <Featured m={featured} shots={shots} />}
      </section>

      <section className="mx-auto max-w-[1280px] px-8 pb-20">
        <div className="mb-6 flex flex-wrap items-center gap-2">
          {comps.map((c) => {
            const on = active === c.id && !q;
            return (
              <button key={c.id} onClick={() => { setActive(c.id); setQ(""); }}
                className={`rounded-xl px-3.5 py-2 text-[13px] font-medium ring-1 transition ${on ? "bg-surface-4 text-ink ring-white/15" : "bg-surface-1 text-ink-3 ring-line hover:text-ink-2"}`}>
                {c.competition} <span className={on ? "text-ink-3" : "text-ink-4"}>{c.season}</span>
              </button>
            );
          })}
          <div className="relative ml-auto">
            <svg className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-4" width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.5" /><path d="m9.5 9.5 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search any team"
              className="w-60 rounded-xl bg-surface-1 py-2 pl-9 pr-4 text-[13px] text-ink ring-1 ring-line placeholder:text-ink-4 focus:outline-none focus:ring-white/20" />
          </div>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {shown.map((m, i) => <Card key={m.match_id} m={m} i={i} />)}
        </div>
        {shown.length === 0 && <div className="py-16 text-center text-sm text-ink-3">No matches found.</div>}
      </section>
    </div>
  );
}

function Featured({ m, shots }: { m: MatchCard; shots: MatchEvent[] }) {
  const { L, W } = PITCH;
  return (
    <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15, duration: 0.6 }}>
      <Link to={`/match/${encodeURIComponent(m.match_id)}`}
        className="group relative block overflow-hidden rounded-[22px] shadow-[0_40px_100px_-40px_rgba(0,0,0,0.9)] ring-1 ring-white/10 transition hover:ring-white/25"
        style={{ ["--home" as string]: m.home.color, ["--away" as string]: m.away.color }}>
        <svg viewBox={`-3 -3 ${L + 6} ${W + 6}`} className="block w-full">
          <PitchMarkings pad={3} />
          {shots.map((e, i) => {
            const goal = e.result === "goal";
            const r = 0.6 + Math.sqrt(e.xg ?? 0.02) * 3.2;
            return (
              <motion.circle key={e.id} cx={e.x!} cy={sy(e.y!)} r={r} initial={{ opacity: 0, scale: 0 }} animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.5 + i * 0.025 }} style={{ transformOrigin: `${e.x}px ${sy(e.y!)}px` }}
                fill={`var(--${e.team})`} fillOpacity={goal ? 1 : 0.35} stroke={goal ? "#fff" : `var(--${e.team})`} strokeWidth={goal ? 0.35 : 0.3} />
            );
          })}
        </svg>
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/50 to-transparent px-6 pb-5 pt-16">
          <div className="eyebrow mb-2 text-white/60">Featured · {m.competition} {m.season} · {m.stage}</div>
          <div className="flex items-center justify-between">
            <div className="display flex items-center gap-3 text-[34px] leading-none text-white">
              <span className="h-7 w-1.5 rounded-full" style={{ background: m.home.color }} />{m.home.name}
              <span className="mx-1 text-white/70">{m.home_score}–{m.away_score}</span>
              {m.away.name}<span className="h-7 w-1.5 rounded-full" style={{ background: m.away.color }} />
            </div>
            <span className="ai-button rounded-xl px-4 py-2.5 text-[13px] font-semibold text-white transition group-hover:translate-x-0.5">Open match →</span>
          </div>
        </div>
      </Link>
    </motion.div>
  );
}

function Card({ m, i }: { m: MatchCard; i: number }) {
  const winner = m.home_score > m.away_score ? "home" : m.away_score > m.home_score ? "away" : null;
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.012, 0.35) }}>
      <Link to={`/match/${encodeURIComponent(m.match_id)}`}
        className="group relative block overflow-hidden rounded-2xl bg-surface-1 px-4 pb-3.5 pt-3 ring-1 ring-line transition hover:-translate-y-0.5 hover:bg-surface-2 hover:ring-white/15">
        <div className="absolute inset-x-0 top-0 flex h-[3px]">
          <span className="flex-1" style={{ background: m.home.color }} />
          <span className="flex-1" style={{ background: m.away.color }} />
        </div>
        <div className="mb-2.5 mt-1 flex items-center justify-between text-[11.5px] text-ink-4">
          <span className="truncate">{m.stage ?? m.competition}</span>
          <span className="tabular">{m.match_date ?? m.season}</span>
        </div>
        {(["home", "away"] as const).map((s) => (
          <div key={s} className="flex items-center gap-2.5 py-[3px]">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: m[s].color }} />
            <span className={`flex-1 truncate text-[14px] ${winner === s ? "font-semibold text-ink" : "text-ink-2"}`}>{m[s].name}</span>
            <span className={`display text-[22px] leading-none tabular ${winner === s ? "text-ink" : "text-ink-3"}`}>{s === "home" ? m.home_score : m.away_score}</span>
          </div>
        ))}
      </Link>
    </motion.div>
  );
}
