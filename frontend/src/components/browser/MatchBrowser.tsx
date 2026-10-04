import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { motion } from "motion/react";
import { api } from "../../api/client";
import type { Competition, MatchCard, MatchEvent } from "../../api/types";
import { Logo } from "../ui/Logo";
import { AnimatedNumber } from "../ui/AnimatedNumber";
import { useUi } from "../../store/ui";
import { SearchButton } from "../search/SearchPalette";
import { PitchMarkings } from "../pitch/PitchMarkings";
import { PITCH, sy } from "../pitch/geometry";

const FEATURED = "sb:3869685";
const COMP_ORDER = ["FIFA World Cup", "UEFA Euro", "Copa America", "1. Bundesliga", "Major League Soccer"];

export function MatchBrowser() {
  const [comps, setComps] = useState<Competition[]>([]);
  const [matches, setMatches] = useState<MatchCard[]>([]);
  const [shots, setShots] = useState<MatchEvent[]>([]);
  const [move, setMove] = useState<MatchEvent[]>([]);
  const [active, setActive] = useState("");
  const [q, setQ] = useState("");

  useEffect(() => {
    void Promise.all([api.competitions(), api.matches()]).then(([c, m]) => {
      const sorted = [...c].sort((a, b) => COMP_ORDER.indexOf(a.competition) - COMP_ORDER.indexOf(b.competition) || b.season.localeCompare(a.season));
      setComps(sorted);
      setMatches(m);
      setActive(sorted[0]?.id ?? "");
    });
    api.events(FEATURED).then((ev) => {
      setShots(ev.filter((e) => e.type.startsWith("shot") && e.x != null));
      // loop the best team goal: the open-play goal whose move has the most passes
      const goals = ev.filter((e) => e.result === "goal" && e.type === "shot");
      const best = goals.map((g) => ev.filter((e) => e.sequence_id === g.sequence_id && e.team === g.team && e.x != null))
        .sort((a, b) => b.filter((e) => e.type === "pass").length - a.filter((e) => e.type === "pass").length)[0];
      if (best) setMove(best.slice(-9));
    }).catch(() => {});
  }, []);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return matches.filter((m) => (needle ? `${m.home.name} ${m.away.name}`.toLowerCase().includes(needle) : m.competition_key === active));
  }, [matches, active, q]);
  const featured = matches.find((m) => m.match_id === FEATURED);

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <header className="mx-auto flex max-w-[1280px] items-center justify-between gap-3 px-5 py-5 md:px-8 md:py-6">
        <Logo />
        <div className="flex items-center gap-4">
          <span className="hidden items-center gap-2 text-[12.5px] text-ink-3 lg:flex">
            <span className="h-1.5 w-1.5 rounded-full bg-[#3ccf8e]" />
            {matches.length} matches · {comps.length} competitions
          </span>
          <Link to="/players" className="hidden rounded-xl px-3 py-2 md:block text-[13px] font-medium text-ink-2 ring-1 ring-line transition hover:bg-surface-2 hover:text-ink">Underrated players</Link>
          <Link to="/backtest" className="hidden rounded-xl px-3 py-2 md:block text-[13px] font-medium text-ink-2 ring-1 ring-line transition hover:bg-surface-2 hover:text-ink">Backtest vs markets</Link>
          <SearchButton />
        </div>
      </header>

      <section className="mx-auto grid max-w-[1280px] grid-cols-1 items-center gap-10 px-5 pb-14 pt-6 md:px-8 lg:grid-cols-[1fr_560px]">
        <div>
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="eyebrow mb-4 flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-ai" /> AI football analyst
          </motion.div>
          <motion.h1 initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
            className="display text-[48px] leading-[0.9] text-ink md:text-[76px]">
            Stats say what<br />happened.<br /><span className="bg-gradient-to-r from-[#cfc4ff] to-[#8f7dff] bg-clip-text text-transparent">We show why.</span>
          </motion.h1>
          <motion.p initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
            className="mt-6 max-w-[480px] text-[16px] leading-relaxed text-ink-2">
            Replay any match on a tactical pitch, find the exact moment it turned, and ask an analyst that backs every claim with the events behind it.
          </motion.p>
        </div>
        {featured && <Featured m={featured} shots={shots} move={move} />}
      </section>

      <Stats />
      <Features />

      <section className="mx-auto max-w-[1280px] px-5 pb-20 md:px-8">
        <div className="mb-6 flex flex-wrap items-center gap-2">
          {comps.map((c) => {
            const on = active === c.id && !q;
            return (
              <button key={c.id} onClick={() => { setActive(c.id); setQ(""); }}
                className={`relative rounded-xl px-3.5 py-2 text-[13px] font-medium ring-1 transition ${on ? "text-ink ring-white/15" : "bg-surface-1 text-ink-3 ring-line hover:text-ink-2"}`}>
                {on && <motion.span layoutId="comp-pill" className="absolute inset-0 rounded-xl bg-surface-4" transition={{ type: "spring", bounce: 0.15, duration: 0.45 }} />}
                <span className="relative">{c.competition} <span className={on ? "text-ink-3" : "text-ink-4"}>{c.season}</span></span>
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

function Featured({ m, shots, move }: { m: MatchCard; shots: MatchEvent[]; move: MatchEvent[] }) {
  const { L, W } = PITCH;
  return (
    <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15, duration: 0.6 }}>
      <Link to={`/match/${encodeURIComponent(m.match_id)}`}
        className="group relative block overflow-hidden rounded-[22px] shadow-[0_40px_100px_-40px_rgba(0,0,0,0.9)] ring-1 ring-white/10 transition hover:ring-white/25"
        style={{ ["--home" as string]: m.home.color, ["--away" as string]: m.away.color }}>
        <svg viewBox={`-3 -3 ${L + 6} ${W + 6}`} className="block w-full">
          <PitchMarkings pad={3} />
          <LoopingMove move={move} />
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
          <div className="eyebrow mb-2 truncate text-white/60">Featured · {m.competition} {m.season} · {m.stage}</div>
          <div className="flex items-center justify-between">
            <div className="display flex flex-wrap items-center gap-x-3 gap-y-1 text-[22px] leading-none text-white md:text-[34px]">
              <span className="h-7 w-1.5 rounded-full" style={{ background: m.home.color }} />{m.home.name}
              <span className="mx-1 whitespace-nowrap text-white/70">{m.home_score}–{m.away_score}</span>
              {m.away.name}<span className="h-7 w-1.5 rounded-full" style={{ background: m.away.color }} />
            </div>
            <span className="ai-button hidden shrink-0 rounded-xl px-4 py-2.5 text-[13px] font-semibold text-white transition group-hover:translate-x-0.5 sm:inline">Open match →</span>
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

/** Draws the featured goal's passing move on repeat over the shot map. */
function LoopingMove({ move }: { move: MatchEvent[] }) {
  if (move.length < 2) return null;
  const total = move.length * 0.32 + 1.6;
  return (
    <g strokeLinecap="round" fill="none" pointerEvents="none">
      {move.map((e, i) => (
        <motion.line key={e.id} x1={e.x!} y1={sy(e.y!)} x2={e.end_x!} y2={sy(e.end_y!)} stroke="#fff" strokeWidth={e.type === "carry" ? 0.3 : 0.45}
          strokeDasharray={e.type === "carry" ? "0.15 0.8" : undefined}
          initial={{ pathLength: 0, opacity: 0 }}
          animate={{ pathLength: [0, 1, 1, 1], opacity: [0, 0.9, 0.9, 0] }}
          transition={{ duration: total, times: [0, 0.12, 0.85, 1], delay: i * 0.32, repeat: Infinity, repeatDelay: 0.6, ease: "easeOut" }} />
      ))}
      {move.map((e, i) => (
        <motion.circle key={`d-${e.id}`} cx={e.x!} cy={sy(e.y!)} r={0.9} fill="#fff"
          initial={{ opacity: 0 }} animate={{ opacity: [0, 1, 1, 0] }}
          transition={{ duration: total, times: [0, 0.08, 0.85, 1], delay: i * 0.32, repeat: Infinity, repeatDelay: 0.6 }} />
      ))}
    </g>
  );
}

function Stats() {
  const items: [number, string][] = [[493, "matches to explore"], [2924, "matches our models trained on"], [82580, "lines of AI commentary"], [52151, "player profiles"]];
  return (
    <section className="mx-auto max-w-[1280px] px-5 pb-10 md:px-8">
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl bg-line ring-1 ring-line md:grid-cols-4">
        {items.map(([n, label], i) => (
          <motion.div key={label} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 + i * 0.07 }}
            className="bg-surface-1 px-5 py-4">
            <div className="display text-[34px] leading-none text-ink"><AnimatedNumber value={n} from={0} ms={1400} format={(v) => Math.round(v).toLocaleString()} /></div>
            <div className="mt-1.5 text-[12.5px] text-ink-3">{label}</div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

function Features() {
  const open = () => useUi.getState().setSearchOpen(true);
  const cards: { title: string; body: string; cta: string; to?: string; onClick?: () => void; accent: string }[] = [
    { title: "Search every moment", body: "Semantic search over 82,580 lines of commentary: “a goalkeeper makes a brilliant save”.", cta: "Press ⌘K", onClick: open, accent: "#b6a4ff" },
    { title: "Who did the market underrate?", body: "Value added per 90 against Transfermarkt prices, for every player with real minutes.", cta: "See players", to: "/players", accent: "#3ccf8e" },
    { title: "Would it beat the bookies?", body: "We backtested our models against Pinnacle and Polymarket. Honest answer inside.", cta: "See the backtest", to: "/backtest", accent: "#f2c94c" },
  ];
  return (
    <section className="mx-auto grid max-w-[1280px] grid-cols-1 gap-3 px-5 pb-12 md:grid-cols-3 md:px-8">
      {cards.map((c, i) => {
        const inner = (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 + i * 0.08 }}
            whileHover={{ y: -3 }} className="group relative h-full overflow-hidden rounded-2xl bg-surface-1 p-5 ring-1 ring-line transition-colors hover:ring-white/15">
            <div className="absolute -right-10 -top-10 h-32 w-32 rounded-full opacity-20 blur-2xl transition-opacity group-hover:opacity-40" style={{ background: c.accent }} />
            <div className="relative">
              <div className="text-[16px] font-semibold text-ink">{c.title}</div>
              <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-3">{c.body}</p>
              <div className="mt-4 text-[13px] font-semibold" style={{ color: c.accent }}>{c.cta} →</div>
            </div>
          </motion.div>
        );
        return c.to ? <Link key={c.title} to={c.to}>{inner}</Link> : <button key={c.title} onClick={c.onClick} className="text-left">{inner}</button>;
      })}
    </section>
  );
}

