import { useMemo, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { area, curveMonotoneX } from "d3-shape";
import { scaleLinear } from "d3-scale";
import type { MatchCard, Side, TimelineMinute, TurningPoint } from "../../api/types";

type Goal = { id: string; period: number; minute: number; team: Side };
import { useSize } from "../ui/useSize";

const H = 168;
const PAD_T = 26; // room for the turning-point label
const PAD_B = 22; // room for period labels
const PERIOD_GAP = 6;
const PERIOD_NAME: Record<number, string> = { 1: "1st half", 2: "2nd half", 3: "Extra time" };

/** Compact momentum chart for the landing page: one diverging area around zero, the top-ranked turning point shaded. */
export function MomentumPreview({ m, minutes, turning, goals }: {
  m: MatchCard; minutes: TimelineMinute[]; turning: TurningPoint | null; goals: Goal[];
}) {
  const [ref, { width }] = useSize<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const reduce = useReducedMotion();

  const geo = useMemo(() => {
    if (!width || !minutes.length) return null;
    const periods = [...new Set(minutes.map((d) => d.period))];
    const step = (width - PERIOD_GAP * (periods.length - 1)) / minutes.length;
    const x = (i: number) => i * step + periods.indexOf(minutes[i].period) * PERIOD_GAP;
    const cx = (i: number) => x(i) + step / 2;
    const max = Math.max(0.05, ...minutes.map((d) => Math.abs(d.momentum)));
    const y = scaleLinear().domain([-max, max]).range([H - PAD_B, PAD_T]);
    const spans = periods.map((p) => {
      const idx = minutes.filter((d) => d.period === p).map((d) => d.index);
      return { p, a: Math.min(...idx), b: Math.max(...idx) };
    });
    return { step, x, cx, y, spans };
  }, [width, minutes]);

  const goalAt = useMemo(() => {
    const map = new Map<number, Goal>();
    for (const g of goals) {
      const d = minutes.find((t) => t.period === g.period && t.minute === g.minute);
      if (d) map.set(d.index, g);
    }
    return map;
  }, [goals, minutes]);

  const name = { home: m.home.name, away: m.away.name };
  // keep the last minute while the tooltip fades out, so it doesn't empty mid-exit
  const [lastHover, setLastHover] = useState<number | null>(null);
  if (hover != null && hover !== lastHover) setLastHover(hover);
  const shownIdx = hover ?? lastHover;
  const shown = shownIdx != null ? minutes[shownIdx] : null;
  // near zero neither side is on top; say so instead of naming a leader
  const shownLeader = shown ? (Math.abs(shown.momentum) < 0.03 ? "even" : shown.momentum > 0 ? "home" : "away") : null;

  return (
    <div style={{ ["--home" as string]: m.home.color, ["--away" as string]: m.away.color }}>
      <div ref={ref} className="relative" style={{ height: H }}>
        {geo && (
          <svg width={width} height={H} className="block overflow-visible" role="img"
            aria-label={`Momentum by minute, ${m.home.name} against ${m.away.name}. ${turning ? `Biggest swing from ${turning.start.label} to ${turning.end.label}, toward ${name[turning.team_gaining]}.` : ""}`}>
            <defs>
              <clipPath id="mp-above"><rect x={0} y={0} width={width} height={geo.y(0)} /></clipPath>
              <clipPath id="mp-below"><rect x={0} y={geo.y(0)} width={width} height={H} /></clipPath>
              <clipPath id="mp-reveal">
                <motion.rect x={0} y={0} width={width} height={H} style={{ transformOrigin: "0px 0px" }}
                  initial={reduce ? false : { scaleX: 0 }} whileInView={{ scaleX: 1 }} viewport={{ once: true, amount: 0.6 }}
                  transition={{ duration: 1.4, ease: [0.22, 1, 0.36, 1] }} />
              </clipPath>
            </defs>

            {turning && (
              <g>
                <rect x={geo.x(turning.start.index) - 2} y={PAD_T - 6} rx={6}
                  width={geo.x(turning.end.index) - geo.x(turning.start.index) + geo.step + 4} height={H - PAD_B - PAD_T + 12}
                  fill="var(--ink)" fillOpacity={0.06} />
                <text x={geo.x(turning.end.index) + geo.step + 2} y={PAD_T - 12} textAnchor="end" fontSize={11.5} fill="var(--ink-2)" fontWeight={500}>
                  Biggest swing {turning.start.label} to {turning.end.label}
                </text>
              </g>
            )}

            <g clipPath="url(#mp-reveal)">
              {geo.spans.map(({ p, a, b }) => {
                const pts = minutes.slice(a, b + 1);
                const d = area<TimelineMinute>().x((t) => geo.cx(t.index)).y0(geo.y(0)).y1((t) => geo.y(t.momentum)).curve(curveMonotoneX)(pts) ?? "";
                return (
                  <g key={p}>
                    <path d={d} fill="var(--home)" fillOpacity={0.85} clipPath="url(#mp-above)" />
                    <path d={d} fill="var(--away)" fillOpacity={0.85} clipPath="url(#mp-below)" />
                  </g>
                );
              })}
              {[...goalAt].map(([i, g]) => (
                <circle key={g.id} cx={geo.cx(i)} cy={g.team === "home" ? PAD_T - 2 + 8 : H - PAD_B - 8 + 2} r={3.5}
                  fill={`var(--${g.team})`} stroke="var(--surface-1)" strokeWidth={2} />
              ))}
            </g>

            {geo.spans.map(({ p, a, b }) => (
              <g key={p}>
                <line x1={geo.x(a)} x2={geo.x(b) + geo.step} y1={geo.y(0)} y2={geo.y(0)} stroke="var(--ink-4)" />
                <text x={geo.x(a)} y={H - 4} fontSize={11} fill="var(--ink-3)">{PERIOD_NAME[p] ?? ""}</text>
              </g>
            ))}

            {shownIdx != null && (
              <line x1={geo.cx(shownIdx)} x2={geo.cx(shownIdx)} y1={PAD_T - 6} y2={H - PAD_B + 6} stroke="var(--ink-2)" strokeWidth={1}
                opacity={hover != null ? 1 : 0} style={{ transition: `opacity ${hover != null ? "var(--tt-in-dur)" : "var(--tt-out-dur)"} ease-out` }} />
            )}
            <rect x={0} y={0} width={width} height={H} fill="transparent"
              onPointerMove={(e) => {
                const px = e.clientX - e.currentTarget.getBoundingClientRect().left;
                let best = 0;
                for (let i = 0; i < minutes.length; i++) if (Math.abs(geo.cx(i) - px) < Math.abs(geo.cx(best) - px)) best = i;
                setHover(best);
              }}
              onPointerLeave={() => setHover(null)} />
          </svg>
        )}
        {geo && shown && shownLeader && (
          <div data-open={hover != null} style={{ left: Math.min(Math.max(geo.cx(shownIdx!), 90), width - 90) }}
            className="t-tt absolute top-0 z-10 whitespace-nowrap rounded-lg bg-surface-3 px-2.5 py-1.5 text-[12px] text-ink shadow-[0_8px_24px_-8px_rgba(0,0,0,0.6)] ring-1 ring-line-strong">
            <span className="tabular mr-2 text-ink-2">{shown.label}</span>
            {shownLeader === "even" ? "Evenly matched" : (
              <><span className="mr-2 inline-block size-2 rounded-[2px] align-middle" style={{ background: `var(--${shownLeader})` }} />{name[shownLeader]} on top</>
            )}
            {goalAt.has(shownIdx!) && <span className="text-ink-2">, goal for {name[goalAt.get(shownIdx!)!.team]}</span>}
          </div>
        )}
      </div>
      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-[12.5px] text-ink-3">
        <span className="flex items-center gap-2"><span className="size-2.5 rounded-[3px] bg-home" />{m.home.name} above the line</span>
        <span className="flex items-center gap-2"><span className="size-2.5 rounded-[3px] bg-away" />{m.away.name} below</span>
        <span className="flex items-center gap-2"><span className="size-2 rounded-full border-2 border-ink-3" />Goal</span>
      </div>
    </div>
  );
}
