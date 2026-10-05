import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import type { MatchEvent, Side } from "../../api/types";
import { bucketKey, resolveSequence, useMatch } from "../../store/match";
import { clock, describe, isDefensive, isMove, isShot } from "../../lib/format";
import { PitchMarkings } from "./PitchMarkings";
import { PITCH, sy } from "./geometry";
import { useSize } from "../ui/useSize";

const { L, W } = PITCH;
const PAD = 2.6;
const DETAIL_MINUTES = 12;
const VB = { x: -PAD, y: -PAD, w: L + 2 * PAD, h: W + 2 * PAD };

export type PitchMode = "overview" | "detail" | "sequence";

const col = (s: Side) => `var(--${s})`;

export function usePitchEvents() {
  const data = useMatch((s) => s.data);
  const win = useMatch((s) => s.window);
  const focus = useMatch((s) => s.focus);
  const replay = useMatch((s) => s.replay);
  const seqId = replay?.sequenceId ?? (focus?.kind === "sequence" ? focus.id : undefined);
  const seq = seqId ? resolveSequence(data, seqId) : undefined;
  return useMemo(() => {
    if (!data) return { events: [] as MatchEvent[], mode: "overview" as PitchMode, seq };
    if (seq) {
      const ids = new Set(seq.event_ids);
      return { events: data.events.filter((e) => ids.has(e.id)), mode: "sequence" as PitchMode, seq };
    }
    const inWin = win
      ? data.events.filter((e) => {
          const i = data.bucketOf.get(bucketKey(e.period, e.minute)) ?? -1;
          return i >= win.from && i <= win.to;
        })
      : data.events;
    const span = win ? win.to - win.from + 1 : Infinity;
    return { events: inWin, mode: (span <= DETAIL_MINUTES ? "detail" : "overview") as PitchMode, seq };
  }, [data, win, seq]);
}

export function Pitch() {
  const data = useMatch((s) => s.data);
  const focus = useMatch((s) => s.focus);
  const replay = useMatch((s) => s.replay);
  const stepReplay = useMatch((s) => s.stepReplay);
  const focusEvent = useMatch((s) => s.focusEvent);
  const { events, mode } = usePitchEvents();
  const [hover, setHover] = useState<MatchEvent | null>(null);
  // keep the last hovered event while the tooltip fades out, so it doesn't empty mid-exit
  const [lastHover, setLastHover] = useState<MatchEvent | null>(null);
  if (hover && hover !== lastHover) setLastHover(hover);
  const [boxRef, box] = useSize<HTMLDivElement>();

  const reel = useMatch((s) => s.reel);
  const nextHighlight = useMatch((s) => s.nextHighlight);
  useEffect(() => {
    if (!replay?.playing) return;
    const t = setTimeout(stepReplay, replay.ms);
    return () => clearTimeout(t);
  }, [replay, stepReplay]);
  // highlights reel: hold the finished move on screen, then roll the next one
  useEffect(() => {
    if (!reel || !replay || replay.playing) return;
    const t = setTimeout(nextHighlight, 2200);
    return () => clearTimeout(t);
  }, [reel, replay, nextHighlight]);

  if (!data) return <div ref={boxRef} className="h-full w-full" />;
  if (!data.has.events && !data.has.shots) return <NoReplay />;
  // extend the grass sideways so the pitch fills its container edge to edge
  const aspect = box.width && box.height ? box.width / box.height : VB.w / VB.h;
  const vbW = Math.max(VB.w, VB.h * aspect);
  const padX = (vbW - L) / 2;
  const full = { x: -padX, y: VB.y, w: vbW, h: VB.h };
  // phones: zoom the camera onto the attack being shown, so its passes and names are big enough to read
  const vb = mode === "sequence" && box.width > 0 && box.width < 700 ? zoomTo(events, full, aspect) : full;
  const focusId = focus?.kind === "event" ? focus.id : null;
  const visible = mode === "sequence" && replay ? events.slice(0, replay.step + 1) : events;
  const current = mode === "sequence" && replay ? visible[visible.length - 1] : null;
  const located = visible.filter((e) => e.x != null && e.y != null);
  const shots = located.filter((e) => isShot(e.type));
  const shotIndex = new Map(shots.map((e, i) => [e.id, i]));
  const moves = mode === "overview" ? [] : located.filter((e) => isMove(e.type) || e.type === "carry" || e.type === "take_on");
  const defensive = mode === "detail" ? located.filter((e) => isDefensive(e.type)) : [];
  const focusEv = focusId ? data.eventById.get(focusId) : undefined;
  const win = useMatch.getState().window;
  const sceneKey = `${mode}:${win?.from ?? "all"}-${win?.to ?? "all"}:${replay?.sequenceId ?? ""}`;
  const hoverProps = (e: MatchEvent) => ({
    onPointerEnter: () => setHover(e),
    onPointerLeave: () => setHover(null),
    onClick: () => focusEvent(e.id),
    style: { cursor: "pointer" } as const,
  });

  return (
    <div ref={boxRef} className="relative h-full w-full select-none">
      <motion.svg initial={false} animate={{ viewBox: `${vb.x} ${vb.y} ${vb.w} ${vb.h}` }} transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="block h-full w-full" preserveAspectRatio="xMidYMid meet"
        role="img" aria-label={`Pitch showing ${visible.length} events`}>
        <defs>
          <filter id="pglow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="0.8" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          {(["home", "away"] as Side[]).map((s) => (
            <marker key={s} id={`arr-${s}`} viewBox="0 0 6 6" refX="4.6" refY="3" markerWidth="2.6" markerHeight="2.6" orient="auto-start-reverse">
              <path d="M0,0.4 L5.6,3 L0,5.6 L1.2,3 z" fill={col(s)} />
            </marker>
          ))}
        </defs>
        <PitchMarkings pad={PAD} padX={padX} />

        <motion.g key={sceneKey} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.35, ease: "easeOut" }}>
        {/* moves: dark under-stroke keeps team colours readable on grass */}
        <g strokeLinecap="round" fill="none">
          {moves.map((e, i) => {
            const ok = e.result === "success";
            const carry = e.type === "carry" || e.type === "take_on";
            const isFocus = e.id === focusId;
            const w = isFocus ? 0.6 : carry ? 0.24 : 0.34;
            const op = isFocus ? 1 : ok ? (mode === "sequence" ? 1 : 0.85) : 0.35;
            const geom = { x1: e.x!, y1: sy(e.y!), x2: e.end_x!, y2: sy(e.end_y!) };
            const anim = mode === "sequence"
              ? { initial: { pathLength: 0 }, animate: { pathLength: 1 }, transition: { duration: replay ? replay.ms / 1500 : 0.45, delay: replay ? 0 : i * 0.05, ease: "easeOut" as const } }
              : { initial: { pathLength: 0 }, animate: { pathLength: 1 }, transition: { duration: 0.4, delay: Math.min(i * 0.004, 0.45), ease: "easeOut" as const } };
            return (
              <g key={e.id} opacity={op} {...hoverProps(e)}>
                {!carry && <motion.line {...geom} {...anim} stroke="var(--on-grass)" strokeOpacity={0.45} strokeWidth={w + 0.3} />}
                <motion.line {...geom} {...anim} stroke={col(e.team)} strokeWidth={w} strokeDasharray={carry ? "0.12 0.7" : undefined}
                  strokeLinecap="round" markerEnd={!carry && ok ? `url(#arr-${e.team})` : undefined} />
                {!ok && !carry && <circle cx={e.end_x!} cy={sy(e.end_y!)} r={0.35} fill="none" stroke={col(e.team)} strokeWidth={0.18} />}
              </g>
            );
          })}
        </g>

        {defensive.map((e) => (
          <rect key={e.id} x={e.x! - 0.5} y={sy(e.y!) - 0.5} width={1} height={1} rx={0.15}
            transform={`rotate(45 ${e.x} ${sy(e.y!)})`} fill="var(--on-grass)" fillOpacity={0.4} stroke={col(e.team)} strokeWidth={0.2} {...hoverProps(e)} />
        ))}

        {/* shots: area ∝ xG; goals are solid with a white core */}
        {shots.map((e) => {
          const r = 0.6 + Math.sqrt(e.xg ?? 0.02) * 3.2;
          const goal = e.result === "goal";
          const isFocus = e.id === focusId;
          return (
            <g key={e.id} {...hoverProps(e)}>
              {(goal || isFocus || mode === "sequence") && (
                <line x1={e.x!} y1={sy(e.y!)} x2={e.team === "home" ? L : 0} y2={sy(e.end_y ?? W / 2)}
                  stroke="var(--ink)" strokeOpacity={goal ? 0.5 : 0.25} strokeWidth={0.16} strokeDasharray={goal ? undefined : "0.5 0.5"} />
              )}
              <motion.g initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1], delay: Math.min(shotIndex.get(e.id) ?? 0, 40) * 0.018 }}
                style={{ transformBox: "fill-box", transformOrigin: "center" }}>
                <circle cx={e.x!} cy={sy(e.y!)} r={Math.max(r + 1, 2.4)} fill="transparent" />
                <circle cx={e.x!} cy={sy(e.y!)} r={r} fill={col(e.team)} fillOpacity={goal ? 1 : 0.32}
                  stroke={goal ? "var(--ink)" : col(e.team)} strokeWidth={goal ? 0.32 : 0.3} filter={goal || isFocus ? "url(#pglow)" : undefined} />
                {goal && <circle cx={e.x!} cy={sy(e.y!)} r={Math.max(r * 0.3, 0.35)} fill="var(--ink)" />}
              </motion.g>
            </g>
          );
        })}

        </motion.g>
        {mode === "overview" && <GoalCallouts goals={shots.filter((e) => e.result === "goal")} />}
        {mode === "sequence" && <SequenceNodes evs={located} />}

        <AnimatePresence>
          {current && current.x != null && (
            <motion.g key="ball" initial={{ x: current.x, y: sy(current.y!) }}
              animate={{ x: current.end_x ?? current.x, y: sy(current.end_y ?? current.y!) }}
              transition={{ duration: 0.6, ease: "easeInOut" }} exit={{ opacity: 0 }}>
              <circle r={1.1} fill="var(--ink)" filter="url(#pglow)" />
              <circle r={0.45} fill="var(--on-grass)" />
            </motion.g>
          )}
        </AnimatePresence>

        {focusEv && focusEv.x != null && mode !== "sequence" && <FocusCallout e={focusEv} />}

        <g fontSize={1.45} fontWeight={600} fill="var(--ink)" fillOpacity={0.72}>
          <text x={L / 2 - 1.6} y={-0.75} textAnchor="end">{data.match.teams.home.name} attacking →</text>
          <text x={L / 2 + 1.6} y={-0.75} textAnchor="start">← {data.match.teams.away.name} attacking</text>
        </g>
      </motion.svg>
      {lastHover && <Tooltip e={lastHover} vb={vb} open={!!hover && hover.id !== focusId} />}
    </div>
  );
}

function Pill({ x, y, text, side, anchor = "middle", size = 1.5 }: { x: number; y: number; text: string; side?: Side; anchor?: "middle" | "start" | "end"; size?: number }) {
  const w = text.length * size * 0.56 + (side ? 2.4 : 1.6);
  const h = size * 1.75;
  const x0 = anchor === "middle" ? x - w / 2 : anchor === "end" ? x - w : x;
  return (
    <g pointerEvents="none">
      <rect x={x0} y={y - h / 2} width={w} height={h} rx={h / 2} fill="var(--bg)" fillOpacity={0.82} stroke="var(--ink)" strokeOpacity={0.14} strokeWidth={0.08} />
      {side && <circle cx={x0 + 1.15} cy={y} r={0.42} fill={col(side)} />}
      <text x={x0 + (side ? 1.9 : 0.8)} y={y + size * 0.36} fontSize={size} fontWeight={600} fill="var(--ink)">{text}</text>
    </g>
  );
}

function GoalCallouts({ goals }: { goals: MatchEvent[] }) {
  const placed: { x: number; y: number }[] = [];
  return (
    <g>
      {goals.map((e) => {
        let ly = sy(e.y!) - 4.2;
        while (placed.some((p) => Math.abs(p.x - e.x!) < 12 && Math.abs(p.y - ly) < 2.8)) ly -= 3;
        placed.push({ x: e.x!, y: ly });
        const label = `${e.player} ${clock(e.period, e.minute)}${e.type === "shot_penalty" ? " (pen)" : ""}`;
        const anchor = e.x! > L - 10 ? "end" : e.x! < 10 ? "start" : "middle";
        return (
          <g key={`c-${e.id}`}>
            <line x1={e.x!} y1={sy(e.y!) - 1} x2={e.x!} y2={ly + 1.2} stroke="var(--ink)" strokeOpacity={0.4} strokeWidth={0.1} />
            <Pill x={e.x!} y={ly} text={label} side={e.team} anchor={anchor} size={1.35} />
          </g>
        );
      })}
    </g>
  );
}

function FocusCallout({ e }: { e: MatchEvent }) {
  const reduce = useReducedMotion();
  const y = sy(e.y!);
  return (
    <g>
      <circle cx={e.x!} cy={y} r={2.4} fill="none" stroke="var(--ink)" strokeWidth={0.2}>
        {!reduce && <animate attributeName="r" values="2;3.6;2" dur="1.8s" repeatCount="indefinite" />}
        {!reduce && <animate attributeName="opacity" values="0.9;0.1;0.9" dur="1.8s" repeatCount="indefinite" />}
      </circle>
    </g>
  );
}

function SequenceNodes({ evs }: { evs: MatchEvent[] }) {
  const steps = evs.filter((e) => e.type !== "carry");
  const placed: { x: number; y: number }[] = [];
  let prev: string | null = null;
  return (
    <g>
      {steps.map((e, i) => {
        let name: string | null = null;
        if (e.player && e.player !== prev && placed.every((p) => Math.hypot(p.x - e.x!, p.y - e.y!) > 7)) {
          name = e.player;
          placed.push({ x: e.x!, y: e.y! });
        }
        prev = e.player;
        return (
          <motion.g key={`n-${e.id}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.05 }}>
            <circle cx={e.x!} cy={sy(e.y!)} r={1.25} fill={col(e.team)} stroke="var(--ink)" strokeWidth={0.22} />
            <text x={e.x!} y={sy(e.y!) + 0.46} textAnchor="middle" fontSize={1.25} fontWeight={700} fill="var(--on-grass)">{i + 1}</text>
            {name && <Pill x={e.x!} y={sy(e.y!) - 3.1} text={name} size={1.3} />}
          </motion.g>
        );
      })}
    </g>
  );
}

/** Event tooltip (transitions.dev tooltip): fades and scales in over 150ms, out in 50ms. */
function Tooltip({ e, vb, open }: { e: MatchEvent; vb: typeof VB; open: boolean }) {
  const left = `${((e.x! - vb.x) / vb.w) * 100}%`;
  const top = `${((sy(e.y!) - vb.y) / vb.h) * 100}%`;
  return (
    <div className="pointer-events-none absolute z-10 -translate-y-[calc(100%+14px)] whitespace-nowrap" style={{ left, top }}>
      <div data-open={open} className="t-tt glass flex items-center gap-2 rounded-xl px-3 py-2 text-[12.5px] shadow-2xl">
        <span className="size-2 rounded-full" style={{ background: col(e.team) }} aria-hidden />
        <span className="font-semibold text-ink">{describe(e)}</span>
        {isShot(e.type) && e.xg != null && <span className="tabular text-ink-2">{Math.round(e.xg * 100)}% chance</span>}
      </div>
    </div>
  );
}

/** Lite matches have no event stream: an empty pitch that says so, instead of a blank or broken one. */
function NoReplay() {
  return (
    <div className="relative h-full w-full">
      <svg viewBox={`${VB.x} ${VB.y} ${VB.w} ${VB.h}`} className="block h-full w-full opacity-60" preserveAspectRatio="xMidYMid slice" aria-hidden>
        <PitchMarkings pad={PAD} />
      </svg>
      <div className="absolute inset-0 grid place-items-center p-6">
        <p className="glass max-w-[36ch] rounded-2xl px-5 py-4 text-center text-[14px] leading-[1.5] text-ink-2">
          <span className="block font-semibold text-ink">No pitch replay for this match</span>
          We have the score and the key moments, but not every touch of the ball.
        </p>
      </div>
    </div>
  );
}

type Box = { x: number; y: number; w: number; h: number };

/** A viewBox around the events (with room for labels), at the container's aspect, never smaller than a third of the pitch. */
function zoomTo(evs: MatchEvent[], full: Box, aspect: number): Box {
  const xs: number[] = [], ys: number[] = [];
  for (const e of evs) {
    if (e.x == null || e.y == null) continue;
    xs.push(e.x); ys.push(sy(e.y));
    if (e.end_x != null && e.end_y != null) { xs.push(e.end_x); ys.push(sy(e.end_y)); }
  }
  if (!xs.length) return full;
  const pad = 7;
  let x0 = Math.min(...xs) - pad, x1 = Math.max(...xs) + pad;
  let y0 = Math.min(...ys) - pad - 3, y1 = Math.max(...ys) + pad;
  let w = Math.max(x1 - x0, full.w / 2.4), h = Math.max(y1 - y0, w / aspect);
  w = Math.max(w, h * aspect);
  h = w / aspect;
  if (w >= full.w || h >= full.h) return full;
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  x0 = Math.min(Math.max(cx - w / 2, full.x), full.x + full.w - w);
  y0 = Math.min(Math.max(cy - h / 2, full.y), full.y + full.h - h);
  return { x: x0, y: y0, w, h };
}
