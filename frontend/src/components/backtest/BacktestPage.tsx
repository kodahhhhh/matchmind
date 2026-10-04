import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { motion } from "motion/react";
import { scaleLinear } from "d3-scale";
import { area, line } from "d3-shape";
import { api } from "../../api/client";
import type { Backtest, BacktestStrategy } from "../../api/types";
import { Logo } from "../ui/Logo";
import { SearchButton } from "../search/SearchPalette";
import { useSize } from "../ui/useSize";

const money = (s: BacktestStrategy, v: number, signed = false) => {
  const sign = signed ? (v > 0 ? "+" : v < 0 ? "−" : "") : v < 0 ? "−" : "";
  const abs = Math.abs(v);
  return s.market === "polymarket" ? `${sign}$${abs.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : `${sign}${abs.toFixed(1)}u`;
};
const axisMoney = (s: BacktestStrategy, v: number) =>
  s.market === "polymarket" ? `$${Math.round(v).toLocaleString()}` : `${Math.round(v).toLocaleString()}u`;
const pctS = (v: number, signed = true) => `${signed && v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v * 100).toFixed(1)}%`;

export function BacktestPage() {
  const [bt, setBt] = useState<Backtest | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState(0);

  useEffect(() => { api.backtest().then(setBt).catch((e) => setErr(String(e))); }, []);

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <header className="mx-auto flex max-w-[1280px] items-center justify-between gap-3 px-5 py-5 md:px-8 md:py-6">
        <Link to="/"><Logo /></Link>
        <div className="flex items-center gap-3">
          <Link to="/" className="rounded-xl px-3 py-2 text-[13px] text-ink-3 transition hover:text-ink">Matches</Link>
          <Link to="/players" className="rounded-xl px-3 py-2 text-[13px] text-ink-3 transition hover:text-ink">Players</Link>
          <SearchButton />
        </div>
      </header>

      <section className="mx-auto max-w-[1280px] px-8 pb-8 pt-4">
        <div className="eyebrow mb-3 flex items-center gap-2"><span className="h-1.5 w-1.5 rounded-full bg-ai" />Backtest</div>
        <h1 className="display max-w-[900px] text-[40px] leading-[0.92] md:text-[60px] text-ink">Would MatchMind have<br />beaten the market?</h1>
        <p className="mt-4 max-w-[640px] text-[15.5px] leading-relaxed text-ink-2">
          We replayed our models against real prices from before and during the matches, using only information available at the time,
          and counted every bet. If we'd lost money, this page would say so.
        </p>
        {bt && <Verdict bt={bt} />}
      </section>

      {err && <div className="mx-auto max-w-[1280px] px-8 text-sm text-ink-3">Backtest results aren't available yet. <span className="text-ink-4">{err}</span></div>}

      {bt && (
        <>
          <section className="mx-auto grid max-w-[1280px] grid-cols-1 gap-4 px-8 lg:grid-cols-2">
            {headline(bt).map((s, i) => <StrategyCard key={s.id} s={s} i={i} />)}
          </section>
          <Sensitivity bt={bt} />
          <PlayerDataComparison bt={bt} />

          <section className="mx-auto max-w-[1280px] px-8 pt-10">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="display text-[28px] text-ink">Every bet</h2>
              <div className="flex rounded-xl bg-surface-2 p-1">
                {headline(bt).map((s, i) => (
                  <button key={s.id} onClick={() => setTab(i)}
                    className={`rounded-lg px-3.5 py-1.5 text-[12.5px] font-medium transition ${tab === i ? "bg-surface-4 text-ink shadow" : "text-ink-3 hover:text-ink-2"}`}>{s.name}</button>
                ))}
              </div>
            </div>
            {headline(bt)[tab] && <BetsTable s={headline(bt)[tab]} />}
          </section>

          <section className="mx-auto grid max-w-[1280px] grid-cols-1 gap-4 px-8 pb-20 pt-10 lg:grid-cols-2">
            <div className="rounded-[var(--radius)] bg-surface-1 p-5 ring-1 ring-line">
              <div className="eyebrow mb-3">Data sources</div>
              <ul className="space-y-3">
                {bt.sources.map((src) => (
                  <li key={src.name} className="flex items-start gap-3">
                    <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${src.matches ? "bg-[#3ccf8e]" : "bg-ink-4"}`} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="text-[14px] font-semibold text-ink">{src.name}</span>
                        <span className="shrink-0 text-[12px] tabular text-ink-3">{src.matches} matches</span>
                      </div>
                      <div className="text-[12.5px] leading-snug text-ink-3">{src.notes}</div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-[var(--radius)] bg-surface-1 p-5 ring-1 ring-line">
              <div className="eyebrow mb-3">How to read this</div>
              <ul className="space-y-2 text-[13px] leading-relaxed text-ink-2">
                {bt.caveats.map((c) => <li key={c} className="flex gap-2.5"><span className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-ink-3" />{c}</li>)}
              </ul>
              <div className="mt-4 text-[11.5px] text-ink-4">Generated {bt.generated_at}</div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

/** One headline strategy per market: Pinnacle at closing odds with flat stakes, Polymarket with 1¢ slippage. */
function headline(bt: Backtest): BacktestStrategy[] {
  const pick = (market: string, pref: (s: BacktestStrategy) => boolean) => {
    const xs = bt.strategies.filter((s) => s.market === market);
    return xs.find(pref) ?? xs[0];
  };
  return [
    pick("pinnacle", (s) => /closing/i.test(s.name) && /1 unit|flat/i.test(s.name)),
    pick("polymarket", (s) => /1¢|1c|\+1/i.test(s.name)),
  ].filter((s): s is BacktestStrategy => !!s);
}

function Sensitivity({ bt }: { bt: Backtest }) {
  const head = new Set(headline(bt).map((s) => s.id));
  const rest = bt.strategies.filter((s) => !head.has(s.id));
  if (!rest.length) return null;
  return (
    <section className="mx-auto max-w-[1280px] px-8 pt-6">
      <div className="eyebrow mb-2">Sensitivity checks</div>
      <div className="overflow-hidden rounded-[var(--radius)] bg-surface-1 ring-1 ring-line">
        {rest.map((s, i) => (
          <div key={s.id} className={`grid grid-cols-[2fr_0.6fr_0.8fr_0.8fr_0.7fr_1.2fr] items-center gap-3 px-5 py-2.5 text-[13px] ${i ? "border-t border-line" : ""}`}>
            <span className="font-medium text-ink">{s.name}</span>
            <span className="tabular text-ink-3">{s.n_bets} bets</span>
            <span className="tabular text-ink-3">{money(s, s.staked)} staked</span>
            <span className={`font-semibold tabular ${s.pnl >= 0 ? "text-[#3ccf8e]" : "text-[#ff6b6b]"}`}>{money(s, s.pnl, true)}</span>
            <span className="tabular text-ink">{pctS(s.roi)}</span>
            <span className="tabular text-ink-3">95% CI {pctS(s.roi_ci95[0])} to {pctS(s.roi_ci95[1])}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

/** Before/after adding squad data (starting-XI market value, age, missing regulars) to the models. */
function PlayerDataComparison({ bt }: { bt: Backtest }) {
  if (!bt.comparison?.length) return null;
  const byId = new Map(bt.strategies.map((s) => [s.id, s]));
  const pm = bt.comparison.find((c) => c.strategy_id.startsWith("pinnacle"));
  return (
    <section className="mx-auto max-w-[1280px] px-8 pt-10">
      <h2 className="display text-[28px] text-ink">Did player data help?</h2>
      <p className="mt-1 max-w-[760px] text-[13.5px] leading-relaxed text-ink-3">
        We added squad information from Transfermarkt (CC0): each starting XI's market value at kick-off, age, caps, and which regular starters were missing.
        {pm && <> It made the pre-match model more accurate (Brier {pm.before.brier_model.toFixed(3)} → <span className="font-semibold text-ink">{pm.after.brier_model.toFixed(3)}</span>, lower is better), but not more profitable. The in-play version got worse, so we kept the original.</>}
      </p>
      <div className="mt-4 overflow-hidden rounded-[var(--radius)] bg-surface-1 ring-1 ring-line">
        <div className="grid grid-cols-[2fr_1fr_1fr_1fr_1fr] gap-3 border-b border-line px-5 py-2.5 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-ink-4">
          <span>Strategy</span><span>Brier before → after</span><span>ROI before</span><span>ROI after</span><span>95% CI after</span>
        </div>
        {bt.comparison.map((c, i) => {
          const s = byId.get(c.strategy_id);
          const better = c.after.brier_model < c.before.brier_model - 1e-6;
          return (
            <div key={c.strategy_id} className={`grid grid-cols-[2fr_1fr_1fr_1fr_1fr] items-center gap-3 px-5 py-2.5 text-[13px] ${i ? "border-t border-line" : ""}`}>
              <span className="font-medium text-ink">{s?.name ?? c.strategy_id}</span>
              <span className="tabular text-ink-2">{c.before.brier_model.toFixed(3)} → <span className={better ? "font-semibold text-[#3ccf8e]" : "text-ink-3"}>{c.after.brier_model.toFixed(3)}</span></span>
              <span className="tabular text-ink-3">{pctS(c.before.roi)}</span>
              <span className={`font-semibold tabular ${c.after.roi >= 0 ? "text-[#3ccf8e]" : "text-[#ff6b6b]"}`}>{pctS(c.after.roi)}</span>
              <span className="tabular text-ink-3">{pctS(c.after.roi_ci95[0])} to {pctS(c.after.roi_ci95[1])}</span>
            </div>
          );
        })}
      </div>
      {bt.model_versions && <div className="mt-2 text-[11px] text-ink-4">Models: {bt.model_versions.before} → {bt.model_versions.after}</div>}
    </section>
  );
}

function Verdict({ bt }: { bt: Backtest }) {
  const sig = bt.strategies.filter((s) => s.roi_ci95[0] > 0);
  const neg = bt.strategies.filter((s) => s.roi_ci95[1] < 0);
  const text = sig.length
    ? `Yes, with ${sig.map((s) => s.name).join(" and ")} profitable beyond the noise.`
    : neg.length === bt.strategies.length
      ? "No. Both strategies lost money; the markets were sharper."
      : "Not conclusively. Every result sits inside its 95% confidence interval around zero.";
  return (
    <div className="mt-6 inline-flex items-center gap-3 rounded-2xl bg-surface-1 px-4 py-3 ring-1 ring-line">
      <span className={`h-2.5 w-2.5 rounded-full ${sig.length ? "bg-[#3ccf8e]" : neg.length === bt.strategies.length ? "bg-[#e5484d]" : "bg-[#f2c94c]"}`} />
      <span className="text-[14.5px] font-medium text-ink">{text}</span>
    </div>
  );
}

function StrategyCard({ s, i }: { s: BacktestStrategy; i: number }) {
  const up = s.pnl >= 0;
  const brierBetter = s.brier_model < s.brier_market;
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.08 }}
      className="flex flex-col rounded-[var(--radius)] bg-surface-1 p-5 ring-1 ring-line">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[16px] font-semibold text-ink">{s.name}</div>
          <div className="mt-0.5 text-[12.5px] text-ink-3">{s.eval_period} · {s.n_matches} matches</div>
        </div>
        <span className="shrink-0 rounded-lg bg-surface-3 px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-ink-2">{s.market === "polymarket" ? "Polymarket" : "Pinnacle"}</span>
      </div>

      <div className="mt-5 flex items-end gap-6">
        <div>
          <div className="text-[12px] text-ink-3">Profit / loss</div>
          <div className={`display text-[52px] leading-none ${up ? "text-[#3ccf8e]" : "text-[#ff6b6b]"}`}>{money(s, s.pnl, true)}</div>
        </div>
        <div className="pb-1">
          <div className="text-[12px] text-ink-3">ROI</div>
          <div className="display text-[30px] leading-none text-ink">{pctS(s.roi)}</div>
        </div>
        <div className="ml-auto pb-1 text-right">
          <div className="text-[12px] text-ink-3">95% CI on ROI</div>
          <CiBar lo={s.roi_ci95[0]} hi={s.roi_ci95[1]} est={s.roi} />
        </div>
      </div>

      <EquityChart s={s} />

      <div className="mt-4 grid grid-cols-3 gap-3 sm:grid-cols-6">
        <Stat label="Bets" value={String(s.n_bets)} />
        <Stat label="Staked" value={money(s, s.staked)} />
        <Stat label="Hit rate" value={pctS(s.hit_rate, false)} />
        <Stat label="Max drawdown" value={money(s, s.max_drawdown)} />
        <Stat label="CLV" value={s.clv == null ? "—" : pctS(s.clv)} />
        <Stat label="Brier" value={`${s.brier_model.toFixed(3)}`} sub={`market ${s.brier_market.toFixed(3)}`} good={brierBetter} />
      </div>
      <p className="mt-4 text-[12.5px] leading-relaxed text-ink-3">{s.description}</p>
    </motion.div>
  );
}

function Stat({ label, value, sub, good }: { label: string; value: string; sub?: string; good?: boolean }) {
  return (
    <div className="rounded-xl bg-surface-2 px-3 py-2">
      <div className="text-[10.5px] text-ink-3">{label}</div>
      <div className="text-[14px] font-semibold tabular text-ink">{value}</div>
      {sub && <div className={`text-[10.5px] tabular ${good ? "text-[#3ccf8e]" : "text-ink-4"}`}>{sub}</div>}
    </div>
  );
}

function CiBar({ lo, hi, est }: { lo: number; hi: number; est: number }) {
  const span = Math.max(Math.abs(lo), Math.abs(hi), 0.05) * 1.15;
  const x = scaleLinear().domain([-span, span]).range([24, 150]);
  return (
    <svg width={174} height={30} className="mt-1" role="img" aria-label={`ROI 95% interval ${pctS(lo)} to ${pctS(hi)}`}>
      <line x1={x(0)} x2={x(0)} y1={2} y2={20} stroke="var(--ink-4)" />
      <rect x={x(lo)} y={8} width={Math.max(x(hi) - x(lo), 2)} height={6} rx={3} fill="var(--ai)" opacity={0.35} />
      <circle cx={x(est)} cy={11} r={4} fill="var(--ai)" stroke="var(--surface-1)" strokeWidth={2} />
      <text x={x(lo)} y={29} fontSize={9.5} fill="var(--ink-3)" textAnchor="middle">{pctS(lo)}</text>
      <text x={x(hi)} y={29} fontSize={9.5} fill="var(--ink-3)" textAnchor="middle">{pctS(hi)}</text>
    </svg>
  );
}

function EquityChart({ s }: { s: BacktestStrategy }) {
  const [ref, { width }] = useSize<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const H = 170, P = { l: 44, r: 10, t: 12, b: 20 };
  const pts = s.equity;
  const geo = useMemo(() => {
    if (!width || pts.length < 2) return null;
    const vals = pts.map((p) => p.bankroll);
    // the curve starts from its pre-bet bankroll (0 for cumulative P&L, the bankroll for Kelly)
    const ref = /^start$/i.test(pts[0].label) ? vals[0] : 0;
    const lo = Math.min(ref, ...vals), hi = Math.max(ref, ...vals);
    const pad = (hi - lo) * 0.08 || 1;
    const x = scaleLinear().domain([0, pts.length - 1]).range([P.l, width - P.r]);
    const y = scaleLinear().domain([lo - pad, hi + pad]).nice(4).range([H - P.b, P.t]);
    return { x, y, ref };
  }, [width, pts, P.l, P.r, P.t, P.b]);
  const up = s.pnl >= 0;
  const stroke = up ? "#3ccf8e" : "#ff6b6b";
  return (
    <div ref={ref} className="relative mt-4">
      {geo && (
        <svg width={width} height={H} role="img" aria-label={`Cumulative profit over ${pts.length} bets`}
          onPointerMove={(e) => { const i = Math.round(geo.x.invert(e.nativeEvent.offsetX)); setHover(Math.max(0, Math.min(pts.length - 1, i))); }}
          onPointerLeave={() => setHover(null)}>
          {geo.y.ticks(4).map((t) => (
            <g key={t}>
              <line x1={P.l} x2={width - P.r} y1={geo.y(t)} y2={geo.y(t)} stroke="var(--grid)" />
              <text x={P.l - 8} y={geo.y(t) + 3.5} fontSize={10} fill="var(--ink-4)" textAnchor="end" className="tabular">{axisMoney(s, t)}</text>
            </g>
          ))}
          <line x1={P.l} x2={width - P.r} y1={geo.y(geo.ref)} y2={geo.y(geo.ref)} stroke="var(--ink-4)" />
          <text x={width - P.r} y={geo.y(geo.ref) - 4} fontSize={9.5} fill="var(--ink-4)" textAnchor="end">start</text>
          <path d={area<(typeof pts)[number]>().x((_, i) => geo.x(i)).y0(geo.y(geo.ref)).y1((p) => geo.y(p.bankroll))(pts) ?? ""} fill={stroke} opacity={0.1} />
          <path d={line<(typeof pts)[number]>().x((_, i) => geo.x(i)).y((p) => geo.y(p.bankroll))(pts) ?? ""} fill="none" stroke={stroke} strokeWidth={2} strokeLinejoin="round" />
          <circle cx={geo.x(pts.length - 1)} cy={geo.y(pts[pts.length - 1].bankroll)} r={4} fill={stroke} stroke="var(--surface-1)" strokeWidth={2} />
          <text x={P.l} y={H - 4} fontSize={10} fill="var(--ink-4)">{pts[0].label}</text>
          <text x={width - P.r} y={H - 4} fontSize={10} fill="var(--ink-4)" textAnchor="end">{pts[pts.length - 1].label}</text>
          {hover != null && (
            <g pointerEvents="none">
              <line x1={geo.x(hover)} x2={geo.x(hover)} y1={P.t} y2={H - P.b} stroke="var(--ink)" strokeOpacity={0.4} />
              <circle cx={geo.x(hover)} cy={geo.y(pts[hover].bankroll)} r={4} fill="var(--ink)" />
            </g>
          )}
        </svg>
      )}
      {geo && hover != null && (
        <div className="glass pointer-events-none absolute top-0 rounded-xl px-3 py-2 text-xs shadow-xl"
          style={{ left: Math.min(geo.x(hover) + 10, width - 200) }}>
          <div className="font-semibold tabular text-ink">{money(s, pts[hover].bankroll, true)}</div>
          <div className="max-w-[180px] truncate text-ink-3">{pts[hover].label}</div>
        </div>
      )}
    </div>
  );
}

function BetsTable({ s }: { s: BacktestStrategy }) {
  return (
    <div className="overflow-hidden rounded-[var(--radius)] bg-surface-1 ring-1 ring-line">
      <div className="grid grid-cols-[1.6fr_0.7fr_0.5fr_0.7fr_0.7fr_0.6fr_0.7fr_0.7fr] gap-3 border-b border-line px-5 py-2.5 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-ink-4">
        <span>Match</span><span>Bet</span><span>Min</span><span className="text-right">Model</span><span className="text-right">Market</span>
        <span className="text-right">Edge</span><span className="text-right">{s.market === "polymarket" ? "Price" : "Odds"}</span><span className="text-right">P&L</span>
      </div>
      <div className="scroll-thin max-h-[440px] overflow-y-auto">
        {s.bets.map((b, i) => (
          <div key={i} className="grid grid-cols-[1.6fr_0.7fr_0.5fr_0.7fr_0.7fr_0.6fr_0.7fr_0.7fr] items-center gap-3 border-b border-line/60 px-5 py-2 text-[13px] transition hover:bg-surface-2">
            <Link to={`/match/${encodeURIComponent(b.match_id)}`} className="truncate font-medium text-ink hover:underline">{b.label}</Link>
            <span className="capitalize text-ink-2">{b.side} {b.outcome}</span>
            <span className="tabular text-ink-3">{b.minute != null ? `${b.minute}'` : "pre"}</span>
            <span className="text-right tabular text-ink">{(b.model_prob * 100).toFixed(0)}%</span>
            <span className="text-right tabular text-ink-2">{(b.market_prob * 100).toFixed(0)}%</span>
            <span className="text-right tabular text-ai">+{((b.model_prob - b.market_prob) * 100).toFixed(0)}</span>
            <span className="text-right tabular text-ink-2">{s.market === "polymarket" ? `${Math.round(b.price_or_odds * 100)}¢` : b.price_or_odds.toFixed(2)}</span>
            <span className={`text-right font-semibold tabular ${b.pnl >= 0 ? "text-[#3ccf8e]" : "text-[#ff6b6b]"}`}>{money(s, b.pnl, true)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
