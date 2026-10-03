import { useState } from "react";
import { motion } from "motion/react";
import { CommentaryFeed } from "./CommentaryFeed";
import type { MatchEvent, Sequence } from "../../api/types";
import { useMatch } from "../../store/match";
import { xg } from "../../lib/format";
import { PitchMarkings } from "../pitch/PitchMarkings";
import { PITCH, sy } from "../pitch/geometry";

export function Sequences() {
  const data = useMatch((s) => s.data);
  const focus = useMatch((s) => s.focus);
  const replay = useMatch((s) => s.replay);
  const focusSequence = useMatch((s) => s.focusSequence);
  const startReplay = useMatch((s) => s.startReplay);
  const [view, setView] = useState<"top" | "feed">("top");
  if (!data) return null;

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="sticky top-0 z-10 bg-surface-1 px-4 pb-3">
        <div className="flex rounded-xl bg-surface-2 p-1">
          {([["top", "Most dangerous"], ["feed", "Live commentary"]] as const).map(([v, label]) => (
            <button key={v} onClick={() => setView(v)}
              className={`flex-1 rounded-lg py-1.5 text-[12.5px] font-medium transition ${view === v ? "bg-surface-4 text-ink shadow" : "text-ink-3 hover:text-ink-2"}`}>{label}</button>
          ))}
        </div>
      </div>
      {view === "feed" ? <CommentaryFeed /> : (
      <div className="px-4 pb-4">
      <div className="px-1 pb-3">
        <p className="text-[13px] leading-relaxed text-ink-3">Ranked by how much threat each move created (VAEP). Click to draw it, ▶ to replay.</p>
      </div>
      <ol className="space-y-2.5">
        {data.sequences.map((s, i) => {
          const active = focus?.kind === "sequence" && focus.id === s.id;
          const playing = replay?.sequenceId === s.id && replay.playing;
          const evs = s.event_ids.map((id) => data.eventById.get(id)).filter((e): e is MatchEvent => !!e);
          return (
            <motion.li key={s.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
              <div onClick={() => focusSequence(s.id)} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && focusSequence(s.id)}
                className={`group flex cursor-pointer gap-3.5 rounded-2xl p-2.5 ring-1 transition ${active ? "bg-surface-3 ring-white/15" : "bg-surface-2 ring-line hover:bg-surface-3"}`}>
                <Thumb evs={evs} team={s.team} />
                <div className="flex min-w-0 flex-1 flex-col py-0.5">
                  <div className="flex items-center gap-2">
                    <span className="display text-[22px] leading-none text-ink">{s.start.label}</span>
                    <Outcome s={s} />
                    <button onClick={(e) => { e.stopPropagation(); startReplay(s.id); }} aria-label="Replay"
                      className="ml-auto flex h-8 w-8 items-center justify-center rounded-full bg-white/8 text-ink transition hover:bg-white/15">
                      {playing ? <span className="h-2.5 w-2.5 animate-pulse rounded-sm bg-ink" />
                        : <svg width="10" height="12" viewBox="0 0 10 12"><path d="M1.5 1.2 9 6l-7.5 4.8z" fill="currentColor" /></svg>}
                    </button>
                  </div>
                  <div className="mt-1 flex items-center gap-1.5 text-[12px] text-ink-2">
                    <span className="h-2 w-2 rounded-full" style={{ background: `var(--${s.team})` }} />
                    {data.match.teams[s.team].name}
                  </div>
                  <div className="mt-1 line-clamp-1 text-[12px] text-ink-3">{s.players.join(" → ")}</div>
                  <div className="mt-auto pt-1.5 text-[11.5px] tabular text-ink-4">{s.n_events} actions · {Math.round(s.duration)}s{s.xg > 0 ? ` · ${xg(s.xg)} xG` : ""}</div>
                </div>
              </div>
            </motion.li>
          );
        })}
      </ol>
      </div>
      )}
    </div>
  );
}

function Outcome({ s }: { s: Sequence }) {
  if (s.outcome === "goal") return <span className="rounded-md bg-white px-1.5 py-[2px] text-[10px] font-bold uppercase tracking-wider text-bg">Goal</span>;
  return <span className="rounded-md bg-white/8 px-1.5 py-[2px] text-[10px] font-semibold uppercase tracking-wider text-ink-2">{s.outcome === "shot" ? "Shot" : "Lost ball"}</span>;
}

function Thumb({ evs, team }: { evs: MatchEvent[]; team: "home" | "away" }) {
  const { L, W } = PITCH;
  const pts = evs.filter((e) => e.x != null && e.y != null);
  return (
    <svg viewBox={`-1.5 -1.5 ${L + 3} ${W + 3}`} className="h-[86px] w-[132px] shrink-0 overflow-hidden rounded-xl" aria-hidden>
      <PitchMarkings pad={1.5} texture={false} lineWidth={0.5} />
      <g stroke={`var(--${team})`} strokeLinecap="round" fill="none">
        {pts.map((e) => (
          <line key={e.id} x1={e.x!} y1={sy(e.y!)} x2={e.end_x!} y2={sy(e.end_y!)} strokeWidth={e.type === "carry" ? 0.7 : 1.1}
            strokeDasharray={e.type === "carry" ? "0.4 1.6" : undefined} />
        ))}
      </g>
      {pts.filter((e) => e.type.startsWith("shot")).map((e) => (
        <circle key={e.id} cx={e.x!} cy={sy(e.y!)} r={2.6} fill={e.result === "goal" ? "#fff" : `var(--${team})`} stroke={`var(--${team})`} strokeWidth={0.8} />
      ))}
      {pts[0] && <circle cx={pts[0].x!} cy={sy(pts[0].y!)} r={1.6} fill="#fff" />}
    </svg>
  );
}
