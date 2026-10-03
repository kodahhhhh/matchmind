import { useId, useMemo, useRef, useState } from "react";
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
const PERIOD_NAME: Record<number, string> = { 1: "First half", 2: "Second half", 3: "Extra time", 4: "ET 2" };

export function Timeline() {
  const uid = useId().replace(/:/g, "");
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
    const height = xgTop + H_XG + H_AXIS;
    const indexAt = (px: number) => {
      let best = 0;
      for (let i = 0; i < tl.length; i++) if (Math.abs(cx(i) - px) < Math.abs(cx(best) - px)) best = i;
      return best;
    };
    return { tl, step, x, cx, yMom, yXg, height, indexAt, waveTop, xgTop };
  }, [data, width]);

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

  const goals = markers.filter((m) => m.type === "goal");
  const laneEnds: number[][] = [[], []];
  const goalLabels = geo ? goals.map((g) => {
    const i = idxOf(g) ?? 0;
    const text = `${nameOf(g.player_id) || "Own goal"} ${clock(g.period, g.minute)}`;
    const w = text.length * 7.1 + 36;
    const x0 = Math.min(Math.max(geo.cx(i) - w / 2, 0), width - w);
    let lane = laneEnds.findIndex((l) => l.every((end) => x0 > end + 6));
    if (lane < 0) lane = 1;
    laneEnds[lane].push(x0 + w);
    return { g, i, text, x0, w, lane };
  }) : [];
  const selH = geo ? geo.height - geo.waveTop - H_AXIS + 6 : 0;

  return (
    <div ref={ref} className="relative w-full">
      {geo && (
        <>
          <svg width={width} height={geo.height} className="block touch-none" onPointerDown={onDown} onPointerMove={onMove}
            onPointerUp={onUp} onPointerLeave={() => setHoverIndex(null)} role="img" aria-label="Match timeline: momentum and cumulative xG by minute">
            <defs>
              {(["home", "away"] as Side[]).map((s) => (
                <linearGradient key={s} id={`wave-${s}-${uid}`} x1="0" y1={s === "home" ? "0" : "1"} x2="0" y2={s === "home" ? "1" : "0"}>
                  <stop offset="0%" stopColor={`var(--${s})`} stopOpacity={0.95} />
                  <stop offset="100%" stopColor={`var(--${s})`} stopOpacity={0.1} />
                </linearGradient>
              ))}
              <clipPath id={`above-${uid}`}><rect x={0} y={0} width={width} height={geo.yMom(0)} /></clipPath>
              <clipPath id={`below-${uid}`}><rect x={0} y={geo.yMom(0)} width={width} height={geo.height} /></clipPath>
            </defs>

            {periods.map((p) => {
              const pts = geo.tl.slice(p.start_index, p.end_index + 1);
              const wave = area<TimelineMinute>().x((m) => geo.cx(m.index)).y0(geo.yMom(0)).y1((m) => geo.yMom(m.momentum)).curve(curveMonotoneX);
              const x0 = geo.x(p.start_index);
              const x1 = geo.x(p.end_index) + geo.step;
              return (
                <g key={p.period}>
                  <rect x={x0} y={geo.waveTop} width={x1 - x0} height={H_WAVE} rx={8} fill="var(--surface-2)" />
                  <path d={wave(pts) ?? ""} fill={`url(#wave-home-${uid})`} clipPath={`url(#above-${uid})`} />
                  <path d={wave(pts) ?? ""} fill={`url(#wave-away-${uid})`} clipPath={`url(#below-${uid})`} />
                  <line x1={x0} x2={x1} y1={geo.yMom(0)} y2={geo.yMom(0)} stroke="var(--ink-4)" strokeOpacity={0.5} />
                  <line x1={x0} x2={x1} y1={geo.yXg(0)} y2={geo.yXg(0)} stroke="var(--axis)" />
                  <text x={x0 + 2} y={geo.height - 5} fontSize={10.5} fill="var(--ink-3)" fontWeight={500}>{PERIOD_NAME[p.period] ?? `Period ${p.period}`}</text>
                </g>
              );
            })}

            {tp && data.turningPoints.map((t) => (
              <rect key={t.id} x={geo.x(t.start.index) - 3} y={geo.waveTop - 6} width={geo.x(t.end.index) - geo.x(t.start.index) + geo.step + 6}
                height={selH} rx={8} fill="var(--ai-soft)" opacity={t.id === tp.id ? 1 : 0.55}
                stroke={t.id === tp.id ? "none" : "var(--ai-line)"} strokeDasharray="3 3" />
            ))}

            <g fontSize={10.5} fill="var(--ink-4)" className="tabular" textAnchor="middle">
              {geo.tl.filter((m) => [15, 30, 60, 75, 105].includes(m.minute + 1) && !m.label.includes("+")).map((m) => (
                <text key={m.index} x={geo.cx(m.index)} y={geo.height - 5}>{m.minute + 1}'</text>
              ))}
            </g>

            <XgLines tl={geo.tl} x={geo.x} step={geo.step} y={geo.yXg} periods={periods} />

            <g fontSize={10.5} fontWeight={700} letterSpacing={0.8}>
              <text x={width - M.r + 12} y={geo.waveTop + 14} fill="var(--ink)">{teams.home.short}</text>
              <rect x={width - M.r + 12} y={geo.waveTop + 18} width={14} height={2} rx={1} fill="var(--home)" />
              <text x={width - M.r + 12} y={geo.waveTop + H_WAVE - 12} fill="var(--ink)">{teams.away.short}</text>
              <rect x={width - M.r + 12} y={geo.waveTop + H_WAVE - 8} width={14} height={2} rx={1} fill="var(--away)" />
              <text x={width - M.r + 12} y={geo.yMom(0) + 3.5} fill="var(--ink-4)" fontWeight={500} letterSpacing={0}>momentum</text>
            </g>

            {goalLabels.map(({ g, i, lane }) => (
              <line key={`stem-${g.event_id}`} x1={geo.cx(i)} x2={geo.cx(i)} y1={lane ? 48 : 22} y2={geo.yMom(0)}
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
                  <title>{`${mk.type === "sub" ? "Substitution" : "Card"} · ${geo.tl[i].label}`}</title>
                  {mk.type === "card"
                    ? <rect x={x - 2.5} y={y - 4} width={5} height={7} rx={1} fill={mk.detail === "yellow" ? "#f2c94c" : "#e5484d"} />
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

          {goalLabels.map(({ g, text, x0, w, lane }) => (
            <button key={g.event_id} onClick={() => focusEvent(g.event_id)}
              className="absolute flex h-[22px] items-center gap-1.5 rounded-full bg-surface-3 pl-1.5 pr-2.5 text-[11.5px] font-semibold text-ink shadow-lg ring-1 ring-white/10 transition hover:bg-surface-4"
              style={{ left: x0, top: lane ? 26 : 0, width: w }}>
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: `var(--${g.team})` }} />
              <span className="truncate">{text}</span>
            </button>
          ))}
          {hovered && <HoverCard m={hovered} left={geo.cx(hovered.index)} width={width} top={geo.waveTop} />}
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
            <tspan fontWeight={700} fill="var(--ink)">{xg(last[s].xg_cum)}</tspan> xG
          </text>
        </g>
      ))}
    </g>
  );
}

function HoverCard({ m, left, width, top }: { m: TimelineMinute; left: number; width: number; top: number }) {
  const flip = left > width - 240;
  return (
    <div className="glass pointer-events-none absolute z-20 w-[208px] rounded-xl px-3.5 py-2.5 text-xs shadow-2xl"
      style={{ left: flip ? left - 220 : left + 12, top }}>
      <div className="display mb-1.5 text-base text-ink">{m.label}</div>
      {(["home", "away"] as Side[]).map((s) => (
        <div key={s} className="flex items-center gap-2 py-0.5 tabular text-ink-2">
          <span className="h-[2px] w-3 rounded" style={{ background: `var(--${s})` }} />
          <span className="font-semibold text-ink">{xg(m[s].xg_cum)}</span> xG
          <span className="ml-auto font-semibold text-ink">{pct(m[s].possession)}</span> poss.
        </div>
      ))}
    </div>
  );
}
