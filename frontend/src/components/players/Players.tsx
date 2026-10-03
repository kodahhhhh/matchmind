import { useMemo, useState } from "react";
import type { PlayerRow, Side } from "../../api/types";
import { useMatch } from "../../store/match";
import { signed } from "../../lib/format";

type Sort = "vaep" | "passes";

/** VAEP ranking vs raw pass counts: the point is that they disagree. */
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
      .map((p) => ({ p, passRank: passRank.get(p.player_id)!, valueRank: valueRank.get(p.player_id)! }));
  }, [data, sort, team]);
  if (!data) return null;
  const maxV = Math.max(...rows.map((r) => Math.abs(r.p.vaep)), 0.01);
  const maxP = Math.max(...rows.map((r) => r.p.passes), 1);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="px-5 pt-5">
        <div className="mb-1 text-sm font-medium text-ink">Who actually mattered</div>
        <p className="mb-3 text-xs leading-relaxed text-ink-3">
          Value added (VAEP) counts how much each action changed the chance of scoring or conceding. Compare it with raw pass counts.
        </p>
        <div className="mb-3 flex items-center gap-2 text-xs">
          <Seg value={sort} onChange={setSort} options={[["vaep", "Value added"], ["passes", "Passes"]]} />
          <Seg value={team} onChange={setTeam} options={[["all", "Both"], ["home", data.match.teams.home.short], ["away", data.match.teams.away.short]]} />
        </div>
        <div className="grid grid-cols-[1fr_96px_72px_44px] gap-2 border-b border-line pb-1.5 text-[10px] uppercase tracking-[0.14em] text-ink-3">
          <span>Player</span><span>Value added</span><span>Passes</span><span className="whitespace-nowrap text-right">Δ rank</span>
        </div>
      </div>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-5 pb-5">
        {rows.map(({ p, passRank, valueRank }) => (
          <Row key={p.player_id} p={p} maxV={maxV} maxP={maxP} delta={passRank - valueRank} />
        ))}
      </div>
    </div>
  );
}

function Row({ p, maxV, maxP, delta }: { p: PlayerRow; maxV: number; maxP: number; delta: number }) {
  return (
    <div className="grid grid-cols-[1fr_96px_72px_44px] items-center gap-2 border-b border-line/60 py-2 text-xs">
      <div className="flex min-w-0 items-center gap-2">
        <span className="h-4 w-1 shrink-0 rounded-full" style={{ background: `var(--${p.team})` }} />
        <span className="w-5 shrink-0 text-right tabular text-ink-4">{p.jersey}</span>
        <span className="truncate font-medium text-ink">{p.short_name}</span>
        <span className="shrink-0 tabular text-ink-4">{p.minutes}'</span>
      </div>
      <Bar v={p.vaep} max={maxV} label={signed(p.vaep)} side={p.team} />
      <Bar v={p.passes} max={maxP} label={String(p.passes)} muted />
      <span className={`text-right tabular ${delta > 0 ? "text-ink" : "text-ink-4"}`}>{delta > 0 ? `▲${delta}` : delta < 0 ? `▼${-delta}` : "–"}</span>
    </div>
  );
}

function Bar({ v, max, label, side, muted }: { v: number; max: number; label: string; side?: Side; muted?: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1.5 flex-1 rounded-full bg-surface-3">
        <div className="h-1.5 rounded-r-full" style={{ width: `${(Math.max(v, 0) / max) * 100}%`, background: muted ? "var(--ink-4)" : `var(--${side})` }} />
      </div>
      <span className="w-9 text-right tabular text-ink-2">{label}</span>
    </div>
  );
}

function Seg<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: [T, string][] }) {
  return (
    <div className="flex rounded-lg border border-line p-0.5">
      {options.map(([v, l]) => (
        <button key={v} onClick={() => onChange(v)}
          className={`rounded-md px-2.5 py-1 transition ${value === v ? "bg-surface-3 text-ink" : "text-ink-3 hover:text-ink-2"}`}>{l}</button>
      ))}
    </div>
  );
}
