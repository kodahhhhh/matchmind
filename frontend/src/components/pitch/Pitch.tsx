import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import type { MatchEvent, Side } from "../../api/types";
import { bucketKey, useMatch } from "../../store/match";
import { clock, describe, isDefensive, isMove, isShot, xg } from "../../lib/format";
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
  const seq = seqId ? data?.sequences.find((s) => s.id === seqId) : undefined;
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
  const [boxRef, box] = useSize<HTMLDivElement>();

  useEffect(() => {
    if (!replay?.playing) return;
    const t = setTimeout(stepReplay, 700);
    return () => clearTimeout(t);
  }, [replay, stepReplay]);

  if (!data) return <div ref={boxRef} className="h-full w-full" />;
  // extend the grass sideways so the pitch fills its container edge to edge
  const aspect = box.width && box.height ? box.width / box.height : VB.w / VB.h;
  const vbW = Math.max(VB.w, VB.h * aspect);
  const padX = (vbW - L) / 2;
  const vb = { x: -padX, y: VB.y, w: vbW, h: VB.h };
  const focusId = focus?.kind === "event" ? focus.id : null;
  const visible = mode === "sequence" && replay ? events.slice(0, replay.step + 1) : events;
  const current = mode === "sequence" && replay ? visible[visible.length - 1] : null;
  const located = visible.filter((e) => e.x != null && e.y != null);
  const shots = located.filter((e) => isShot(e.type));
  const moves = mode === "overview" ? [] : located.filter((e) => isMove(e.type) || e.type === "carry" || e.type === "take_on");
  const defensive = mode === "detail" ? located.filter((e) => isDefensive(e.type)) : [];
  const focusEv = focusId ? data.eventById.get(focusId) : undefined;
  const hoverProps = (e: MatchEvent) => ({
    onPointerEnter: () => setHover(e),
    onPointerLeave: () => setHover(null),
    onClick: () => focusEvent(e.id),
    style: { cursor: "pointer" } as const,
  });

  return (
    <div ref={boxRef} className="relative h-full w-full select-none">
      <svg viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`} className="block h-full w-full" preserveAspectRatio="xMidYMid meet"
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
              ? { initial: { pathLength: 0 }, animate: { pathLength: 1 }, transition: { duration: 0.45, delay: replay ? 0 : i * 0.05, ease: "easeOut" as const } }
              : {};
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
                  stroke="#fff" strokeOpacity={goal ? 0.5 : 0.25} strokeWidth={0.16} strokeDasharray={goal ? undefined : "0.5 0.5"} />
              )}
              <circle cx={e.x!} cy={sy(e.y!)} r={Math.max(r + 1, 2.4)} fill="transparent" />
              <circle cx={e.x!} cy={sy(e.y!)} r={r} fill={col(e.team)} fillOpacity={goal ? 1 : 0.32}
                stroke={goal ? "#fff" : col(e.team)} strokeWidth={goal ? 0.32 : 0.3} filter={goal || isFocus ? "url(#pglow)" : undefined} />
              {goal && <circle cx={e.x!} cy={sy(e.y!)} r={Math.max(r * 0.3, 0.35)} fill="#fff" />}
            </g>
          );
        })}

        {mode === "overview" && <GoalCallouts goals={shots.filter((e) => e.result === "goal")} />}
        {mode === "sequence" && <SequenceNodes evs={located} />}

        <AnimatePresence>
          {current && current.x != null && (
            <motion.g key="ball" initial={{ x: current.x, y: sy(current.y!) }}
              animate={{ x: current.end_x ?? current.x, y: sy(current.end_y ?? current.y!) }}
              transition={{ duration: 0.6, ease: "easeInOut" }} exit={{ opacity: 0 }}>
              <circle r={1.1} fill="#fff" filter="url(#pglow)" />
              <circle r={0.45} fill="var(--on-grass)" />
            </motion.g>
          )}
        </AnimatePresence>

        {focusEv && focusEv.x != null && mode !== "sequence" && <FocusCallout e={focusEv} />}

        <g fontSize={1.5} fontWeight={700} letterSpacing={0.15} fill="#fff" fillOpacity={0.7} textAnchor="middle">
          <text x={L / 2} y={-0.8}>{data.match.teams.home.short} →  attacking  ← {data.match.teams.away.short}</text>
        </g>
      </svg>
      {hover && hover.id !== focusId && <Tooltip e={hover} vb={vb} />}
    </div>
  );
}

function Pill({ x, y, text, side, anchor = "middle", size = 1.5 }: { x: number; y: number; text: string; side?: Side; anchor?: "middle" | "start" | "end"; size?: number }) {
  const w = text.length * size * 0.56 + (side ? 2.4 : 1.6);
  const h = size * 1.75;
  const x0 = anchor === "middle" ? x - w / 2 : anchor === "end" ? x - w : x;
  return (
    <g pointerEvents="none">
      <rect x={x0} y={y - h / 2} width={w} height={h} rx={h / 2} fill="rgba(6,10,8,0.82)" stroke="rgba(255,255,255,0.14)" strokeWidth={0.08} />
      {side && <circle cx={x0 + 1.15} cy={y} r={0.42} fill={col(side)} />}
      <text x={x0 + (side ? 1.9 : 0.8)} y={y + size * 0.36} fontSize={size} fontWeight={600} fill="#fff">{text}</text>
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
        const label = `${e.player} ${clock(e.period, e.minute)}${e.type === "shot_penalty" ? " (P)" : ""}`;
        const anchor = e.x! > L - 10 ? "end" : e.x! < 10 ? "start" : "middle";
        return (
          <g key={`c-${e.id}`}>
            <line x1={e.x!} y1={sy(e.y!) - 1} x2={e.x!} y2={ly + 1.2} stroke="#fff" strokeOpacity={0.4} strokeWidth={0.1} />
            <Pill x={e.x!} y={ly} text={label} side={e.team} anchor={anchor} size={1.35} />
          </g>
        );
      })}
    </g>
  );
}

function FocusCallout({ e }: { e: MatchEvent }) {
  const y = sy(e.y!);
  const above = y > 8;
  return (
    <g>
      <circle cx={e.x!} cy={y} r={2.4} fill="none" stroke="#fff" strokeWidth={0.2}>
        <animate attributeName="r" values="2;3.6;2" dur="1.8s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.9;0.1;0.9" dur="1.8s" repeatCount="indefinite" />
      </circle>
      <Pill x={e.x!} y={above ? y - 4.6 : y + 4.6} text={describe(e)} side={e.team} anchor={e.x! > L - 14 ? "end" : e.x! < 14 ? "start" : "middle"} />
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
            <circle cx={e.x!} cy={sy(e.y!)} r={1.25} fill={col(e.team)} stroke="#fff" strokeWidth={0.22} />
            <text x={e.x!} y={sy(e.y!) + 0.46} textAnchor="middle" fontSize={1.25} fontWeight={700} fill="var(--on-grass)">{i + 1}</text>
            {name && <Pill x={e.x!} y={sy(e.y!) - 3.1} text={name} size={1.3} />}
          </motion.g>
        );
      })}
    </g>
  );
}

function Tooltip({ e, vb }: { e: MatchEvent; vb: typeof VB }) {
  const left = `${((e.x! - vb.x) / vb.w) * 100}%`;
  const top = `${((sy(e.y!) - vb.y) / vb.h) * 100}%`;
  return (
    <div className="glass pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-[calc(100%+16px)] rounded-xl px-3 py-2 text-xs shadow-2xl"
      style={{ left, top }}>
      <div className="flex items-center gap-2 whitespace-nowrap">
        <span className="h-2 w-2 rounded-full" style={{ background: col(e.team) }} />
        <span className="font-semibold text-ink">{describe(e)}</span>
        {isShot(e.type) && <span className="tabular text-ink-2">{xg(e.xg)} xG</span>}
      </div>
    </div>
  );
}
