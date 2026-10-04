import { Link } from "react-router";
import { motion, useReducedMotion } from "motion/react";
import { ArrowUpRight } from "@phosphor-icons/react";
import type { MatchCard, MatchEvent } from "../../api/types";
import { PitchMarkings } from "../pitch/PitchMarkings";
import { PITCH, sy } from "../pitch/geometry";

/** Hero visual: the featured match's real shot map, with its best team goal drawn on repeat. */
export function FeaturedPitch({ m, shots, move, label }: { m: MatchCard; shots: MatchEvent[]; move: MatchEvent[]; label: string }) {
  const { L, W } = PITCH;
  return (
    <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}>
      <Link to={`/match/${encodeURIComponent(m.match_id)}`} aria-label={`Open ${m.home.name} ${m.home_score}-${m.away_score} ${m.away.name}, ${label}`}
        className="group block rounded-[24px] bg-white/[0.03] p-1.5 shadow-[0_40px_80px_-40px_rgba(0,8,4,0.9)] ring-1 ring-white/[0.07] transition-[box-shadow] duration-200 hover:ring-white/[0.14]"
        style={{ ["--home" as string]: m.home.color, ["--away" as string]: m.away.color }}>
        <div className="overflow-hidden rounded-[18px] bg-surface-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
          <svg viewBox={`-3 -3 ${L + 6} ${W + 6}`} className="block w-full" aria-hidden>
            <PitchMarkings pad={3} />
            <LoopingMove move={move} />
            {shots.map((e, i) => {
              const goal = e.result === "goal";
              const r = 0.6 + Math.sqrt(e.xg ?? 0.02) * 3.2;
              return (
                <motion.circle key={e.id} cx={e.x!} cy={sy(e.y!)} r={r} initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: 0.6 + i * 0.02, duration: 0.3 }} style={{ transformOrigin: `${e.x}px ${sy(e.y!)}px` }}
                  fill={`var(--${e.team})`} fillOpacity={goal ? 1 : 0.35} stroke={goal ? "var(--ink)" : `var(--${e.team})`} strokeWidth={goal ? 0.35 : 0.3} />
              );
            })}
          </svg>
          <div className="flex items-center gap-4 px-5 py-4">
            <div className="flex min-w-0 flex-1 items-center gap-3 text-[15px] font-medium text-ink">
              <TeamName name={m.home.name} color={m.home.color} />
              <span className="numeral shrink-0 text-[24px] leading-none text-ink">{m.home_score}<span className="px-1.5 text-ink-4">-</span>{m.away_score}</span>
              <TeamName name={m.away.name} color={m.away.color} />
            </div>
            <span className="hidden shrink-0 text-[13px] text-ink-3 sm:block lg:hidden xl:block">{label}</span>
            <span className="grid size-8 shrink-0 place-items-center rounded-full bg-surface-3 text-ink-2 transition-[transform,background-color,color] duration-200 ease-[var(--ease-smooth-out)] group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:bg-surface-4 group-hover:text-ink">
              <ArrowUpRight size={15} weight="bold" aria-hidden />
            </span>
          </div>
        </div>
      </Link>
    </motion.div>
  );
}

function TeamName({ name, color }: { name: string; color: string }) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: color }} />
      <span className="truncate">{name}</span>
    </span>
  );
}

/** Draws the goal's passing move on a loop; static under reduced motion. */
function LoopingMove({ move }: { move: MatchEvent[] }) {
  const reduce = useReducedMotion();
  if (move.length < 2) return null;
  if (reduce) {
    return (
      <g strokeLinecap="round" fill="none" pointerEvents="none" opacity={0.85}>
        {move.map((e) => (
          <line key={e.id} x1={e.x!} y1={sy(e.y!)} x2={e.end_x!} y2={sy(e.end_y!)} stroke="var(--ink)" strokeWidth={e.type === "carry" ? 0.3 : 0.45}
            strokeDasharray={e.type === "carry" ? "0.15 0.8" : undefined} />
        ))}
      </g>
    );
  }
  const total = move.length * 0.32 + 1.6;
  return (
    <g strokeLinecap="round" fill="none" pointerEvents="none">
      {move.map((e, i) => (
        <motion.line key={e.id} x1={e.x!} y1={sy(e.y!)} x2={e.end_x!} y2={sy(e.end_y!)} stroke="var(--ink)" strokeWidth={e.type === "carry" ? 0.3 : 0.45}
          strokeDasharray={e.type === "carry" ? "0.15 0.8" : undefined}
          initial={{ pathLength: 0, opacity: 0 }}
          animate={{ pathLength: [0, 1, 1, 1], opacity: [0, 0.9, 0.9, 0] }}
          transition={{ duration: total, times: [0, 0.12, 0.85, 1], delay: i * 0.32, repeat: Infinity, repeatDelay: 0.6, ease: "easeOut" }} />
      ))}
      {move.map((e, i) => (
        <motion.circle key={`d-${e.id}`} cx={e.x!} cy={sy(e.y!)} r={0.9} fill="var(--ink)"
          initial={{ opacity: 0 }} animate={{ opacity: [0, 1, 1, 0] }}
          transition={{ duration: total, times: [0, 0.08, 0.85, 1], delay: i * 0.32, repeat: Infinity, repeatDelay: 0.6 }} />
      ))}
    </g>
  );
}
