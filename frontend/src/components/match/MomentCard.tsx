import { useMemo } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowCounterClockwise, ChatCircleDots, GitFork, Play, X } from "@phosphor-icons/react";
import { undash } from "../../lib/format";
import { momentInfo } from "../../lib/story";
import { useMatch } from "../../store/match";

const EASE = [0.22, 1, 0.36, 1] as const;

/** The selected moment, in words, with the next steps: replay it, ask about it, or try a what-if.
 *  Overlays the bottom of the pitch on wide screens and sits under it on phones. */
export function MomentCard({ placement }: { placement: "overlay" | "below" }) {
  const data = useMatch((s) => s.data);
  const focus = useMatch((s) => s.focus);
  const replay = useMatch((s) => s.replay);
  const reel = useMatch((s) => s.reel);
  const commentaryBySeq = useMatch((s) => s.commentaryBySeq);
  const seq = replay?.sequenceId ?? (focus?.kind === "sequence" ? focus.id : undefined);
  const ev = !seq && focus?.kind === "event" ? focus.id : undefined;
  const info = useMemo(
    () => (data && (ev || seq) ? momentInfo(data, { ev, seq }, (id) => { const t = commentaryBySeq.get(id)?.text; return t ? undash(t) : undefined; }) : null),
    [data, ev, seq, commentaryBySeq],
  );
  const key = ev ?? seq ?? "none";
  const overlay = placement === "overlay";

  return (
    <AnimatePresence mode="wait" initial={false}>
      {info && (
        <motion.div key={key} role="region" aria-label="Selected moment" aria-live="polite"
          initial={{ opacity: 0, y: overlay ? 8 : -4 }} animate={{ opacity: 1, y: 0, transition: { duration: 0.22, ease: EASE } }}
          exit={{ opacity: 0, y: overlay ? 6 : -4, transition: { duration: 0.12, ease: EASE } }}
          className={overlay ? "pointer-events-none absolute inset-x-0 bottom-3 z-10 flex justify-center px-3 md:bottom-4 md:px-4" : ""}>
          <div className={`pointer-events-auto flex w-full items-stretch overflow-hidden rounded-2xl ${overlay ? "glass max-w-[760px]" : "bg-surface-1 ring-1 ring-line"}`}>
            <span className="w-1.5 shrink-0" style={{ background: `var(--${info.team})` }} aria-hidden />
            <div className="min-w-0 flex-1 py-3 pl-3.5 pr-2">
              <div className="flex items-start gap-3">
                <span className="numeral shrink-0 pt-px text-[20px] leading-none text-ink">{info.clock}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-pretty text-[14.5px] font-semibold leading-snug text-ink">
                    {info.title}
                    {info.chance != null && <span className="ml-2 whitespace-nowrap text-[13px] font-medium text-ink-2"><span className="tabular">{Math.round(info.chance * 100)}%</span> chance of scoring</span>}
                  </p>
                  {info.sub && <p className="mt-0.5 line-clamp-2 text-pretty text-[13px] leading-snug text-ink-2">{info.sub}</p>}
                </div>
                <button type="button" onClick={() => { const st = useMatch.getState(); st.stopHighlights(); }} aria-label="Close this moment"
                  className="-mr-0.5 -mt-1 grid size-8 shrink-0 place-items-center rounded-full text-ink-3 transition-[background-color,color,transform] duration-150 ease-out hover:bg-ink/10 hover:text-ink active:scale-[0.94]">
                  <X size={14} weight="bold" aria-hidden />
                </button>
              </div>
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {info.seq && !reel && data?.has.events && (
                  <Action onClick={() => useMatch.getState().startReplay(info.seq!)} icon={replay?.playing ? <ArrowCounterClockwise size={13} weight="bold" /> : <Play size={12} weight="fill" />}>
                    {replay?.playing ? "Replay again" : replay ? "Replay" : "Replay the move"}
                  </Action>
                )}
                <Action ai onClick={() => useMatch.getState().askAbout(info.question)} icon={<ChatCircleDots size={14} weight="fill" />}>Ask about this</Action>
                {info.whatIf && data?.has.events && (
                  <Action onClick={() => useMatch.getState().openWhatIf(info.whatIf!)} icon={<GitFork size={13} weight="bold" />}>{info.whatIfLabel}</Action>
                )}
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function Action({ children, icon, onClick, ai }: { children: React.ReactNode; icon: React.ReactNode; onClick: () => void; ai?: boolean }) {
  return (
    <button type="button" onClick={onClick}
      className={`flex h-8 items-center gap-1.5 rounded-full pl-2.5 pr-3 text-[12.5px] font-semibold transition-[background-color,color,transform] duration-150 ease-out active:scale-[0.97] ${ai ? "bg-ai-soft text-ai ring-1 ring-[var(--ai-line)] hover:bg-[var(--ai-line)] hover:text-ink" : "bg-ink/10 text-ink hover:bg-ink/15"}`}>
      <span aria-hidden className="grid place-items-center">{icon}</span>{children}
    </button>
  );
}
