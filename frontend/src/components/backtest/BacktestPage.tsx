import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { motion, MotionConfig, useReducedMotion } from "motion/react";
import { CheckCircle, Scales, XCircle } from "@phosphor-icons/react";
import { scaleLinear } from "d3-scale";
import { area, line } from "d3-shape";
import { api } from "../../api/client";
import type { Backtest, BacktestStrategy } from "../../api/types";
import { LoadError, PageFooter } from "../ui/PageFooter";
import { Line, Stagger } from "../ui/motion";
import { SiteHeader } from "../ui/SiteHeader";
import { useSize } from "../ui/useSize";

const EASE = [0.22, 1, 0.36, 1] as const;
const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
const stampFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC" });

// API text uses dashes for ranges and fixtures; the interface uses "to" and "v" instead
const plain = (s: string) => s.replace(/(\d)\s*[–—]\s*(\d)/g, "$1 to $2").replace(/\s+[–—]\s+/g, " v ").replace(/[–—]/g, "-");
const pointLabel = (l: string) => (/^\d{4}-\d{2}-\d{2}$/.test(l) ? dateFmt.format(new Date(l)) : l);

const sign = (v: number, signed: boolean) => (v < 0 ? "−" : signed && v > 0 ? "+" : "");
const isPoly = (s: BacktestStrategy) => s.market === "polymarket";
/** Compact money for tables: "+$2,306" or "−10.3u". */
const money = (s: BacktestStrategy, v: number, signed = false) => {
  const abs = Math.abs(v);
  return isPoly(s) ? `${sign(v, signed)}$${abs.toLocaleString("en-GB", { maximumFractionDigits: 0 })}` : `${sign(v, signed)}${abs.toLocaleString("en-GB", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}u`;
};
const axisMoney = (s: BacktestStrategy, v: number) =>
  isPoly(s) ? `$${Math.round(v).toLocaleString("en-GB")}` : `${Math.round(v).toLocaleString("en-GB")}u`;
/** Profit green, loss red; the sign always carries the meaning too, so colour is never the only cue. */
const pnlTone = (v: number) => (v > 0 ? "text-positive" : v < 0 ? "text-negative" : "text-ink");
const pctS = (v: number, signed = true) => `${sign(v, signed)}${Math.abs(v * 100).toFixed(1)}%`;

/** Renders the API's shouted "NOT" as a quiet bold "not", keeping the emphasis. */
function Emph({ text }: { text: string }) {
  // contract sides read as words: "YES/NO" becomes "Yes/No"
  const parts = plain(text).replace(/\bYES\b/g, "Yes").replace(/\bNO\b/g, "No").split(/\bNOT\b/);
  return <>{parts.map((p, i) => <span key={i}>{i > 0 && <strong className="font-semibold text-ink">not</strong>}{p}</span>)}</>;
}

export function BacktestPage() {
  const [bt, setBt] = useState<Backtest | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const scroller = useRef<HTMLDivElement>(null);

  const fetchBacktest = useCallback(() => {
    api.backtest().then((b) => { setBt(b); setStatus("ready"); }).catch(() => setStatus("error"));
  }, []);
  useEffect(fetchBacktest, [fetchBacktest]);
  const load = () => { setStatus("loading"); fetchBacktest(); };

  const head = useMemo(() => (bt ? headline(bt) : []), [bt]);

  return (
    <MotionConfig reducedMotion="user">
      <div ref={scroller} className="scroll-thin h-full overflow-y-auto">
        <a href="#results" className="sr-only rounded-full bg-ink px-4 py-2 text-[13px] font-medium text-bg focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-30">
          Skip to results
        </a>
        <SiteHeader scroller={scroller} />

        <main>
          <section className="mx-auto grid max-w-[1280px] grid-cols-1 items-start gap-12 px-5 pb-4 pt-8 md:px-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:pt-14">
            <Stagger onMount>
              <Line n={1} as="h1" className="max-w-[16ch] text-balance text-[38px] font-semibold leading-[1.06] tracking-[-0.04em] text-ink md:text-[48px]">
                Would MatchMind have beaten the market?
              </Line>
              <Line n={2} as="p" className="mt-6 max-w-[48ch] text-pretty text-[17px] leading-[1.6] text-ink-2">
                We replayed our models against real prices from before and during matches, using only what was known at the time, and counted every bet. If we had lost money, this page would say so.
              </Line>
              <Line n={3} as="div" className="mt-8">
                {bt ? <Verdict bt={bt} /> : <div className="h-[60px] max-w-[440px] rounded-2xl bg-surface-1 ring-1 ring-line motion-safe:animate-pulse" aria-hidden />}
              </Line>
            </Stagger>
            {bt ? <ForestPlot bt={bt} head={head} /> : status === "loading" && <div className="h-[420px] rounded-[20px] bg-surface-1 ring-1 ring-line motion-safe:animate-pulse" aria-hidden />}
          </section>

          <div id="results" className="scroll-mt-20">
            {status === "error" && (
              <div className="mx-auto max-w-[1280px] px-5 pt-16 md:px-8">
                <LoadError title="Unable to load the backtest" onRetry={load} />
              </div>
            )}

            {status === "loading" && !bt && (
              <div className="mx-auto grid max-w-[1280px] grid-cols-1 gap-3 px-5 pt-28 md:px-8 lg:grid-cols-2" aria-hidden>
                {[0, 1].map((i) => <div key={i} className="h-[560px] rounded-[20px] bg-surface-1 ring-1 ring-line motion-safe:animate-pulse" />)}
              </div>
            )}

            {bt && (
              <>
                <Section id="headline" title="The two headline strategies"
                  intro="One per market: Pinnacle at closing odds with flat stakes, and Polymarket with a cent of slippage on every fill.">
                  <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                    {head.map((s, i) => <InView key={s.id} i={i}><StrategyCard s={s} /></InView>)}
                  </div>
                </Section>
                <Sensitivity bt={bt} />
                <PlayerDataComparison bt={bt} />
                <EveryBet head={head} />
                <Sources bt={bt} />
              </>
            )}
          </div>
        </main>

        <PageFooter />
      </div>
    </MotionConfig>
  );
}

function Section({ id, title, intro, children, aside }: { id: string; title: string; intro?: ReactNode; children: ReactNode; aside?: ReactNode }) {
  return (
    <section aria-labelledby={`${id}-title`} className="mx-auto max-w-[1280px] px-5 pt-24 md:px-8 md:pt-28">
      <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
        <Stagger>
          <Line n={1} as="h2" className="text-balance text-[30px] font-semibold leading-[1.1] tracking-[-0.03em] text-ink md:text-[38px]">
            <span id={`${id}-title`}>{title}</span>
          </Line>
          {intro && <Line n={2} as="p" className="mt-3 max-w-[64ch] text-pretty text-[15.5px] leading-[1.6] text-ink-3">{intro}</Line>}
        </Stagger>
        {aside}
      </div>
      <div className="mt-10">{children}</div>
    </section>
  );
}

function InView({ children, i = 0, className }: { children: ReactNode; i?: number; className?: string }) {
  return (
    <motion.div className={className} initial={{ opacity: 0, y: 12, filter: "blur(3px)" }} whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      viewport={{ once: true, amount: 0.15 }} transition={{ duration: 0.5, delay: i * 0.06, ease: EASE }}>
      {children}
    </motion.div>
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

function Verdict({ bt }: { bt: Backtest }) {
  const sig = bt.strategies.filter((s) => s.roi_ci95[0] > 0);
  const neg = bt.strategies.filter((s) => s.roi_ci95[1] < 0);
  const allNeg = neg.length === bt.strategies.length;
  const text = sig.length
    ? `Yes, with ${sig.map((s) => s.name).join(" and ")} profitable beyond the noise.`
    : allNeg
      ? "No. Both strategies lost money; the markets were sharper."
      : "Not conclusively. Every result sits inside its 95% confidence interval around zero.";
  const Icon = sig.length ? CheckCircle : allNeg ? XCircle : Scales;
  return (
    <p className="inline-flex max-w-[52ch] items-start gap-3 rounded-2xl bg-surface-1 px-4 py-3.5 text-[15px] font-medium leading-[1.45] text-ink ring-1 ring-line">
      <Icon size={20} weight="regular" className="mt-px shrink-0 text-ink-2" aria-hidden />
      <span><span className="sr-only">Verdict: </span>{text}</span>
    </p>
  );
}

/** Every strategy's return on stake with its 95% interval, on one shared axis with break-even marked. */
function ForestPlot({ bt, head }: { bt: Backtest; head: BacktestStrategy[] }) {
  const [ref, { width }] = useSize<HTMLDivElement>();
  const [hover, setHover] = useState<string | null>(null);
  const reduce = useReducedMotion();
  const headIds = new Set(head.map((s) => s.id));
  // headline strategies first, then the sensitivity checks
  const rows = [...head, ...bt.strategies.filter((s) => !headIds.has(s.id))];
  const lo = Math.min(0, ...rows.map((s) => s.roi_ci95[0]));
  const hi = Math.max(0, ...rows.map((s) => s.roi_ci95[1]));
  const x = scaleLinear().domain([lo, hi]).nice(5).range([6, Math.max(7, width - 6)]);
  const ticks = x.ticks(5);

  return (
    <figure className="rounded-[20px] bg-surface-1 p-6 ring-1 ring-line md:p-8">
      <figcaption>
        <h2 className="text-[17px] font-semibold tracking-[-0.015em] text-ink">Return on stake, with 95% intervals</h2>
        <p className="mt-1.5 text-[13.5px] leading-[1.55] text-ink-3">A bar that crosses break-even means the result could be luck.</p>
      </figcaption>
      <div ref={ref} className="mt-6">
        <ul className="space-y-3.5">
          {rows.map((s, i) => {
            const isHead = headIds.has(s.id);
            const on = hover === s.id;
            return (
              <li key={s.id} onPointerEnter={() => setHover(s.id)} onPointerLeave={() => setHover(null)}
                aria-label={`${s.name}: return ${pctS(s.roi)}, 95% interval ${pctS(s.roi_ci95[0])} to ${pctS(s.roi_ci95[1])}`}>
                <div className="flex flex-col gap-0.5 text-[13px] sm:flex-row sm:items-baseline sm:justify-between sm:gap-3">
                  <span className={`sm:truncate ${isHead ? "font-medium text-ink" : "text-ink-3"}`}>{s.name}</span>
                  <span className={`tabular shrink-0 transition-colors duration-150 ${on ? "text-ink" : "text-ink-3"}`}>
                    {pctS(s.roi)} <span className={on ? "text-ink-2" : "text-ink-4"}>({pctS(s.roi_ci95[0])} to {pctS(s.roi_ci95[1])})</span>
                  </span>
                </div>
                {width > 0 && (
                  <svg width={width} height={14} className="mt-1.5 block overflow-visible" aria-hidden>
                    <line x1={x(lo)} x2={x(hi)} y1={7} y2={7} stroke="var(--grid)" strokeWidth={1} />
                    <line x1={x(0)} x2={x(0)} y1={-1} y2={15} stroke="var(--ink-4)" strokeWidth={1} />
                    <motion.rect y={3} height={8} rx={4} fill={isHead ? "var(--ink-2)" : "var(--ink-4)"} fillOpacity={on ? 0.9 : 0.6}
                      initial={reduce ? false : { x: x(0), width: 0 }} whileInView={{ x: x(s.roi_ci95[0]), width: Math.max(2, x(s.roi_ci95[1]) - x(s.roi_ci95[0])) }}
                      viewport={{ once: true }} transition={{ duration: 0.8, delay: 0.1 + i * 0.04, ease: EASE }} />
                    <motion.circle cy={7} r={4.5} fill={isHead ? "var(--ink)" : "var(--ink-2)"} stroke="var(--surface-1)" strokeWidth={2}
                      initial={reduce ? false : { cx: x(0), opacity: 0 }} whileInView={{ cx: x(s.roi), opacity: 1 }}
                      viewport={{ once: true }} transition={{ duration: 0.8, delay: 0.1 + i * 0.04, ease: EASE }} />
                  </svg>
                )}
              </li>
            );
          })}
        </ul>
        {width > 0 && (
          <div className="relative mt-3 h-10" aria-hidden>
            {ticks.map((t) => (
              <span key={t} className="tabular absolute top-1 -translate-x-1/2 text-[11.5px] text-ink-3" style={{ left: x(t) }}>
                {t === 0 ? "0%" : pctS(t).replace(".0%", "%")}
              </span>
            ))}
            <span className="absolute top-5 -translate-x-1/2 whitespace-nowrap text-[11.5px] font-medium text-ink-2" style={{ left: Math.min(Math.max(x(0), 40), width - 40) }}>Break even</span>
          </div>
        )}
      </div>
    </figure>
  );
}

function StrategyCard({ s }: { s: BacktestStrategy }) {
  const brierBetter = s.brier_model < s.brier_market;
  const abs = Math.abs(s.pnl);
  return (
    <article className="flex h-full flex-col rounded-[20px] bg-surface-1 p-6 ring-1 ring-line md:p-8">
      <h3 className="text-[19px] font-semibold tracking-[-0.015em] text-ink">{s.name}</h3>
      <p className="mt-1 text-[14px] text-ink-3">{s.n_matches} matches, {plain(s.eval_period)}</p>

      <dl className="mt-7 flex flex-wrap items-end gap-x-10 gap-y-5">
        <div className="flex flex-col-reverse justify-end gap-1.5">
          <dt className="text-[13px] text-ink-3">Profit or loss</dt>
          <dd className="leading-none text-ink">
            <span className={`numeral text-[46px] leading-none ${pnlTone(s.pnl)}`}>{sign(s.pnl, true)}{isPoly(s) && "$"}{isPoly(s) ? abs.toLocaleString("en-GB", { maximumFractionDigits: 0 }) : abs.toFixed(1)}</span>
            {!isPoly(s) && <span className="ml-1.5 text-[15px] font-medium text-ink-3">units</span>}
          </dd>
        </div>
        <div className="flex flex-col-reverse justify-end gap-1.5">
          <dt className="text-[13px] text-ink-3">Return on stake</dt>
          <dd className="numeral text-[32px] leading-none text-ink-2">{pctS(s.roi)}</dd>
        </div>
        <div className="flex flex-col-reverse justify-end gap-1.5">
          <dt className="text-[13px] text-ink-3">95% interval</dt>
          <dd className="tabular pb-0.5 text-[15px] font-medium text-ink-2">{pctS(s.roi_ci95[0])} to {pctS(s.roi_ci95[1])}</dd>
        </div>
      </dl>

      <EquityChart s={s} />

      <dl className="mt-6 grid grid-cols-3 gap-x-4 gap-y-5 border-t border-line pt-5">
        <Stat label="Bets" value={String(s.n_bets)} />
        <Stat label="Staked" value={money(s, s.staked)} />
        <Stat label="Hit rate" value={pctS(s.hit_rate, false)} />
        <Stat label="Max drawdown" value={money(s, s.max_drawdown)} />
        <Stat label="Closing line value" value={s.clv == null ? "n/a" : pctS(s.clv)} />
        <Stat label="Brier score" value={s.brier_model.toFixed(3)} sub={`Market ${s.brier_market.toFixed(3)}${brierBetter ? ", ours lower" : ""}`} />
      </dl>
      <p className="mt-6 text-pretty text-[13.5px] leading-[1.6] text-ink-3"><Emph text={s.description} /></p>
    </article>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex min-w-0 flex-col-reverse justify-end gap-1">
      <dt className="text-[12.5px] leading-[1.35] text-ink-3">{label}{sub && <span className="tabular mt-0.5 block text-ink-4">{sub}</span>}</dt>
      <dd className="tabular text-[16px] font-medium text-ink">{value}</dd>
    </div>
  );
}

/** Bankroll over the evaluation period as a line that draws on, with a crosshair tooltip. */
function EquityChart({ s }: { s: BacktestStrategy }) {
  const [ref, { width }] = useSize<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const [last, setLast] = useState<number | null>(null);
  const reduce = useReducedMotion();
  const H = 190, P = { l: 56, r: 12, t: 18, b: 26 };
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
  // keep the last point while the tooltip fades out, so it doesn't empty mid-exit
  if (hover != null && hover !== last) setLast(hover);
  const shownIdx = hover ?? last;
  const shown = shownIdx != null ? pts[shownIdx] : null;

  const linePath = geo ? line<(typeof pts)[number]>().x((_, i) => geo.x(i)).y((p) => geo.y(p.bankroll))(pts) ?? "" : "";
  const fillPath = geo ? area<(typeof pts)[number]>().x((_, i) => geo.x(i)).y0(geo.y(geo.ref)).y1((p) => geo.y(p.bankroll))(pts) ?? "" : "";
  const end = pts[pts.length - 1];

  return (
    <div className="mt-8">
      <p className="mb-2 flex items-baseline justify-between gap-3 text-[12.5px] text-ink-3">
        <span>Bankroll after each {isPoly(s) ? "trading day" : "matchweek"}</span>
        <span className="tabular">{pts.length - 1} steps</span>
      </p>
      <div ref={ref} className="relative" style={{ height: H }}>
        {geo && (
          <svg width={width} height={H} className="block overflow-visible" role="img"
            aria-label={`Bankroll from ${axisMoney(s, geo.ref)} at the start to ${axisMoney(s, end.bankroll)} after ${pointLabel(end.label)}`}>
            {geo.y.ticks(4).map((t) => (
              <g key={t}>
                <line x1={P.l} x2={width - P.r} y1={geo.y(t)} y2={geo.y(t)} stroke="var(--grid)" />
                <text x={P.l - 10} y={geo.y(t) + 4} fontSize={11} fill="var(--ink-3)" textAnchor="end" className="tabular">{axisMoney(s, t)}</text>
              </g>
            ))}
            <line x1={P.l} x2={width - P.r} y1={geo.y(geo.ref)} y2={geo.y(geo.ref)} stroke="var(--ink-4)" strokeDasharray="3 3" />
            <text x={width - P.r} y={geo.y(geo.ref) - 6} fontSize={11} fill="var(--ink-3)" textAnchor="end">Starting bankroll</text>
            <motion.path d={fillPath} fill="var(--ink)" initial={reduce ? false : { opacity: 0 }} whileInView={{ opacity: 0.06 }}
              viewport={{ once: true }} transition={{ duration: 0.6, delay: 0.5 }} style={reduce ? { opacity: 0.06 } : undefined} />
            <motion.path d={linePath} fill="none" stroke="var(--ink)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round"
              initial={reduce ? false : { pathLength: 0 }} whileInView={{ pathLength: 1 }} viewport={{ once: true, amount: 0.5 }} transition={{ duration: 1.1, ease: EASE }} />
            <circle cx={geo.x(pts.length - 1)} cy={geo.y(end.bankroll)} r={4} fill="var(--ink)" stroke="var(--surface-1)" strokeWidth={2} />
            <text x={P.l} y={H - 6} fontSize={11} fill="var(--ink-3)">{pointLabel(pts[0].label)}</text>
            <text x={width - P.r} y={H - 6} fontSize={11} fill="var(--ink-3)" textAnchor="end">{pointLabel(end.label)}</text>
            {shownIdx != null && (
              <g pointerEvents="none" opacity={hover != null ? 1 : 0} style={{ transition: `opacity ${hover != null ? "var(--tt-in-dur)" : "var(--tt-out-dur)"} ease-out` }}>
                <line x1={geo.x(shownIdx)} x2={geo.x(shownIdx)} y1={P.t} y2={H - P.b} stroke="var(--ink-2)" strokeWidth={1} />
                <circle cx={geo.x(shownIdx)} cy={geo.y(pts[shownIdx].bankroll)} r={4.5} fill="var(--ink)" stroke="var(--surface-1)" strokeWidth={2} />
              </g>
            )}
            <rect x={P.l} y={0} width={Math.max(0, width - P.l - P.r)} height={H} fill="transparent"
              onPointerMove={(e) => {
                const px = e.clientX - e.currentTarget.getBoundingClientRect().left + P.l;
                setHover(Math.max(0, Math.min(pts.length - 1, Math.round(geo.x.invert(px)))));
              }}
              onPointerLeave={() => setHover(null)} />
          </svg>
        )}
        {geo && shown && (
          <div data-open={hover != null} style={{ left: Math.min(Math.max(geo.x(shownIdx!), 90), width - 90) }}
            className="t-tt absolute -top-9 z-10 whitespace-nowrap rounded-lg bg-surface-3 px-2.5 py-1.5 text-[12px] text-ink shadow-[0_8px_24px_-8px_rgba(0,0,0,0.6)] ring-1 ring-line-strong">
            <span className="mr-2 text-ink-2">{pointLabel(shown.label)}</span>
            <span className="tabular">{money(s, shown.bankroll - geo.ref, true)}</span>
            <span className="text-ink-2"> since start</span>
          </div>
        )}
      </div>
    </div>
  );
}

// wide tables scroll sideways on phones; the fade at the edge says there is more
const TABLE_WRAP = "scroll-thin relative overflow-x-auto rounded-[20px] bg-surface-1 ring-1 ring-line [mask-image:linear-gradient(to_right,black_calc(100%-36px),transparent)] lg:[mask-image:none]";
const TH = "px-4 py-3 text-left text-[12.5px] font-medium text-ink-3 first:pl-5 last:pr-5 md:first:pl-6 md:last:pr-6";
const TD = "px-4 py-2.5 first:pl-5 last:pr-5 md:first:pl-6 md:last:pr-6";

function Sensitivity({ bt }: { bt: Backtest }) {
  const head = new Set(headline(bt).map((s) => s.id));
  const rest = bt.strategies.filter((s) => !head.has(s.id));
  if (!rest.length) return null;
  return (
    <Section id="sensitivity" title="Sensitivity checks"
      intro="The same models with other staking rules, opening prices and more slippage. Opening-price rows test payouts only and are not evidence of tradable profit.">
      <div className={TABLE_WRAP}>
        <table className="w-full min-w-[760px] border-collapse text-[13.5px]">
          <thead className="border-b border-line">
            <tr>
              <th scope="col" className={TH}>Strategy</th>
              <th scope="col" className={`${TH} text-right`}>Bets</th>
              <th scope="col" className={`${TH} text-right`}>Staked</th>
              <th scope="col" className={`${TH} text-right`}>Profit or loss</th>
              <th scope="col" className={`${TH} text-right`}>Return</th>
              <th scope="col" className={`${TH} text-right`}>95% interval</th>
            </tr>
          </thead>
          <tbody>
            {rest.map((s) => (
              <tr key={s.id} className="border-t border-line first:border-t-0">
                <th scope="row" className={`${TD} text-left font-medium text-ink`}>{s.name}</th>
                <td className={`${TD} tabular text-right text-ink-3`}>{s.n_bets}</td>
                <td className={`${TD} tabular text-right text-ink-3`}>{money(s, s.staked)}</td>
                <td className={`${TD} tabular text-right font-medium ${pnlTone(s.pnl)}`}>{money(s, s.pnl, true)}</td>
                <td className={`${TD} tabular text-right text-ink-2`}>{pctS(s.roi)}</td>
                <td className={`${TD} tabular whitespace-nowrap text-right text-ink-3`}>{pctS(s.roi_ci95[0])} to {pctS(s.roi_ci95[1])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

/** Before/after adding squad data (starting-XI market value, age, missing regulars) to the models. */
function PlayerDataComparison({ bt }: { bt: Backtest }) {
  if (!bt.comparison?.length) return null;
  const byId = new Map(bt.strategies.map((s) => [s.id, s]));
  const pm = bt.comparison.find((c) => c.strategy_id.startsWith("pinnacle"));
  return (
    <Section id="player-data" title="Did player data help?"
      intro={<>
        We added squad information from Transfermarkt (CC0): each starting XI's market value at kick-off, age, caps, and which regular starters were missing.
        {pm && <> It made the pre-match model more accurate (Brier score from {pm.before.brier_model.toFixed(3)} to <span className="tabular font-medium text-ink">{pm.after.brier_model.toFixed(3)}</span>, lower is better), but not more profitable. The in-play version got worse, so we kept the original.</>}
      </>}>
      <div className={TABLE_WRAP}>
        <table className="w-full min-w-[760px] border-collapse text-[13.5px]">
          <thead className="border-b border-line">
            <tr>
              <th scope="col" className={TH}>Strategy</th>
              <th scope="col" className={`${TH} text-right`}>Brier before</th>
              <th scope="col" className={`${TH} text-right`}>Brier after</th>
              <th scope="col" className={`${TH} text-right`}>Return before</th>
              <th scope="col" className={`${TH} text-right`}>Return after</th>
              <th scope="col" className={`${TH} text-right`}>95% interval after</th>
            </tr>
          </thead>
          <tbody>
            {bt.comparison.map((c) => {
              const s = byId.get(c.strategy_id);
              const better = c.after.brier_model < c.before.brier_model - 1e-6;
              return (
                <tr key={c.strategy_id} className="border-t border-line first:border-t-0">
                  <th scope="row" className={`${TD} text-left font-medium text-ink`}>{s?.name ?? c.strategy_id}</th>
                  <td className={`${TD} tabular text-right text-ink-3`}>{c.before.brier_model.toFixed(3)}</td>
                  <td className={`${TD} tabular text-right ${better ? "font-medium text-ink" : "text-ink-3"}`}>{c.after.brier_model.toFixed(3)}{better && <span className="sr-only"> (improved)</span>}</td>
                  <td className={`${TD} tabular text-right text-ink-3`}>{pctS(c.before.roi)}</td>
                  <td className={`${TD} tabular text-right font-medium text-ink`}>{pctS(c.after.roi)}</td>
                  <td className={`${TD} tabular whitespace-nowrap text-right text-ink-3`}>{pctS(c.after.roi_ci95[0])} to {pctS(c.after.roi_ci95[1])}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {bt.model_versions && <p className="mt-3 text-[12.5px] text-ink-3">Models compared: <span className="font-mono text-[12px]">{bt.model_versions.before}</span> before, <span className="font-mono text-[12px]">{bt.model_versions.after}</span> after.</p>}
    </Section>
  );
}

const edge = (d: number) => {
  const n = Math.round(d * 100);
  return `+${n} ${n === 1 ? "pt" : "pts"}`;
};
const OUTCOME: Record<string, string> = { home: "Home win", draw: "Draw", away: "Away win" };
const betLabel = (side: string, outcome: string) => {
  const o = OUTCOME[outcome] ?? outcome;
  return /^no$/i.test(side) ? `No on ${o.toLowerCase()}` : o;
};

function EveryBet({ head }: { head: BacktestStrategy[] }) {
  const [tab, setTab] = useState(0);
  const s = head[tab];
  if (!s) return null;
  return (
    <Section id="bets" title="Every bet" intro="Each bet the headline strategies placed, with our probability, the market's and the result."
      aside={
        <div role="group" aria-label="Strategy" className="-mx-5 overflow-x-auto px-5 md:mx-0 md:px-0">
          <div className="flex w-max gap-1 rounded-full bg-surface-1 p-1 ring-1 ring-line">
            {head.map((h, i) => {
              const on = i === tab;
              return (
                <button key={h.id} type="button" aria-pressed={on} onClick={() => setTab(i)}
                  className={`relative shrink-0 whitespace-nowrap rounded-full px-4 py-1.5 text-[13.5px] font-medium transition-[color,transform] duration-[250ms] active:scale-[0.97] ${on ? "text-bg" : "text-ink-3 hover:text-ink"}`}>
                  {on && <motion.span layoutId="bets-pill" className="absolute inset-0 rounded-full bg-ink" transition={{ duration: 0.25, ease: EASE }} />}
                  <span className="relative">{h.name}</span>
                </button>
              );
            })}
          </div>
        </div>
      }>
      <BetsTable s={s} />
    </Section>
  );
}

function BetsTable({ s }: { s: BacktestStrategy }) {
  return (
    <div className="overflow-hidden rounded-[20px] bg-surface-1 ring-1 ring-line">
      <div className="scroll-thin relative max-h-[520px] overflow-auto [mask-image:linear-gradient(to_right,black_calc(100%-36px),transparent)] lg:[mask-image:none]" tabIndex={0} aria-label={`Bets placed by ${s.name}`}>
        <table className="w-full min-w-[820px] border-collapse text-[13.5px]">
          <thead className="sticky top-0 z-[1] bg-surface-1 shadow-[inset_0_-1px_0_var(--border)]">
            <tr>
              <th scope="col" className={TH}>Match</th>
              <th scope="col" className={TH}>Bet</th>
              <th scope="col" className={TH}>Minute</th>
              <th scope="col" className={`${TH} text-right`}>Our model</th>
              <th scope="col" className={`${TH} text-right`}>Market</th>
              <th scope="col" className={`${TH} text-right`}>Edge</th>
              <th scope="col" className={`${TH} text-right`}>{isPoly(s) ? "Price" : "Odds"}</th>
              <th scope="col" className={`${TH} text-right`}>Profit or loss</th>
            </tr>
          </thead>
          <tbody>
            {s.bets.map((b, i) => (
              <tr key={i} className="border-t border-line transition-colors duration-150 first:border-t-0 hover:bg-surface-2">
                <th scope="row" className={`${TD} max-w-[280px] text-left font-medium`}>
                  <Link to={`/match/${encodeURIComponent(b.match_id)}`} className="block truncate text-ink underline-offset-4 hover:underline">{plain(b.label)}</Link>
                </th>
                <td className={`${TD} whitespace-nowrap text-ink-2`}>{betLabel(b.side, b.outcome)}</td>
                <td className={`${TD} tabular whitespace-nowrap text-ink-3`}>{b.minute != null ? `${b.minute}'` : "Pre-match"}</td>
                <td className={`${TD} tabular text-right text-ink`}>{(b.model_prob * 100).toFixed(0)}%</td>
                <td className={`${TD} tabular text-right text-ink-2`}>{(b.market_prob * 100).toFixed(0)}%</td>
                <td className={`${TD} tabular whitespace-nowrap text-right text-ink-2`}>{edge(b.model_prob - b.market_prob)}</td>
                <td className={`${TD} tabular text-right text-ink-2`}>{isPoly(s) ? `${Math.round(b.price_or_odds * 100)}¢` : b.price_or_odds.toFixed(2)}</td>
                <td className={`${TD} tabular text-right font-medium ${pnlTone(b.pnl)}`}>{money(s, b.pnl, true)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Sources({ bt }: { bt: Backtest }) {
  const stamp = new Date(bt.generated_at);
  return (
    <Section id="method" title="Sources and caveats" intro="Where the prices came from, and what these numbers can and cannot tell you.">
      <div className="grid grid-cols-1 items-start gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)]">
        <InView className="rounded-[20px] bg-surface-1 p-6 ring-1 ring-line md:p-8">
          <h3 className="text-[17px] font-semibold tracking-[-0.015em] text-ink">Data sources</h3>
          <ul className="mt-5 space-y-6">
            {bt.sources.map((src) => (
              <li key={src.name}>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-[15px] font-medium text-ink">{src.name}</span>
                  <span className={`tabular shrink-0 text-[13px] ${src.matches ? "text-ink-2" : "text-ink-4"}`}>{src.matches ? `${src.matches} matches` : "No matches used"}</span>
                </div>
                <p className="mt-1.5 text-pretty text-[13.5px] leading-[1.6] text-ink-3">{plain(src.notes)}</p>
              </li>
            ))}
          </ul>
        </InView>
        <InView i={1} className="rounded-[20px] bg-surface-1 p-6 ring-1 ring-line md:p-8">
          <h3 className="text-[17px] font-semibold tracking-[-0.015em] text-ink">How to read this</h3>
          <ul className="mt-5 list-disc space-y-3 pl-5 text-pretty text-[14px] leading-[1.6] text-ink-2 marker:text-ink-4">
            {bt.caveats.map((c) => <li key={c}><Emph text={c} /></li>)}
          </ul>
          <p className="mt-6 text-[12.5px] text-ink-3">Generated {Number.isNaN(stamp.getTime()) ? bt.generated_at : `${stampFmt.format(stamp)} UTC`}</p>
        </InView>
      </div>
    </Section>
  );
}
