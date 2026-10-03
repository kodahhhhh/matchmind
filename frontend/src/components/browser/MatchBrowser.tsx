import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { motion } from "motion/react";
import { api } from "../../api/client";
import type { Competition, MatchCard } from "../../api/types";
import { Logo } from "../ui/Logo";

const FEATURED = "sb:3869685";

export function MatchBrowser() {
  const [comps, setComps] = useState<Competition[]>([]);
  const [matches, setMatches] = useState<MatchCard[]>([]);
  const [active, setActive] = useState<string>("");
  const [q, setQ] = useState("");

  useEffect(() => {
    void Promise.all([api.competitions(), api.matches()]).then(([c, m]) => {
      setComps(c);
      setMatches(m);
      setActive(c.find((x) => x.competition === "FIFA World Cup")?.id ?? c[0]?.id ?? "");
    });
  }, []);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return matches.filter((m) =>
      needle ? `${m.home.name} ${m.away.name}`.toLowerCase().includes(needle) : m.competition_key === active,
    );
  }, [matches, active, q]);
  const featured = matches.find((m) => m.match_id === FEATURED);

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <header className="mx-auto flex max-w-[1240px] items-center justify-between px-6 py-5">
        <Logo />
        <span className="text-xs text-ink-3">{matches.length} matches · StatsBomb open data</span>
      </header>

      <section className="mx-auto max-w-[1240px] px-6 pb-8 pt-6">
        <motion.h1 initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          className="max-w-[760px] font-display text-[56px] font-semibold uppercase leading-[0.95] tracking-wide">
          Stats tell you what happened.<br /><span className="text-ink-3">MatchMind tells you why.</span>
        </motion.h1>
        <p className="mt-4 max-w-[560px] text-[15px] leading-relaxed text-ink-2">
          Replay any match on a tactical pitch, find the moment it turned, and ask an analyst that cites every claim back to the events.
        </p>
        {featured && <Featured m={featured} />}
      </section>

      <section className="mx-auto max-w-[1240px] px-6 pb-16">
        <div className="mb-5 flex flex-wrap items-center gap-2">
          {comps.map((c) => (
            <button key={c.id} onClick={() => { setActive(c.id); setQ(""); }}
              className={`rounded-full border px-3.5 py-1.5 text-sm transition ${active === c.id && !q ? "border-line-strong bg-surface-3 text-ink" : "border-line text-ink-3 hover:text-ink-2"}`}>
              {c.competition} <span className="text-ink-4">{c.season}</span>
            </button>
          ))}
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search teams…"
            className="ml-auto w-56 rounded-full border border-line bg-surface-2 px-4 py-1.5 text-sm text-ink placeholder:text-ink-4 focus:border-line-strong focus:outline-none" />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {shown.map((m, i) => <Card key={m.match_id} m={m} i={i} />)}
        </div>
        {shown.length === 0 && <div className="py-12 text-center text-sm text-ink-3">No matches found.</div>}
      </section>
    </div>
  );
}

function Featured({ m }: { m: MatchCard }) {
  return (
    <Link to={`/match/${encodeURIComponent(m.match_id)}`}
      className="group mt-8 flex items-center gap-6 rounded-2xl border border-line bg-surface-1/70 p-5 transition hover:border-line-strong">
      <div className="flex-1">
        <div className="mb-2 text-[11px] uppercase tracking-[0.16em] text-ink-3">Featured · {m.competition} {m.season} · {m.stage}</div>
        <div className="flex items-center gap-4 font-display text-3xl font-semibold uppercase tracking-wide">
          <TeamName name={m.home.name} color={m.home.color} />
          <span className="text-ink-2">{m.home_score} – {m.away_score}</span>
          <TeamName name={m.away.name} color={m.away.color} />
        </div>
      </div>
      <span className="rounded-xl border border-[var(--ai-line)] bg-ai-soft px-4 py-2 text-sm font-semibold text-ink transition group-hover:shadow-[0_0_24px_rgba(184,166,255,0.25)]">
        Open match →
      </span>
    </Link>
  );
}

function TeamName({ name, color }: { name: string; color: string }) {
  return <span className="flex items-center gap-2.5"><span className="h-6 w-1.5 rounded-full" style={{ background: color }} />{name}</span>;
}

function Card({ m, i }: { m: MatchCard; i: number }) {
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.015, 0.4) }}>
      <Link to={`/match/${encodeURIComponent(m.match_id)}`}
        className="block rounded-xl border border-line bg-surface-1/60 px-4 py-3.5 transition hover:border-line-strong hover:bg-surface-2">
        <div className="mb-2.5 flex items-center justify-between text-[11px] text-ink-3">
          <span className="truncate">{m.stage ?? m.competition}</span>
          <span className="tabular">{m.match_date ?? m.season}</span>
        </div>
        {(["home", "away"] as const).map((s) => (
          <div key={s} className="flex items-center gap-2.5 py-0.5">
            <span className="h-3.5 w-1 rounded-full" style={{ background: m[s].color }} />
            <span className="flex-1 truncate text-sm text-ink">{m[s].name}</span>
            <span className="font-display text-lg font-semibold tabular text-ink">{s === "home" ? m.home_score : m.away_score}</span>
          </div>
        ))}
      </Link>
    </motion.div>
  );
}
