import { useMemo, useState, type ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import type { PlayerRow, Side } from "../../api/types";
import { useMatch } from "../../store/match";
import { usePlayerUi } from "../../store/ui";
import { signed } from "../../lib/format";

type Sort = "vaep" | "passes";
const EASE = [0.22, 1, 0.36, 1] as const;
const COLS = "grid-cols-[minmax(0,1fr)_84px_60px_34px] sm:grid-cols-[minmax(0,1fr)_104px_76px_40px]";

/** Value added (VAEP) vs raw pass counts: the story is where they disagree. */
export function Players() {
  const data = useMatch((s) => s.data);
  const [sort, setSort] = useState<Sort>("vaep");
  const [team, setTeam] = useState<Side | "all">("all");

  const rows = useMemo(() => {
    if (!data) return [];
    const ps = data.players.filter((p) => team === "all" || p.team === team);
    const passRank = new Map([...ps].sort((a, b) => b.passes - a.passes).map((p, i) => [p.player_id, i + 1]));
    const valueRank = new Map([...ps].sort((a, b) => b.vaep - a.vaep).map((p, i) => [p.player_id, i + 1]));
    return [...ps]
      .sort((a, b) => (sort === "vaep" ? b.vaep - a.vaep : b.passes - a.passes))
      .map((p) => ({ p, delta: passRank.get(p.player_id)! - valueRank.get(p.player_id)! }));
  }, [data, sort, team]);
  if (!data) return null;
  const maxV = Math.max(...rows.map((r) => r.p.vaep), 0.01);
  const maxP = Math.max(...rows.map((r) => r.p.passes), 1);
  const top = [...rows].sort((a, b) => b.delta - a.delta)[0];
  const teams = data.match.teams;
  const teamLabel = (s: Side) => (
    <span className="flex min-w-0 items-center gap-1.5">
      <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: `var(--${s})` }} aria-hidden />
      <span className="max-w-[88px] truncate">{teams[s].name}</span>
    </span>
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="px-5 pt-1">
        <h2 className="text-[16px] font-semibold leading-snug tracking-[-0.015em] text-ink">Who actually mattered</h2>
        <p className="mt-1 text-pretty text-[13.5px] leading-[1.55] text-ink-3">Value added measures how much each action changed the chance of scoring or conceding. Pass counts don't.</p>
        {top && top.delta > 3 && (
          <div className="mt-3.5 flex items-center gap-3 rounded-2xl bg-surface-2 p-3 ring-1 ring-line">
            <Jersey p={top.p.jersey} side={top.p.team} />
            <p className="min-w-0 text-pretty text-[13.5px] leading-snug text-ink-2">
              <span className="font-semibold text-ink">{top.p.short_name}</span> ranks <span className="tabular font-semibold text-ink">{top.delta} places higher</span> on impact than on passes: they did more with the ball than the pass count suggests.
            </p>
          </div>
        )}
        <div className="mt-3.5 flex flex-wrap items-center justify-between gap-2">
          <Seg id="players-sort" label="Sort by" value={sort} onChange={setSort} options={[["vaep", "Impact"], ["passes", "Passes"]]} />
          <Seg id="players-team" label="Team" value={team} onChange={setTeam}
            options={[["all", "Both"], ["home", teamLabel("home")], ["away", teamLabel("away")]]}
            names={{ all: "Both teams", home: teams.home.name, away: teams.away.name }} />
        </div>
        <div className={`mt-3.5 grid ${COLS} gap-2 px-1 pb-2 text-[12px] font-medium text-ink-3`} aria-hidden>
          <span>Player</span><span>Impact</span><span>Passes</span>
          <span className="text-right" title="Places higher on impact than on passes">Gap</span>
        </div>
      </div>
      <ol className="scroll-thin min-h-0 flex-1 overflow-y-auto px-4 pb-4" aria-label="Players">
        {rows.map(({ p, delta }, i) => <Row key={p.player_id} p={p} i={i} maxV={maxV} maxP={maxP} delta={delta} />)}
      </ol>
    </div>
  );
}

function Jersey({ p, side }: { p: number; side: Side }) {
  return (
    <span className="numeral flex size-8 shrink-0 items-center justify-center rounded-full text-[15px] text-bg" style={{ background: `var(--${side})` }}>{p}</span>
  );
}

function Row({ p, i, maxV, maxP, delta }: { p: PlayerRow; i: number; maxV: number; maxP: number; delta: number }) {
  const reduce = useReducedMotion();
  const gap = delta > 0 ? `+${delta}` : `${delta}`;
  const meta = [p.position, `${p.minutes}'`].filter(Boolean).join(" · ");
  return (
    <motion.li layout={!reduce} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      transition={{ duration: 0.25, delay: Math.min(i * 0.015, 0.24), ease: EASE, layout: { duration: 0.25, ease: EASE } }}>
      <button type="button" onClick={() => usePlayerUi.getState().openPlayer(p.player_id)}
        aria-label={`${p.short_name}, impact ${signed(p.vaep)}, ${p.passes} passes, rank gap ${gap}. Open profile`}
        className={`grid w-full ${COLS} items-center gap-2 rounded-xl px-1 py-2 text-left transition-[background-color,transform] duration-150 ease-out hover:bg-surface-2 active:scale-[0.99]`}>
        <span className="flex min-w-0 items-center gap-2.5">
          <Jersey p={p.jersey} side={p.team} />
          <span className="min-w-0">
            <span className="block truncate text-[13.5px] font-semibold text-ink">{p.short_name}</span>
            <span className="tabular block truncate text-[12px] text-ink-3">{meta}</span>
          </span>
        </span>
        <Bar v={p.vaep} max={maxV} label={signed(p.vaep)} color={`var(--${p.team})`} />
        <Bar v={p.passes} max={maxP} label={String(p.passes)} color="var(--ink-4)" />
        <span className={`tabular text-right text-[12.5px] font-semibold ${delta > 0 ? "text-ink" : "text-ink-4"}`}>{gap}</span>
      </button>
    </motion.li>
  );
}

function Bar({ v, max, label, color }: { v: number; max: number; label: string; color: string }) {
  return (
    <span className="flex items-center gap-1.5" aria-hidden>
      <span className="h-[5px] flex-1 rounded-full bg-surface-3">
        <span className="block h-[5px] rounded-full" style={{ width: `${(Math.max(v, 0) / max) * 100}%`, background: color }} />
      </span>
      <span className="tabular w-9 shrink-0 text-right text-[12.5px] text-ink-2 sm:w-10">{label}</span>
    </span>
  );
}

/** Segmented control with a sliding pill. */
function Seg<T extends string>({ id, label, value, onChange, options, names }: {
  id: string; label: string; value: T; onChange: (v: T) => void; options: [T, ReactNode][]; names?: Partial<Record<T, string>>;
}) {
  const reduce = useReducedMotion();
  return (
    <div role="group" aria-label={label} className="flex min-w-0 rounded-full bg-surface-2 p-1 ring-1 ring-line">
      {options.map(([v, l]) => {
        const on = value === v;
        return (
          <button key={v} type="button" aria-pressed={on} aria-label={names?.[v]} onClick={() => onChange(v)}
            className={`relative min-h-7 min-w-0 rounded-full px-3 py-1 text-[13px] font-medium transition-colors duration-200 ${on ? "text-bg" : "text-ink-3 hover:text-ink"}`}>
            {on && <motion.span layoutId={`${id}-pill`} className="absolute inset-0 rounded-full bg-ink" transition={{ duration: reduce ? 0 : 0.25, ease: EASE }} />}
            <span className="relative flex items-center">{l}</span>
          </button>
        );
      })}
    </div>
  );
}
