import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { scaleLinear, scaleLog } from "d3-scale";
import { api } from "../../api/client";
import type { LeaderboardRow } from "../../api/types";
import { usePlayerUi } from "../../store/ui";
import { Logo } from "../ui/Logo";
import { SearchButton } from "../search/SearchPalette";
import { useSize } from "../ui/useSize";
import { eur } from "./PlayerDrawer";

const METRICS: [string, string][] = [["vaep_per90", "VAEP / 90"], ["xg", "xG"], ["prog_per90", "Progression / 90"]];

/** Value added vs market value: who did the market underrate? */
export function LeaderboardPage() {
  const [metric, setMetric] = useState("vaep_per90");
  const [rows, setRows] = useState<LeaderboardRow[]>([]);
  const [comp, setComp] = useState("");
  const [err, setErr] = useState(false);
  const openPlayer = usePlayerUi((s) => s.openPlayer);

  useEffect(() => {
    api.leaderboard({ metric, min_minutes: 900 }).then((r) => { setRows(r.rows); setErr(false); }).catch(() => setErr(true));
  }, [metric]);

  const comps = useMemo(() => [...new Set(rows.map((r) => `${r.competition} ${r.season}`))].sort(), [rows]);
  const shown = useMemo(() => rows.filter((r) => !comp || `${r.competition} ${r.season}` === comp), [rows, comp]);
  const underrated = useMemo(() => [...shown].filter((r) => r.underrated_score != null).sort((a, b) => b.underrated_score! - a.underrated_score!).slice(0, 8), [shown]);
  const label = METRICS.find(([k]) => k === metric)?.[1] ?? metric;

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <header className="mx-auto flex max-w-[1280px] items-center justify-between px-8 py-6">
        <Link to="/"><Logo /></Link>
        <div className="flex items-center gap-3">
          <Link to="/" className="rounded-xl px-3 py-2 text-[13px] text-ink-3 transition hover:text-ink">Matches</Link>
          <Link to="/backtest" className="rounded-xl px-3 py-2 text-[13px] text-ink-3 transition hover:text-ink">Backtest</Link>
          <SearchButton />
        </div>
      </header>

      <section className="mx-auto max-w-[1280px] px-8 pb-6 pt-4">
        <div className="eyebrow mb-3 flex items-center gap-2"><span className="h-1.5 w-1.5 rounded-full bg-ai" />Players</div>
        <h1 className="display max-w-[900px] text-[60px] leading-[0.92] text-ink">Who did the<br />market underrate?</h1>
        <p className="mt-4 max-w-[640px] text-[15.5px] leading-relaxed text-ink-2">
          Every player with 900+ minutes, ranked by the value our models say they added, against what the transfer market said they were worth at the time.
        </p>
        <div className="mt-6 flex flex-wrap items-center gap-2">
          <div className="flex rounded-xl bg-surface-2 p-1">
            {METRICS.map(([k, l]) => (
              <button key={k} onClick={() => setMetric(k)} className={`rounded-lg px-3 py-1.5 text-[12.5px] font-medium transition ${metric === k ? "bg-surface-4 text-ink shadow" : "text-ink-3 hover:text-ink-2"}`}>{l}</button>
            ))}
          </div>
          <select value={comp} onChange={(e) => setComp(e.target.value)}
            className="rounded-xl bg-surface-2 px-3 py-2 text-[12.5px] text-ink ring-1 ring-line focus:outline-none">
            <option value="">All competitions</option>
            {comps.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <span className="ml-auto text-[12px] text-ink-4">{shown.length} players</span>
        </div>
      </section>

      {err && <div className="mx-auto max-w-[1280px] px-8 text-sm text-ink-3">Player data isn't available yet.</div>}

      <section className="mx-auto grid max-w-[1280px] grid-cols-1 gap-4 px-8 pb-20 lg:grid-cols-[1.5fr_1fr]">
        <div className="rounded-[var(--radius)] bg-surface-1 p-5 ring-1 ring-line">
          <div className="mb-2 flex items-baseline justify-between">
            <span className="text-[14px] font-semibold text-ink">{label} vs market value</span>
            <span className="text-[11.5px] text-ink-4">top-left = underrated · click a dot</span>
          </div>
          <Scatter rows={shown} label={label} highlight={new Set(underrated.map((r) => r.player_id + r.season))} onPick={openPlayer} />
        </div>
        <div className="rounded-[var(--radius)] bg-surface-1 p-5 ring-1 ring-line">
          <div className="eyebrow mb-3">Most underrated</div>
          <ol className="space-y-1">
            {underrated.map((r, i) => (
              <li key={r.player_id + r.season}>
                <button onClick={() => openPlayer(r.player_id)} className="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left transition hover:bg-surface-2">
                  <span className="display w-6 text-[18px] text-ink-4">{i + 1}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[14px] font-semibold text-ink">{r.name}</span>
                    <span className="block truncate text-[11.5px] text-ink-3">{r.team} · {r.competition} {r.season}</span>
                  </span>
                  <span className="text-right">
                    <span className="block text-[13px] font-semibold tabular text-ai">{r.value.toFixed(2)}</span>
                    <span className="block text-[11px] tabular text-ink-3">{eur(r.market_value_eur)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
          <p className="mt-3 text-[11px] leading-relaxed text-ink-4">Underrated = how many places higher a player ranks on {label} than on market value, within the same filter. Market values from Transfermarkt (CC0 dataset).</p>
        </div>
      </section>
    </div>
  );
}

function Scatter({ rows, label, highlight, onPick }: { rows: LeaderboardRow[]; label: string; highlight: Set<string>; onPick: (id: number) => void }) {
  const [ref, { width }] = useSize<HTMLDivElement>();
  const [hover, setHover] = useState<LeaderboardRow | null>(null);
  const H = 420, P = { l: 52, r: 16, t: 12, b: 34 };
  const pts = rows.filter((r) => r.market_value_eur && r.market_value_eur > 0);
  if (!width || !pts.length) return <div ref={ref} className="h-[420px]" />;
  const vals = pts.map((r) => r.market_value_eur!);
  const x = scaleLog().domain([Math.min(...vals) * 0.8, Math.max(...vals) * 1.2]).range([P.l, width - P.r]);
  const y = scaleLinear().domain([Math.min(0, ...pts.map((r) => r.value)), Math.max(...pts.map((r) => r.value)) * 1.08]).nice(5).range([H - P.b, P.t]);
  const xt = [1e5, 1e6, 1e7, 1e8].filter((t) => t >= x.domain()[0] && t <= x.domain()[1]);
  return (
    <div ref={ref} className="relative">
      <svg width={width} height={H} role="img" aria-label={`${label} against market value`}>
        {y.ticks(5).map((t) => (
          <g key={t}>
            <line x1={P.l} x2={width - P.r} y1={y(t)} y2={y(t)} stroke="var(--grid)" />
            <text x={P.l - 8} y={y(t) + 3.5} fontSize={10} fill="var(--ink-4)" textAnchor="end" className="tabular">{t.toFixed(2)}</text>
          </g>
        ))}
        {xt.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={P.t} y2={H - P.b} stroke="var(--grid)" />
            <text x={x(t)} y={H - P.b + 16} fontSize={10} fill="var(--ink-4)" textAnchor="middle">{eur(t)}</text>
          </g>
        ))}
        <text x={width - P.r} y={H - 4} fontSize={10.5} fill="var(--ink-3)" textAnchor="end">market value (log scale)</text>
        <text x={P.l} y={P.t - 2} fontSize={10.5} fill="var(--ink-3)">{label}</text>
        {pts.map((r) => {
          const hl = highlight.has(r.player_id + r.season);
          return (
            <g key={r.player_id + r.season} style={{ cursor: "pointer" }} onClick={() => onPick(r.player_id)}
              onPointerEnter={() => setHover(r)} onPointerLeave={() => setHover(null)}>
              <circle cx={x(r.market_value_eur!)} cy={y(r.value)} r={12} fill="transparent" />
              <circle cx={x(r.market_value_eur!)} cy={y(r.value)} r={hl ? 6 : 4.5} fill={hl ? "var(--ai)" : "var(--ink-3)"} fillOpacity={hl ? 1 : 0.55}
                stroke="var(--surface-1)" strokeWidth={2} />
            </g>
          );
        })}
        {(() => {
          // label the highlighted players, skipping any label that would collide with one already placed
          const placed: { x: number; y: number }[] = [];
          return pts.filter((r) => highlight.has(r.player_id + r.season)).map((r) => {
            const lx = x(r.market_value_eur!) + 9, ly = y(r.value) + 4;
            if (placed.some((q) => Math.abs(q.y - ly) < 14 && Math.abs(q.x - lx) < 90)) return null;
            placed.push({ x: lx, y: ly });
            return <text key={`l-${r.player_id}${r.season}`} x={lx} y={ly} fontSize={11} fill="var(--ink-2)" pointerEvents="none">{r.short_name}</text>;
          });
        })()}
      </svg>
      {hover && (
        <div className="glass pointer-events-none absolute rounded-xl px-3 py-2 text-xs shadow-xl"
          style={{ left: Math.min(x(hover.market_value_eur!) + 12, width - 210), top: Math.max(y(hover.value) - 50, 0) }}>
          <div className="font-semibold text-ink">{hover.name}</div>
          <div className="text-ink-3">{hover.team} · {hover.competition} {hover.season}</div>
          <div className="mt-1 tabular text-ink-2"><span className="font-semibold text-ai">{hover.value.toFixed(2)}</span> {label} · {eur(hover.market_value_eur)} · {hover.minutes}'</div>
        </div>
      )}
    </div>
  );
}
