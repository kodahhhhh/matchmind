import { useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { Play, Stop } from "@phosphor-icons/react";
import { CommentaryFeed } from "./CommentaryFeed";
import type { MatchEvent, Sequence } from "../../api/types";
import { useMatch } from "../../store/match";
import { PitchMarkings } from "../pitch/PitchMarkings";
import { PITCH, sy } from "../pitch/geometry";

const EASE = [0.22, 1, 0.36, 1] as const;
const VIEWS = [["top", "Most dangerous"], ["feed", "Live commentary"]] as const;

export function Sequences() {
  const data = useMatch((s) => s.data);
  const focus = useMatch((s) => s.focus);
  const replay = useMatch((s) => s.replay);
  const focusSequence = useMatch((s) => s.focusSequence);
  const startReplay = useMatch((s) => s.startReplay);
  const [view, setView] = useState<"top" | "feed">("top");
  const reduce = useReducedMotion();
  if (!data) return null;

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="sticky top-0 z-10 bg-surface-1 px-4 pb-3">
        <div role="group" aria-label="Moments view" className="flex rounded-full bg-surface-2 p-1 ring-1 ring-line">
          {VIEWS.map(([v, label]) => {
            const on = view === v;
            return (
              <button key={v} type="button" aria-pressed={on} onClick={() => setView(v)}
                className={`relative min-h-8 flex-1 rounded-full py-1.5 text-[13px] font-medium transition-colors duration-200 ${on ? "text-bg" : "text-ink-3 hover:text-ink"}`}>
                {on && <motion.span layoutId="moments-view-pill" className="absolute inset-0 rounded-full bg-ink" transition={{ duration: reduce ? 0 : 0.25, ease: EASE }} />}
                <span className="relative">{label}</span>
              </button>
            );
          })}
        </div>
      </div>
      {view === "feed" ? <CommentaryFeed /> : (
        <div className="px-4 pb-4">
          <p className="px-1 pb-3 text-pretty text-[13.5px] leading-[1.55] text-ink-3">
            Ranked by the threat each move created (VAEP). Select a move to draw it on the pitch, or play it back.
          </p>
          <ol className="space-y-2.5" aria-label="Most dangerous moves">
            {data.sequences.map((s, i) => {
              const active = focus?.kind === "sequence" && focus.id === s.id;
              const playing = replay?.sequenceId === s.id && replay.playing;
              const evs = s.event_ids.map((id) => data.eventById.get(id)).filter((e): e is MatchEvent => !!e);
              const team = data.match.teams[s.team].name;
              return (
                <motion.li key={s.id} className="relative"
                  initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6, filter: "blur(2px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                  transition={{ duration: 0.3, delay: Math.min(i * 0.04, 0.24), ease: EASE }}>
                  <button type="button" onClick={() => focusSequence(s.id)} aria-current={active || undefined}
                    aria-label={`${s.start.label}, ${team}, ${outcomeLabel(s)}. ${s.players.join(", ")}. Draw on the pitch`}
                    className={`flex w-full gap-3.5 rounded-2xl p-2 pr-3 text-left ring-1 transition-[background-color,box-shadow,transform] duration-150 ease-out active:scale-[0.99] ${active ? "bg-surface-3 ring-line-strong" : "bg-surface-2 ring-line hover:bg-surface-3"}`}>
                    <Thumb evs={evs} team={s.team} />
                    <span className="flex min-w-0 flex-1 flex-col py-1">
                      <span className="flex items-center gap-2 pr-9">
                        <span className="numeral text-[22px] leading-none text-ink">{s.start.label}</span>
                        <Outcome s={s} />
                      </span>
                      <span className="mt-1.5 flex min-w-0 items-center gap-1.5 text-[12.5px] text-ink-2">
                        <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: `var(--${s.team})` }} aria-hidden />
                        <span className="truncate">{team}</span>
                      </span>
                      <span className="mt-1 line-clamp-1 text-[12.5px] text-ink-3">{s.players.join(" → ")}</span>
                      <span className="tabular mt-auto pt-1.5 text-[12px] text-ink-4">
                        {s.n_events} touches in {Math.round(s.duration)} seconds{s.xg > 0 ? ` · ${Math.round(Math.min(s.xg, 0.99) * 100)}% chance of a goal` : ""}
                      </span>
                    </span>
                  </button>
                  <button type="button" onClick={() => startReplay(s.id)} aria-label={playing ? `Playing the ${s.start.label} move` : `Play the ${s.start.label} move`}
                    className="absolute right-2.5 top-2.5 flex size-8 items-center justify-center rounded-full bg-surface-4 text-ink transition-[background-color,transform] duration-150 ease-out hover:bg-ink hover:text-bg active:scale-[0.94]">
                    {playing ? <Stop size={12} weight="fill" className="motion-safe:animate-pulse" aria-hidden /> : <Play size={12} weight="fill" aria-hidden />}
                  </button>
                </motion.li>
              );
            })}
          </ol>
        </div>
      )}
    </div>
  );
}

const outcomeLabel = (s: Sequence) => (s.outcome === "goal" ? "Goal" : s.outcome === "shot" ? "Shot" : "Lost ball");

function Outcome({ s }: { s: Sequence }) {
  if (s.outcome === "goal") return <span className="rounded-full bg-ink px-2 py-[1px] text-[12px] font-semibold text-bg">Goal</span>;
  return <span className="rounded-full bg-surface-4 px-2 py-[1px] text-[12px] font-medium text-ink-2">{outcomeLabel(s)}</span>;
}

function Thumb({ evs, team }: { evs: MatchEvent[]; team: "home" | "away" }) {
  const { L, W } = PITCH;
  const pts = evs.filter((e) => e.x != null && e.y != null);
  return (
    <svg viewBox={`-1.5 -1.5 ${L + 3} ${W + 3}`} className="h-[86px] w-[132px] shrink-0 overflow-hidden rounded-lg" aria-hidden>
      <PitchMarkings pad={1.5} texture={false} lineWidth={0.5} />
      <g stroke={`var(--${team})`} strokeLinecap="round" fill="none">
        {pts.map((e) => (
          <line key={e.id} x1={e.x!} y1={sy(e.y!)} x2={e.end_x!} y2={sy(e.end_y!)} strokeWidth={e.type === "carry" ? 0.7 : 1.1}
            strokeDasharray={e.type === "carry" ? "0.4 1.6" : undefined} />
        ))}
      </g>
      {pts.filter((e) => e.type.startsWith("shot")).map((e) => (
        <circle key={e.id} cx={e.x!} cy={sy(e.y!)} r={2.6} fill={e.result === "goal" ? "var(--ink)" : `var(--${team})`} stroke={`var(--${team})`} strokeWidth={0.8} />
      ))}
      {pts[0] && <circle cx={pts[0].x!} cy={sy(pts[0].y!)} r={1.6} fill="var(--ink)" />}
    </svg>
  );
}
