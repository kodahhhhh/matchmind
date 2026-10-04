import { useMemo, useState } from "react";
import { motion } from "motion/react";
import type { PlayerRow, Side } from "../../api/types";
import { useMatch } from "../../store/match";
import { usePlayerUi } from "../../store/ui";
import { signed } from "../../lib/format";

type Sort = "vaep" | "passes";

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

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="px-5 pt-1">
        <div className="text-[15px] font-semibold text-ink">Who actually mattered</div>
        <p className="mt-0.5 text-[13px] leading-relaxed text-ink-3">Value added measures how much each action changed the chance of scoring or conceding. Pass counts don't.</p>
        {top && top.delta > 3 && (
          <div className="mt-3 flex items-center gap-3 rounded-2xl bg-surface-2 p-3 ring-1 ring-line">
            <Jersey p={top.p.jersey} side={top.p.team} />
            <div className="min-w-0 text-[13px] leading-snug text-ink-2">
              <span className="font-semibold text-ink">{top.p.short_name}</span> ranks <span className="font-semibold text-ink">{top.delta} places higher</span> on value added than on passes.
            </div>
          </div>
        )}
        <div className="mt-3 flex items-center justify-between gap-2">
          <Seg value={sort} onChange={setSort} options={[["vaep", "Value added"], ["passes", "Passes"]]} />
          <Seg value={team} onChange={setTeam} options={[["all", "Both"], ["home", data.match.teams.home.short], ["away", data.match.teams.away.short]]} />
        </div>
        <div className="mt-3 grid grid-cols-[1fr_104px_76px_40px] gap-2 px-1 pb-2 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-ink-4">
          <span>Player</span><span>Value added</span><span>Passes</span><span className="text-right">Δ</span>
        </div>
      </div>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-4 pb-4">
        {rows.map(({ p, delta }, i) => <Row key={p.player_id} p={p} i={i} maxV={maxV} maxP={maxP} delta={delta} />)}
      </div>
    </div>
  );
}

function Jersey({ p, side }: { p: number; side: Side }) {
  return (
    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[12px] font-bold text-bg" style={{ background: `var(--${side})` }}>{p}</span>
  );
}

function Row({ p, i, maxV, maxP, delta }: { p: PlayerRow; i: number; maxV: number; maxP: number; delta: number }) {
  return (
    <motion.div layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: Math.min(i * 0.015, 0.3) }}
      onClick={() => usePlayerUi.getState().openPlayer(p.player_id)} role="button" tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && usePlayerUi.getState().openPlayer(p.player_id)}
      className="grid cursor-pointer grid-cols-[1fr_104px_76px_40px] items-center gap-2 rounded-xl px-1 py-2 transition hover:bg-surface-2">
      <div className="flex min-w-0 items-center gap-2.5">
        <Jersey p={p.jersey} side={p.team} />
        <div className="min-w-0">
          <div className="truncate text-[13.5px] font-semibold text-ink">{p.short_name}</div>
          <div className="truncate text-[11.5px] text-ink-4">{p.position ?? "—"} · {p.minutes}'</div>
        </div>
      </div>
      <Bar v={p.vaep} max={maxV} label={signed(p.vaep)} color={`var(--${p.team})`} />
      <Bar v={p.passes} max={maxP} label={String(p.passes)} color="var(--ink-4)" />
      <span className={`text-right text-[12px] font-semibold tabular ${delta > 0 ? "text-ink" : "text-ink-4"}`}>{delta > 0 ? `+${delta}` : delta < 0 ? `${delta}` : "0"}</span>
    </motion.div>
  );
}

function Bar({ v, max, label, color }: { v: number; max: number; label: string; color: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className="h-[5px] flex-1 rounded-full bg-surface-3">
        <div className="h-[5px] rounded-full" style={{ width: `${(Math.max(v, 0) / max) * 100}%`, background: color }} />
      </div>
      <span className="w-10 text-right text-[12px] tabular text-ink-2">{label}</span>
    </div>
  );
}

function Seg<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: [T, string][] }) {
  return (
    <div className="flex rounded-xl bg-surface-2 p-1">
      {options.map(([v, l]) => (
        <button key={v} onClick={() => onChange(v)}
          className={`rounded-lg px-3 py-1.5 text-[12.5px] font-medium transition ${value === v ? "bg-surface-4 text-ink shadow" : "text-ink-3 hover:text-ink-2"}`}>{l}</button>
      ))}
    </div>
  );
}
