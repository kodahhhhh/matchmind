import { useId, useMemo, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { scaleLinear } from "d3-scale";
import { area, curveMonotoneX, curveStepAfter, line } from "d3-shape";
import type { Marker, Side, TimelineMinute } from "../../api/types";
import { bucketKey, useMatch } from "../../store/match";
import { clock, pct, xg } from "../../lib/format";
import { useSize } from "../ui/useSize";

const M = { l: 8, r: 84 };
const GAP = 10;
const H_GOALS = 56;
const H_WAVE = 84;
const H_XG = 34;
const H_AXIS = 20;
const H_MKT = 46;
// extra time's two short periods share one label, on the first
const PERIOD_NAME: Record<number, string> = { 1: "First half", 2: "Second half", 3: "Extra time", 4: "" };
// real-world card colours and bet outcomes; tokens when the theme defines them
const CARD = { yellow: "var(--card-yellow)", red: "var(--card-red)" };
const BET = { win: "var(--positive)", loss: "var(--negative)" };
const LEGEND_CHARS = 12;
const fit = (name: string, n = LEGEND_CHARS) => (name.length > n ? `${name.slice(0, n - 1).trimEnd()}…` : name);

export function Timeline() {
  const uid = useId().replace(/:/g, "");
  const data = useMatch((s) => s.data);
  const win = useMatch((s) => s.window);
  const focus = useMatch((s) => s.focus);
  const setWindow = useMatch((s) => s.setWindow);
  const showMoment = useMatch((s) => s.showMoment);
  const hoverIndex = useMatch((s) => s.hoverIndex);
  const market = useMatch((s) => s.market);
  const setHoverIndex = useMatch((s) => s.setHoverIndex);
  const [ref, { width }] = useSize<HTMLDivElement>();
  const drag = useRef<{ anchor: number; moved: boolean } | null>(null);
  const [dragWin, setDragWin] = useState<{ from: number; to: number } | null>(null);
  const reduce = useReducedMotion();
  // keep the last hovered minute while the hover card fades out
  const [lastHover, setLastHover] = useState<number | null>(null);
  if (hoverIndex != null && hoverIndex !== lastHover) setLastHover(hoverIndex);

  const geo = useMemo(() => {
    if (!data || !width) return null;
    const tl = data.timeline;
    const inner = width - M.l - M.r - GAP * (data.match.periods.length - 1);
    const step = inner / tl.length;
    const pIdx = new Map(data.match.periods.map((p, i) => [p.period, i]));
    const x = (i: number) => M.l + i * step + (pIdx.get(tl[Math.min(Math.max(i, 0), tl.length - 1)].period) ?? 0) * GAP;
    const cx = (i: number) => x(i) + step / 2;
    const maxMom = Math.max(0.02, ...tl.map((m) => Math.abs(m.momentum)));
    const waveTop = H_GOALS;
    const yMom = scaleLinear().domain([-maxMom, maxMom]).range([waveTop + H_WAVE, waveTop]);
    const xgTop = waveTop + H_WAVE + 8;
    const maxXg = Math.max(0.5, ...tl.map((m) => Math.max(m.home.xg_cum, m.away.xg_cum)));
    const yXg = scaleLinear().domain([0, maxXg]).range([xgTop + H_XG, xgTop + 4]);
    const mktTop = xgTop + H_XG + 10;
    const yMkt = scaleLinear().domain([0, 1]).range([mktTop + H_MKT, mktTop + 2]);
    const height = xgTop + H_XG + (market ? H_MKT + 10 : 0) + H_AXIS;
    const indexAt = (px: number) => {
      let best = 0;
      for (let i = 0; i < tl.length; i++) if (Math.abs(cx(i) - px) < Math.abs(cx(best) - px)) best = i;
      return best;
    };
    return { tl, step, x, cx, yMom, yXg, yMkt, mktTop, height, indexAt, waveTop, xgTop };
  }, [data, width, market]);

  if (!data) return <div ref={ref} className="h-[194px]" />;
  const { teams, markers, periods } = data.match;
  const idxOf = (m: Marker) => data.bucketOf.get(bucketKey(m.period, m.minute));
  const nameOf = (id: number | null | undefined) =>
    [...data.match.lineups.home, ...data.match.lineups.away].find((p) => p.player_id === id)?.short_name ?? "";

  const onDown = (ev: React.PointerEvent<SVGSVGElement>) => {
    if (!geo) return;
    drag.current = { anchor: geo.indexAt(ev.nativeEvent.offsetX), moved: false };
    ev.currentTarget.setPointerCapture(ev.pointerId);
  };
  const onMove = (ev: React.PointerEvent<SVGSVGElement>) => {
    if (!geo) return;
    const i = geo.indexAt(ev.nativeEvent.offsetX);
    setHoverIndex(i);
    if (drag.current && i !== drag.current.anchor) {
      drag.current.moved = true;
      setDragWin({ from: Math.min(i, drag.current.anchor), to: Math.max(i, drag.current.anchor) });
    }
  };
  const onUp = (ev: React.PointerEvent<SVGSVGElement>) => {
    if (!geo || !drag.current) return;
    const i = geo.indexAt(ev.nativeEvent.offsetX);
    if (drag.current.moved && dragWin) setWindow(dragWin);
    else setWindow({ from: Math.max(0, i - 2), to: Math.min(geo.tl.length - 1, i + 2) });
    drag.current = null;
    setDragWin(null);
  };

  const shown = dragWin ?? win;
  const tp = focus?.kind === "turning" ? data.turningPoints.find((t) => t.id === focus.id) : undefined;
  const hovered = hoverIndex != null ? geo?.tl[hoverIndex] : undefined;
  const cardMinute = lastHover != null ? geo?.tl[lastHover] : undefined;
  const narrow = width < 640;
  // where each period name ends, so minute ticks never collide with it
  const nameEnds = geo ? periods.map((p) => ({ from: geo.x(p.start_index), to: geo.x(p.start_index) + 2 + (PERIOD_NAME[p.period] ?? `Period ${p.period}`).length * 6 + 14 })) : [];

  const goals = markers.filter((m) => m.type === "goal");
  const laneEnds: number[][] = [[], []];
  const goalLabels = geo ? goals.map((g) => {
    const i = idxOf(g) ?? 0;
    const full = `${nameOf(g.player_id) || "Own goal"} ${clock(g.period, g.minute)}`;
    // phones: minute only, so labels don't pile up in lanes over a narrow chart
    const text = narrow ? clock(g.period, g.minute) : full;
    const w = text.length * 7.1 + (narrow ? 38 : 36);
    const x0 = Math.min(Math.max(geo.cx(i) - w / 2, 0), width - w);
    let lane = laneEnds.findIndex((l) => l.every((end) => x0 > end + 6));
    if (lane < 0) lane = 1;
    laneEnds[lane].push(x0 + w);
    return { g, i, text, full, x0, w, lane };
  }) : [];
  const selH = geo ? geo.height - geo.waveTop - H_AXIS + 6 : 0;

  return (
    <div ref={ref} className="relative w-full">
      {geo && (
        <>
          <svg width={width} height={geo.height} className="block touch-none" onPointerDown={onDown} onPointerMove={onMove}
            onPointerUp={onUp} onPointerLeave={() => setHoverIndex(null)} role="img" aria-label="Match timeline: who was on top, and chance quality built up minute by minute">
            <defs>
              {(["home", "away"] as Side[]).map((s) => (
                <linearGradient key={s} id={`wave-${s}-${uid}`} x1="0" y1={s === "home" ? "0" : "1"} x2="0" y2={s === "home" ? "1" : "0"}>
                  <stop offset="0%" stopColor={`var(--${s})`} stopOpacity={0.95} />
                  <stop offset="100%" stopColor={`var(--${s})`} stopOpacity={0.1} />
                </linearGradient>
              ))}
              <clipPath id={`reveal-${uid}`}>
                <motion.rect key={data.match.match_id} x={0} y={0} height={geo.height} initial={reduce ? false : { width: 0 }} animate={{ width }} transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }} />
              </clipPath>
              <clipPath id={`above-${uid}`}><rect x={0} y={0} width={width} height={geo.yMom(0)} /></clipPath>
              <clipPath id={`below-${uid}`}><rect x={0} y={geo.yMom(0)} width={width} height={geo.height} /></clipPath>
            </defs>

            {periods.map((p) => {
              const pts = geo.tl.slice(p.start_index, p.end_index + 1);
              const wave = area<TimelineMinute>().x((m) => geo.cx(m.index)).y0(geo.yMom(0)).y1((m) => geo.yMom(m.momentum)).curve(curveMonotoneX);
              const x0 = geo.x(p.start_index);
              const x1 = geo.x(p.end_index) + geo.step;
              const name = PERIOD_NAME[p.period] ?? `Period ${p.period}`;
              // only label a period when the name fits its width (extra time is narrow on phones)
              const showName = name && (x1 - x0 + (p.period === 3 ? geo.step * 15 : 0)) >= name.length * 5.8 + 4;
              return (
                <g key={p.period}>
                  <rect x={x0} y={geo.waveTop} width={x1 - x0} height={H_WAVE} rx={8} fill="var(--surface-2)" />
                  <g clipPath={`url(#reveal-${uid})`}>
                    <path d={wave(pts) ?? ""} fill={`url(#wave-home-${uid})`} clipPath={`url(#above-${uid})`} />
                    <path d={wave(pts) ?? ""} fill={`url(#wave-away-${uid})`} clipPath={`url(#below-${uid})`} />
                  </g>
                  <line x1={x0} x2={x1} y1={geo.yMom(0)} y2={geo.yMom(0)} stroke="var(--ink-4)" strokeOpacity={0.5} />
                  <line x1={x0} x2={x1} y1={geo.yXg(0)} y2={geo.yXg(0)} stroke="var(--axis)" />
                  {showName && <text x={x0 + 2} y={geo.height - 5} fontSize={11} fill="var(--ink-3)" fontWeight={500}>{name}</text>}
                </g>
              );
            })}

            {tp && data.turningPoints.map((t) => (
              <rect key={t.id} x={geo.x(t.start.index) - 3} y={geo.waveTop - 6} width={geo.x(t.end.index) - geo.x(t.start.index) + geo.step + 6}
                height={selH} rx={8} fill="var(--ai-soft)" opacity={t.id === tp.id ? 1 : 0.55}
                stroke={t.id === tp.id ? "none" : "var(--ai-line)"} strokeDasharray="3 3" />
            ))}

            <g fontSize={11} fill="var(--ink-4)" className="tabular" textAnchor="middle">
              {!narrow && geo.tl.filter((m) => [15, 30, 60, 75, 105].includes(m.minute + 1) && !m.label.includes("+")
                && !nameEnds.some((n) => geo.cx(m.index) > n.from && geo.cx(m.index) < n.to)).map((m) => (
                <text key={m.index} x={geo.cx(m.index)} y={geo.height - 5}>{m.minute + 1}'</text>
              ))}
            </g>

            <g clipPath={`url(#reveal-${uid})`}><XgLines tl={geo.tl} x={geo.x} step={geo.step} y={geo.yXg} periods={periods} /></g>

            {market && (
              <g>
                <rect x={M.l} y={geo.mktTop} width={width - M.l - M.r} height={H_MKT + 2} rx={6} fill="var(--surface-2)" opacity={0.6} />
                <line x1={M.l} x2={width - M.r} y1={geo.yMkt(0.5)} y2={geo.yMkt(0.5)} stroke="var(--grid)" />
                {(["market", "model"] as const).map((k) => {
                  const d = line<(typeof market.series)[number]>().x((p) => geo.cx(p.index)).y((p) => geo.yMkt(p[k].home))(market.series);
                  return <path key={k} d={d ?? ""} fill="none" stroke={k === "model" ? "var(--ai)" : "var(--ink-2)"} strokeWidth={k === "model" ? 2 : 1.5}
                    strokeDasharray={k === "market" ? "4 3" : undefined} strokeLinejoin="round" />;
                })}
                {market.bets.filter((b) => b.minute != null).map((b, k) => {
                  const pt = market.series.find((p) => p.minute >= b.minute!);
                  if (!pt) return null;
                  return <circle key={k} cx={geo.cx(pt.index)} cy={geo.yMkt(b.market_prob)} r={4} fill={b.pnl >= 0 ? BET.win : BET.loss} stroke="var(--surface-1)" strokeWidth={1.5}><title>{`Bet ${b.side} ${b.outcome} at ${Math.round(b.price_or_odds * 100)}¢ · ${b.pnl >= 0 ? "+" : ""}$${b.pnl}`}</title></circle>;
                })}
                <g fontSize={10.5} fill="var(--ink-3)">
                  <text x={width - M.r + 12} y={geo.mktTop + 12} fontWeight={600} fill="var(--ink)">{fit(teams.home.name, 9)} win<title>{`${teams.home.name} win probability`}</title></text>
                  <line x1={width - M.r + 12} x2={width - M.r + 26} y1={geo.mktTop + 24} y2={geo.mktTop + 24} stroke="var(--ai)" strokeWidth={2} />
                  <text x={width - M.r + 30} y={geo.mktTop + 27}>Model</text>
                  <line x1={width - M.r + 12} x2={width - M.r + 26} y1={geo.mktTop + 38} y2={geo.mktTop + 38} stroke="var(--ink-2)" strokeWidth={1.5} strokeDasharray="4 3" />
                  <text x={width - M.r + 30} y={geo.mktTop + 41}>Market</text>
                </g>
              </g>
            )}

            <g fontSize={11} fontWeight={600}>
              <rect x={width - M.r + 12} y={geo.waveTop + 6} width={8} height={8} rx={2} fill="var(--home)" />
              <text x={width - M.r + 24} y={geo.waveTop + 14} fill="var(--ink)">{fit(teams.home.name)}<title>{teams.home.name}</title></text>
              <rect x={width - M.r + 12} y={geo.waveTop + H_WAVE - 16} width={8} height={8} rx={2} fill="var(--away)" />
              <text x={width - M.r + 24} y={geo.waveTop + H_WAVE - 8} fill="var(--ink)">{fit(teams.away.name)}<title>{teams.away.name}</title></text>
              <text x={width - M.r + 12} y={geo.yMom(0) + 3.5} fill="var(--ink-4)" fontWeight={500}>Who's on top<title>Who is on top: which team's recent actions are making a goal more likely</title></text>
            </g>

            {goalLabels.map(({ g, i, lane }) => (
              <line key={`stem-${g.event_id}`} x1={geo.cx(i)} x2={geo.cx(i)} y1={lane ? 52 : 24} y2={geo.yMom(0)}
                stroke={`var(--${g.team})`} strokeOpacity={0.6} strokeWidth={1.2} />
            ))}
            {goalLabels.map(({ g, i }) => (
              <circle key={`dot-${g.event_id}`} cx={geo.cx(i)} cy={geo.yMom(0)} r={4.5} fill={`var(--${g.team})`} stroke="var(--surface-1)" strokeWidth={2} />
            ))}

            {markers.filter((m) => m.type !== "goal").map((mk) => {
              const i = idxOf(mk);
              if (i == null) return null;
              const x = geo.cx(i);
              const y = geo.waveTop + H_WAVE - 8;
              return (
                <g key={mk.event_id + mk.type}>
                  <title>{`${mk.type === "sub" ? "Substitution" : mk.detail === "yellow" ? "Yellow card" : "Red card"}, ${geo.tl[i].label}`}</title>
                  {mk.type === "card"
                    ? <rect x={x - 2.5} y={y - 4} width={5} height={7} rx={1} fill={mk.detail === "yellow" ? CARD.yellow : CARD.red} />
                    : <path d={`M ${x - 2.6} ${y + 1.5} l 2.6 -3.4 l 2.6 3.4`} stroke="var(--ink-3)" strokeWidth={1.3} fill="none" strokeLinecap="round" strokeLinejoin="round" />}
                </g>
              );
            })}

            {shown && (
              <g pointerEvents="none">
                <rect x={0} y={geo.waveTop - 6} width={Math.max(0, geo.x(shown.from) - 3)} height={selH} fill="var(--surface-1)" opacity={0.72} />
                <rect x={geo.x(shown.to) + geo.step + 3} y={geo.waveTop - 6} width={Math.max(0, width - geo.x(shown.to) - geo.step - 3)}
                  height={selH} fill="var(--surface-1)" opacity={0.72} />
                <rect x={geo.x(shown.from) - 3} y={geo.waveTop - 6} width={geo.x(shown.to) - geo.x(shown.from) + geo.step + 6}
                  height={selH} rx={8} fill="none" stroke={tp ? "var(--ai)" : "var(--ink)"} strokeOpacity={0.75} strokeWidth={1.5} />
                {[geo.x(shown.from) - 3, geo.x(shown.to) + geo.step + 3].map((hx, k) => (
                  <rect key={k} x={hx - 2} y={geo.waveTop + H_WAVE / 2 - 10} width={4} height={20} rx={2} fill={tp ? "var(--ai)" : "var(--ink)"} />
                ))}
              </g>
            )}

            {hovered && (
              <line pointerEvents="none" x1={geo.cx(hovered.index)} x2={geo.cx(hovered.index)} y1={geo.waveTop} y2={geo.height - H_AXIS}
                stroke="var(--ink)" strokeOpacity={0.4} />
            )}
          </svg>

          {goalLabels.map(({ g, text, full, x0, w, lane }) => (
            <button key={g.event_id} onClick={() => showMoment({ ev: g.event_id })} aria-label={`Show goal: ${full}`}
              className="absolute flex h-6 items-center gap-1.5 rounded-full bg-surface-3 pl-2 pr-2.5 text-[11.5px] font-semibold text-ink shadow-lg ring-1 ring-line-strong transition-[transform,background-color] duration-150 ease-out hover:bg-surface-4 active:scale-[0.97]"
              style={{ left: x0, top: lane ? 28 : 0, width: w }}>
              <span className="size-2 shrink-0 rounded-full" style={{ background: `var(--${g.team})` }} aria-hidden />
              <span className="truncate">{text}</span>
            </button>
          ))}
          {cardMinute && <HoverCard m={cardMinute} open={hovered != null} left={geo.cx(cardMinute.index)} width={width} top={geo.waveTop}
            teams={teams} mkt={market?.series.find((p) => p.index === cardMinute.index)} />}
        </>
      )}
    </div>
  );
}

function XgLines({ tl, x, step, y, periods }: {
  tl: TimelineMinute[]; x: (i: number) => number; step: number; y: (v: number) => number;
  periods: { start_index: number; end_index: number }[];
}) {
  const last = tl[tl.length - 1];
  const endX = x(last.index) + step;
  const dotY = { home: y(last.home.xg_cum), away: y(last.away.xg_cum) };
  const labelY = { ...dotY };
  const gap = 13 - Math.abs(dotY.home - dotY.away);
  if (gap > 0) {
    const upper: Side = dotY.home <= dotY.away ? "home" : "away";
    labelY[upper] -= gap / 2;
    labelY[upper === "home" ? "away" : "home"] += gap / 2;
  }
  return (
    <g fill="none" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round">
      {(["home", "away"] as Side[]).map((s) => (
        <g key={s}>
          {periods.map((p) => {
            const pts = tl.slice(p.start_index, p.end_index + 1);
            const gen = line<TimelineMinute>().x((m) => x(m.index)).y((m) => y(m[s].xg_cum)).curve(curveStepAfter);
            const ext = [...pts, { ...pts[pts.length - 1], index: pts[pts.length - 1].index + 1 } as TimelineMinute];
            return <path key={p.start_index} d={gen(ext) ?? ""} stroke={`var(--${s})`} />;
          })}
          <circle cx={endX} cy={dotY[s]} r={3.5} fill={`var(--${s})`} stroke="var(--surface-1)" strokeWidth={2} />
          <text x={endX + 10} y={labelY[s] + 4} fontSize={11} fill="var(--ink-3)" stroke="none" className="tabular">
            <tspan fontWeight={700} fill="var(--ink)">{xg(last[s].xg_cum)}</tspan> chances<title>Chance quality (xG): about one goal's worth per 1.0</title>
          </text>
        </g>
      ))}
    </g>
  );
}

const CARD_W = 236;

/** Minute card beside the crosshair (transitions.dev tooltip: 150ms in, 50ms out; position follows instantly). */
function HoverCard({ m, open, left, width, top, teams, mkt }: {
  m: TimelineMinute; open: boolean; left: number; width: number; top: number;
  teams: Record<Side, { name: string }>; mkt?: { market: { home: number }; model: { home: number } };
}) {
  const flip = left > width - CARD_W - 32;
  // .t-tt centres itself with translate(-50%), so anchor the wrapper at the card's centre
  const x = (flip ? left - CARD_W - 12 : left + 12) + CARD_W / 2;
  return (
    <div className="pointer-events-none absolute z-20" style={{ left: x, top }}>
      <div data-open={open} className="t-tt glass rounded-xl px-3.5 py-2.5 text-[12px] shadow-2xl" style={{ width: CARD_W }}>
        <div className="mb-1.5 flex items-baseline justify-between">
          <span className="numeral text-[17px] leading-none text-ink">{m.label}</span>
          <span className="flex gap-3 text-[11px] text-ink-3"><span className="w-9 text-right">Chances</span><span className="w-[62px] text-right">Possession</span></span>
        </div>
        {(["home", "away"] as Side[]).map((s) => (
          <div key={s} className="flex items-center gap-2 py-0.5 tabular text-ink-2">
            <span className="size-2 shrink-0 rounded-[2px]" style={{ background: `var(--${s})` }} aria-hidden />
            <span className="min-w-0 flex-1 truncate">{teams[s].name}</span>
            <span className="flex gap-3 font-semibold text-ink">
              <span className="w-9 text-right">{xg(m[s].xg_cum)}</span>
              <span className="w-[62px] text-right">{pct(m[s].possession)}</span>
            </span>
          </div>
        ))}
        {mkt && (
          <div className="mt-1.5 border-t border-line-strong pt-1.5 tabular text-ink-2">
            <div className="truncate text-ink-3">{teams.home.name} win chance</div>
            <div className="mt-0.5 flex items-center gap-3">
              <span>Model <span className="font-semibold text-ai">{pct(mkt.model.home)}</span></span>
              <span>Market <span className="font-semibold text-ink">{pct(mkt.market.home)}</span></span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
