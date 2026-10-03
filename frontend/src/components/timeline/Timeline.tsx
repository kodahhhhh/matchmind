import { useMemo, useRef, useState } from "react";
import { scaleLinear } from "d3-scale";
import { line, curveStepAfter } from "d3-shape";
import type { Side, TimelineMinute } from "../../api/types";
import { bucketKey, useMatch } from "../../store/match";
import { pct, xg } from "../../lib/format";
import { useSize } from "../ui/useSize";

const M = { l: 44, r: 64 };
const GAP = 8; // px between periods
const H_MARK = 20;
const H_MOM = 72;
const H_XG = 44;
const H_AXIS = 18;
const PAD = 8;
const PERIOD_NAME: Record<number, string> = { 1: "1st half", 2: "2nd half", 3: "ET 1", 4: "ET 2" };

export function Timeline() {
  const data = useMatch((s) => s.data);
  const win = useMatch((s) => s.window);
  const focus = useMatch((s) => s.focus);
  const setWindow = useMatch((s) => s.setWindow);
  const focusEvent = useMatch((s) => s.focusEvent);
  const hoverIndex = useMatch((s) => s.hoverIndex);
  const setHoverIndex = useMatch((s) => s.setHoverIndex);
  const [ref, { width }] = useSize<HTMLDivElement>();
  const drag = useRef<{ anchor: number; moved: boolean } | null>(null);
  const [dragWin, setDragWin] = useState<{ from: number; to: number } | null>(null);

  const geo = useMemo(() => {
    if (!data || !width) return null;
    const tl = data.timeline;
    const nPeriods = data.match.periods.length;
    const inner = width - M.l - M.r - GAP * (nPeriods - 1);
    const step = inner / tl.length;
    const pIdx = new Map(data.match.periods.map((p, i) => [p.period, i]));
    const x = (i: number) => M.l + i * step + (pIdx.get(tl[Math.min(i, tl.length - 1)].period) ?? 0) * GAP;
    const maxMom = Math.max(0.02, ...tl.map((m) => Math.abs(m.momentum)));
    const yMom = scaleLinear().domain([-maxMom, maxMom]).range([H_MARK + PAD + H_MOM, H_MARK + PAD]);
    const maxXg = Math.max(0.5, ...tl.map((m) => Math.max(m.home.xg_cum, m.away.xg_cum)));
    const xgTop = H_MARK + PAD + H_MOM + PAD;
    const yXg = scaleLinear().domain([0, maxXg]).nice().range([xgTop + H_XG, xgTop]);
    const height = xgTop + H_XG + H_AXIS;
    const indexAt = (px: number) => {
      let best = 0;
      for (let i = 0; i < tl.length; i++) if (Math.abs(x(i) + step / 2 - px) < Math.abs(x(best) + step / 2 - px)) best = i;
      return best;
    };
    return { tl, step, x, yMom, yXg, height, indexAt, xgTop };
  }, [data, width]);

  if (!data) return <div ref={ref} className="h-[170px]" />;
  const { teams, markers, periods } = data.match;

  const onDown = (ev: React.PointerEvent<SVGSVGElement>) => {
    if (!geo) return;
    const i = geo.indexAt(ev.nativeEvent.offsetX);
    drag.current = { anchor: i, moved: false };
    (ev.target as Element).setPointerCapture?.(ev.pointerId);
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

  return (
    <div ref={ref} className="relative w-full">
      {geo && (
        <svg width={width} height={geo.height} className="block touch-none" onPointerDown={onDown} onPointerMove={onMove}
          onPointerUp={onUp} onPointerLeave={() => setHoverIndex(null)} role="img" aria-label="Match timeline: momentum and cumulative xG by minute">
          {/* turning point band (AI-generated → AI accent) */}
          {tp && (
            <g>
              <rect x={geo.x(tp.start.index) - 2} y={2} width={geo.x(tp.end.index) - geo.x(tp.start.index) + geo.step + 4}
                height={geo.height - H_AXIS - 2} rx={6} fill="var(--ai-soft)" stroke="var(--ai-line)" strokeWidth={1} />
            </g>
          )}

          {/* track labels */}
          <g fontSize={10} fill="var(--ink-3)">
            <text x={M.l - 10} y={geo.yMom(0) + 3} textAnchor="end">0</text>
            <text x={M.l - 10} y={H_MARK + PAD + 8} textAnchor="end">{teams.home.short}</text>
            <text x={M.l - 10} y={H_MARK + PAD + H_MOM - 2} textAnchor="end">{teams.away.short}</text>
            <text x={M.l - 10} y={geo.xgTop + 8} textAnchor="end">xG</text>
          </g>

          {/* per-period chrome */}
          {periods.map((p) => {
            const x0 = geo.x(p.start_index);
            const x1 = geo.x(p.end_index) + geo.step;
            return (
              <g key={p.period}>
                <line x1={x0} x2={x1} y1={geo.yMom(0)} y2={geo.yMom(0)} stroke="var(--axis)" />
                <line x1={x0} x2={x1} y1={geo.yXg(0)} y2={geo.yXg(0)} stroke="var(--axis)" />
                <text x={x0} y={geo.height - 5} fontSize={10} fill="var(--ink-3)">{PERIOD_NAME[p.period] ?? `P${p.period}`}</text>
              </g>
            );
          })}
          {/* minute ticks every 15' */}
          <g fontSize={10} fill="var(--ink-4)" className="tabular">
            {geo.tl.filter((m) => (m.minute + 1) % 15 === 0 && !m.label.includes("+")).map((m) => (
              <text key={m.index} x={geo.x(m.index) + geo.step / 2} y={geo.height - 5} textAnchor="middle">{m.minute + 1}'</text>
            ))}
          </g>

          {/* momentum bars */}
          <g>
            {geo.tl.map((m) => <MomentumBar key={m.index} m={m} x={geo.x(m.index)} step={geo.step} y={geo.yMom} />)}
          </g>

          {/* cumulative xG step lines */}
          <XgLines tl={geo.tl} x={geo.x} step={geo.step} y={geo.yXg} periods={periods} teams={teams} />

          {/* markers */}
          <g>
            {markers.map((mk) => {
              const i = data.bucketOf.get(bucketKey(mk.period, mk.minute));
              if (i == null) return null;
              const cx = geo.x(i) + geo.step / 2;
              const cy = H_MARK / 2 + 2;
              return (
                <g key={mk.event_id + mk.type} style={{ cursor: mk.type === "goal" ? "pointer" : "default" }}
                  onPointerDown={(e) => { e.stopPropagation(); if (mk.type === "goal") focusEvent(mk.event_id); }}>
                  <title>{`${mk.type} · ${geo.tl[i].label}`}</title>
                  {mk.type === "goal" && <><circle cx={cx} cy={cy} r={6} fill={`var(--${mk.team})`} /><circle cx={cx} cy={cy} r={2.2} fill="var(--bg)" /></>}
                  {mk.type === "card" && <rect x={cx - 3} y={cy - 5} width={6} height={9} rx={1.2} fill={mk.detail === "yellow" ? "#f2c94c" : "#e5484d"} />}
                  {mk.type === "sub" && <path d={`M ${cx - 3} ${cy + 1} l 3 -4 l 3 4 M ${cx} ${cy - 3} v 8`} stroke="var(--ink-3)" strokeWidth={1.4} fill="none" strokeLinecap="round" />}
                </g>
              );
            })}
          </g>

          {/* selection: dim outside */}
          {shown && (
            <g pointerEvents="none">
              <rect x={M.l - 4} y={0} width={Math.max(0, geo.x(shown.from) - M.l + 4)} height={geo.height - H_AXIS} fill="var(--bg)" opacity={0.62} />
              <rect x={geo.x(shown.to) + geo.step} y={0} width={Math.max(0, width - M.r + 4 - geo.x(shown.to) - geo.step)} height={geo.height - H_AXIS} fill="var(--bg)" opacity={0.62} />
              <rect x={geo.x(shown.from)} y={1} width={geo.x(shown.to) - geo.x(shown.from) + geo.step} height={geo.height - H_AXIS - 1} rx={4}
                fill="none" stroke="var(--ink-2)" strokeOpacity={0.5} />
            </g>
          )}

          {/* crosshair */}
          {hovered && (
            <line pointerEvents="none" x1={geo.x(hovered.index) + geo.step / 2} x2={geo.x(hovered.index) + geo.step / 2} y1={H_MARK} y2={geo.height - H_AXIS}
              stroke="var(--ink-2)" strokeOpacity={0.6} />
          )}
        </svg>
      )}
      {hovered && geo && <HoverCard m={hovered} left={geo.x(hovered.index) + geo.step / 2} width={width} />}
    </div>
  );
}

function MomentumBar({ m, x, step, y }: { m: TimelineMinute; x: number; step: number; y: (v: number) => number }) {
  const w = Math.min(Math.max(step - 2, 1), 24);
  const side: Side = m.momentum >= 0 ? "home" : "away";
  const y0 = y(0);
  const y1 = y(m.momentum);
  const h = Math.abs(y1 - y0);
  if (h < 0.5) return null;
  const r = Math.min(2, w / 2, h);
  const left = x + (step - w) / 2;
  // rounded at the data end, square at the baseline
  const d = side === "home"
    ? `M ${left} ${y0} V ${y1 + r} Q ${left} ${y1} ${left + r} ${y1} H ${left + w - r} Q ${left + w} ${y1} ${left + w} ${y1 + r} V ${y0} Z`
    : `M ${left} ${y0} V ${y1 - r} Q ${left} ${y1} ${left + r} ${y1} H ${left + w - r} Q ${left + w} ${y1} ${left + w} ${y1 - r} V ${y0} Z`;
  return <path d={d} fill={`var(--${side})`} opacity={0.9} />;
}

function XgLines({ tl, x, step, y, periods, teams }: {
  tl: TimelineMinute[]; x: (i: number) => number; step: number; y: (v: number) => number;
  periods: { start_index: number; end_index: number }[]; teams: Record<Side, { short: string }>;
}) {
  const last = tl[tl.length - 1];
  // end labels: keep at least 13px apart, with a leader line back to the dot when moved
  const dotY = { home: y(last.home.xg_cum), away: y(last.away.xg_cum) };
  const labelY = { ...dotY };
  const gap = 13 - Math.abs(dotY.home - dotY.away);
  if (gap > 0) {
    const upper: Side = dotY.home <= dotY.away ? "home" : "away";
    const lower: Side = upper === "home" ? "away" : "home";
    labelY[upper] -= gap / 2;
    labelY[lower] += gap / 2;
  }
  return (
    <g fill="none" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round">
      {(["home", "away"] as Side[]).map((s) => (
        <g key={s}>
          {periods.map((p) => {
            const pts = tl.slice(p.start_index, p.end_index + 1);
            const gen = line<TimelineMinute>().x((m) => x(m.index)).y((m) => y(m[s].xg_cum)).curve(curveStepAfter);
            const d = gen([...pts, { ...pts[pts.length - 1], index: pts[pts.length - 1].index + 1 } as TimelineMinute]);
            return <path key={p.start_index} d={d ?? ""} stroke={`var(--${s})`} transform={`translate(${0},0)`} />;
          })}
          <circle cx={x(last.index) + step} cy={dotY[s]} r={4} fill={`var(--${s})`} stroke="var(--bg)" strokeWidth={2} />
          {labelY[s] !== dotY[s] && <line x1={x(last.index) + step + 4} y1={dotY[s]} x2={x(last.index) + step + 10} y2={labelY[s]} stroke="var(--ink-4)" strokeWidth={1} />}
          <text x={x(last.index) + step + 12} y={labelY[s] + 4} fontSize={11} fill="var(--ink-2)" stroke="none" className="tabular">
            <tspan fontWeight={600} fill="var(--ink)">{xg(last[s].xg_cum)}</tspan> {teams[s].short}
          </text>
        </g>
      ))}
    </g>
  );
}

function HoverCard({ m, left, width }: { m: TimelineMinute; left: number; width: number }) {
  const flip = left > width - 220;
  return (
    <div className="pointer-events-none absolute top-0 z-20 w-[196px] rounded-lg border border-line-strong bg-surface-2/95 px-3 py-2 text-xs shadow-xl backdrop-blur"
      style={{ left: flip ? left - 208 : left + 12 }}>
      <div className="mb-1.5 font-display text-sm font-semibold tracking-wide text-ink">{m.label}</div>
      <table className="w-full tabular">
        <tbody>
          {(["home", "away"] as Side[]).map((s) => (
            <tr key={s} className="text-ink-2">
              <td className="py-0.5"><span className="mr-1.5 inline-block h-[2px] w-3 align-middle" style={{ background: `var(--${s})` }} /></td>
              <td className="text-right font-semibold text-ink">{xg(m[s].xg_cum)}</td><td className="pl-1">xG</td>
              <td className="text-right font-semibold text-ink">{pct(m[s].possession)}</td><td className="pl-1">poss.</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
