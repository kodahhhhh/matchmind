import { useMemo, useState, useEffect } from "react";
import { AnimatePresence, motion } from "motion/react";
import type { MatchEvent, Side } from "../../api/types";
import { bucketKey, useMatch } from "../../store/match";
import { describe, isDefensive, isMove, isShot, xg } from "../../lib/format";
import { PITCH, PitchMarkings } from "./PitchMarkings";

const { L, W } = PITCH;
const sy = (y: number) => W - y; // SPADL y (up) → SVG y (down)
const DETAIL_MINUTES = 12; // windows up to this long show every action

type Mode = "overview" | "detail" | "sequence";

export function Pitch() {
  const data = useMatch((s) => s.data);
  const win = useMatch((s) => s.window);
  const focus = useMatch((s) => s.focus);
  const replay = useMatch((s) => s.replay);
  const stepReplay = useMatch((s) => s.stepReplay);
  const [hover, setHover] = useState<MatchEvent | null>(null);

  const seq = focus?.kind === "sequence" || replay
    ? data?.sequences.find((s) => s.id === (replay?.sequenceId ?? (focus as { id: string }).id))
    : undefined;

  const { events, mode } = useMemo(() => {
    if (!data) return { events: [] as MatchEvent[], mode: "overview" as Mode };
    if (seq) {
      const ids = new Set(seq.event_ids);
      return { events: data.events.filter((e) => ids.has(e.id)), mode: "sequence" as Mode };
    }
    const inWin = win
      ? data.events.filter((e) => {
          const i = data.bucketOf.get(bucketKey(e.period, e.minute)) ?? -1;
          return i >= win.from && i <= win.to;
        })
      : data.events;
    const span = win ? win.to - win.from + 1 : Infinity;
    return { events: inWin, mode: (span <= DETAIL_MINUTES ? "detail" : "overview") as Mode };
  }, [data, win, seq]);

  // replay ticker
  useEffect(() => {
    if (!replay?.playing) return;
    const t = setTimeout(stepReplay, 650);
    return () => clearTimeout(t);
  }, [replay, stepReplay]);

  if (!data) return null;
  const color = (s: Side) => `var(--${s})`;
  const focusId = focus?.kind === "event" ? focus.id : null;
  const visible = mode === "sequence" && replay ? events.slice(0, replay.step + 1) : events;
  const current = mode === "sequence" && replay ? visible[visible.length - 1] : null;
  const shots = visible.filter((e) => isShot(e.type) && e.x != null);
  const moves = visible.filter((e) => (isMove(e.type) || e.type === "carry" || e.type === "take_on") && e.x != null);
  const defensive = mode !== "overview" ? visible.filter((e) => isDefensive(e.type) && e.x != null) : [];
  const focusEv = focusId ? data.eventById.get(focusId) : undefined;
  const { home, away } = data.match.teams;

  return (
    <div className="relative h-full w-full select-none">
      <svg viewBox={`-4 -4 ${L + 8} ${W + 8}`} className="h-full w-full" preserveAspectRatio="xMidYMid meet" role="img"
        aria-label={`Pitch showing ${visible.length} events`}>
        <defs>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="0.9" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          {(["home", "away"] as Side[]).map((s) => (
            <marker key={s} id={`arrow-${s}`} viewBox="0 0 6 6" refX="5" refY="3" markerWidth="3.2" markerHeight="3.2" orient="auto-start-reverse">
              <path d="M0,0.6 L5.4,3 L0,5.4 z" fill={color(s)} />
            </marker>
          ))}
        </defs>
        <PitchMarkings />

        {/* moves */}
        <g strokeLinecap="round" fill="none">
          {moves.map((e, i) => {
            const ok = e.result === "success";
            const carry = e.type === "carry" || e.type === "take_on";
            const isFocus = e.id === focusId;
            if (mode === "overview") {
              if (carry || !ok) return null;
              return <line key={e.id} x1={e.x!} y1={sy(e.y!)} x2={e.end_x!} y2={sy(e.end_y!)} stroke={color(e.team)} strokeWidth={0.16} opacity={0.11} />;
            }
            const common = {
              stroke: color(e.team),
              strokeWidth: isFocus ? 0.55 : carry ? 0.22 : 0.3,
              opacity: isFocus ? 1 : ok ? (mode === "sequence" ? 0.95 : 0.7) : 0.3,
              strokeDasharray: carry ? "0.7 0.55" : undefined,
              markerEnd: !carry && ok ? `url(#arrow-${e.team})` : undefined,
              onPointerEnter: () => setHover(e),
              onPointerLeave: () => setHover(null),
              style: { cursor: "pointer" },
            };
            return mode === "sequence" ? (
              <motion.line key={e.id} x1={e.x!} y1={sy(e.y!)} x2={e.end_x!} y2={sy(e.end_y!)} {...common}
                initial={{ pathLength: 0, opacity: 0 }} animate={{ pathLength: 1, opacity: common.opacity }}
                transition={{ duration: 0.5, delay: replay ? 0 : i * 0.06, ease: "easeOut" }} />
            ) : (
              <line key={e.id} x1={e.x!} y1={sy(e.y!)} x2={e.end_x!} y2={sy(e.end_y!)} {...common} />
            );
          })}
          {/* failed pass end-marks */}
          {mode !== "overview" && moves.filter((e) => e.result === "fail" && isMove(e.type)).map((e) => (
            <g key={`x-${e.id}`} stroke={color(e.team)} strokeWidth={0.22} opacity={0.45}>
              <line x1={e.end_x! - 0.5} y1={sy(e.end_y!) - 0.5} x2={e.end_x! + 0.5} y2={sy(e.end_y!) + 0.5} />
              <line x1={e.end_x! - 0.5} y1={sy(e.end_y!) + 0.5} x2={e.end_x! + 0.5} y2={sy(e.end_y!) - 0.5} />
            </g>
          ))}
        </g>

        {/* defensive actions */}
        <g>
          {defensive.map((e) => (
            <rect key={e.id} x={e.x! - 0.45} y={sy(e.y!) - 0.45} width={0.9} height={0.9} transform={`rotate(45 ${e.x} ${sy(e.y!)})`}
              fill="none" stroke={color(e.team)} strokeWidth={0.18} opacity={0.6}
              onPointerEnter={() => setHover(e)} onPointerLeave={() => setHover(null)} />
          ))}
        </g>

        {/* shots: area ∝ xG */}
        <g>
          {shots.map((e) => {
            const r = 0.55 + Math.sqrt(e.xg ?? 0.02) * 3.1;
            const goal = e.result === "goal";
            const isFocus = e.id === focusId;
            const gx = e.team === "home" ? L : 0;
            return (
              <g key={e.id} onPointerEnter={() => setHover(e)} onPointerLeave={() => setHover(null)} style={{ cursor: "pointer" }}>
                {(goal || isFocus || mode !== "overview") && (
                  <line x1={e.x!} y1={sy(e.y!)} x2={gx} y2={sy(e.end_y ?? W / 2)} stroke={color(e.team)} strokeWidth={0.14}
                    opacity={goal ? 0.55 : 0.25} />
                )}
                <circle cx={e.x!} cy={sy(e.y!)} r={Math.max(r, 2.2)} fill="transparent" />
                <circle cx={e.x!} cy={sy(e.y!)} r={r + 0.35} fill="var(--pitch)" opacity={0.9} />
                <circle cx={e.x!} cy={sy(e.y!)} r={r} fill={color(e.team)} fillOpacity={goal ? 0.95 : 0.18}
                  stroke={color(e.team)} strokeWidth={goal ? 0 : 0.28} filter={goal || isFocus ? "url(#glow)" : undefined} />
                {goal && <circle cx={e.x!} cy={sy(e.y!)} r={r * 0.32} fill="var(--pitch)" />}
              </g>
            );
          })}
        </g>

        {/* sequence step numbers + names */}
        {mode === "sequence" && (
          <g>
            {seqLabels(visible).map(({ e, n, name }) => (
              <g key={`n-${e.id}`}>
                <circle cx={e.x!} cy={sy(e.y!)} r={1.05} fill="var(--surface-1)" stroke={color(e.team)} strokeWidth={0.2} />
                <text x={e.x!} y={sy(e.y!) + 0.42} textAnchor="middle" fontSize={1.15} fontWeight={600} fill="var(--ink)">{n}</text>
                {name && (
                  <text x={e.x!} y={sy(e.y!) - 1.7} textAnchor="middle" fontSize={1.5} fill="var(--ink-2)" style={{ paintOrder: "stroke" }}
                    stroke="var(--pitch)" strokeWidth={0.5}>{name}</text>
                )}
              </g>
            ))}
          </g>
        )}

        {/* replay ball */}
        <AnimatePresence>
          {current && current.x != null && (
            <motion.circle key="ball" r={0.75} fill="var(--ink)" filter="url(#glow)"
              initial={{ cx: current.x, cy: sy(current.y!) }}
              animate={{ cx: current.end_x ?? current.x, cy: sy(current.end_y ?? current.y!) }}
              transition={{ duration: 0.55, ease: "easeInOut" }} exit={{ opacity: 0 }} />
          )}
        </AnimatePresence>

        {/* focused event tag */}
        {focusEv && focusEv.x != null && (
          <g>
            <circle cx={focusEv.x} cy={sy(focusEv.y!)} r={2.6} fill="none" stroke="var(--ink)" strokeWidth={0.18} opacity={0.8}>
              <animate attributeName="r" values="2.2;3.4;2.2" dur="2s" repeatCount="indefinite" />
              <animate attributeName="opacity" values="0.8;0.15;0.8" dur="2s" repeatCount="indefinite" />
            </circle>
          </g>
        )}

        {/* attacking direction */}
        <g fontSize={1.7} fontWeight={600} letterSpacing={0.1}>
          <text x={1} y={W + 3.1} fill="var(--ink-3)">{home.short}</text>
          <path d={`M ${6.2} ${W + 2.55} h 5`} stroke={color("home")} strokeWidth={0.25} markerEnd="url(#arrow-home)" />
          <text x={L - 1} y={W + 3.1} textAnchor="end" fill="var(--ink-3)">{away.short}</text>
          <path d={`M ${L - 6.2} ${W + 2.55} h -5`} stroke={color("away")} strokeWidth={0.25} markerEnd="url(#arrow-away)" />
        </g>
      </svg>

      {hover && <EventTooltip e={hover} />}
      <PitchLegend mode={mode} count={visible.length} />
    </div>
  );
}

/** Step numbers for a sequence; a name label only when the player changes and no other label is within 6 m. */
function seqLabels(evs: MatchEvent[]) {
  const steps = evs.filter((e) => e.x != null && e.type !== "carry");
  const placed: { x: number; y: number }[] = [];
  let prev: string | null = null;
  return steps.map((e, i) => {
    let name: string | null = null;
    if (e.player && e.player !== prev && placed.every((p) => Math.hypot(p.x - e.x!, p.y - e.y!) > 6)) {
      name = e.player;
      placed.push({ x: e.x!, y: e.y! });
    }
    prev = e.player;
    return { e, n: i + 1, name };
  });
}

function EventTooltip({ e }: { e: MatchEvent }) {
  const left = `${((e.x! + 4) / (L + 8)) * 100}%`;
  const top = `${((sy(e.y!) + 4) / (W + 8)) * 100}%`;
  return (
    <div className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-[calc(100%+14px)] rounded-lg border border-line-strong bg-surface-2/95 px-3 py-2 text-xs shadow-xl backdrop-blur"
      style={{ left, top }}>
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full" style={{ background: `var(--${e.team})` }} />
        <span className="font-medium text-ink">{describe(e)}</span>
      </div>
      {isShot(e.type) && <div className="mt-1 text-ink-2"><span className="tabular font-semibold text-ink">{xg(e.xg)}</span> xG</div>}
    </div>
  );
}

function PitchLegend({ mode, count }: { mode: Mode; count: number }) {
  const label = mode === "overview" ? "Whole window · completed passes + shots" : mode === "detail" ? "Every action in window" : "Sequence";
  return (
    <div className="pointer-events-none absolute left-3 top-2 flex items-center gap-3 text-[11px] text-ink-3">
      <span>{label}</span>
      <span className="tabular text-ink-4">{count} events</span>
      <span className="flex items-center gap-1.5"><svg width="14" height="14"><circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" strokeWidth="1.2" /></svg>shot, size = xG</span>
      <span className="flex items-center gap-1.5"><svg width="14" height="14"><circle cx="7" cy="7" r="5" fill="currentColor" /><circle cx="7" cy="7" r="1.8" fill="var(--bg)" /></svg>goal</span>
    </div>
  );
}

