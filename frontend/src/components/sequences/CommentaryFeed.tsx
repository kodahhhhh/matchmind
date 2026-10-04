import { useEffect, useMemo, useRef } from "react";
import { useReducedMotion } from "motion/react";
import { Play, Sparkle } from "@phosphor-icons/react";
import { bucketKey, useMatch } from "../../store/match";
import { undash } from "../../lib/format";

/** Luna's line-by-line commentary for the current window; select a line to draw the move, or play it back. */
export function CommentaryFeed() {
  const data = useMatch((s) => s.data);
  const lines = useMatch((s) => s.commentary);
  const win = useMatch((s) => s.window);
  const focus = useMatch((s) => s.focus);
  const replay = useMatch((s) => s.replay);
  const focusSequence = useMatch((s) => s.focusSequence);
  const startReplay = useMatch((s) => s.startReplay);
  const activeRef = useRef<HTMLLIElement>(null);
  const reduce = useReducedMotion();
  const activeId = replay?.sequenceId ?? (focus?.kind === "sequence" ? focus.id : null);

  const shown = useMemo(() => {
    if (!data) return [];
    if (!win || activeId) return lines;
    return lines.filter((l) => {
      const i = data.bucketOf.get(bucketKey(l.start.period, l.start.minute)) ?? -1;
      return i >= win.from && i <= win.to;
    });
  }, [data, lines, win, activeId]);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
  }, [activeId, reduce]);

  if (!data) return null;
  if (!lines.length) {
    return (
      <div className="px-5 py-12 text-center" role="status">
        <p className="shimmer text-[14px] font-medium">Writing the commentary</p>
        <p className="mt-1.5 text-pretty text-[13px] text-ink-3">GPT-6 Luna writes a line for every move in every match.</p>
      </div>
    );
  }

  return (
    <div className="px-4 pb-4">
      <div className="flex items-center justify-between gap-3 px-1 pb-2">
        <span className="tabular text-[12.5px] text-ink-3">{win && !activeId ? `${shown.length} moves in this window` : `${lines.length} moves`}</span>
        <span className="flex items-center gap-1.5 text-[12px] text-ink-3">
          <Sparkle size={12} weight="fill" className="text-ai" aria-hidden />Written by GPT-6 Luna from match events
        </span>
      </div>
      <ol className="relative space-y-0.5 before:absolute before:bottom-2 before:left-[52px] before:top-2 before:w-px before:bg-line">
        {shown.map((l) => {
          const active = l.sequence_id === activeId;
          const big = l.outcome === "goal";
          return (
            <li key={l.sequence_id} ref={active ? activeRef : undefined} className="group relative">
              <button type="button" onClick={() => focusSequence(l.sequence_id)} aria-current={active || undefined}
                className={`relative flex w-full gap-3 rounded-xl py-2 pl-1 pr-9 text-left transition-colors duration-150 ${active ? "bg-surface-3" : "hover:bg-surface-2"}`}>
                <span className={`numeral w-10 shrink-0 text-right text-[15px] leading-6 ${big ? "text-ink" : "text-ink-3"}`}>{l.start.label}</span>
                <span className="relative z-10 mt-[7px] size-2.5 shrink-0 rounded-full ring-4 ring-surface-1" style={{ background: `var(--${l.team})` }} aria-hidden />
                <span className={`min-w-0 flex-1 text-pretty text-[13.5px] leading-6 ${big ? "font-semibold text-ink" : l.outcome === "shot" ? "text-ink" : "text-ink-2"}`}>
                  {big && <span className="mr-1.5 inline-block rounded-full bg-ink px-1.5 align-[1px] text-[11.5px] font-semibold leading-[18px] text-bg">Goal</span>}
                  {undash(l.text)}
                </span>
              </button>
              <button type="button" onClick={() => startReplay(l.sequence_id)} aria-label={`Play the ${l.start.label} move`}
                className={`absolute right-1.5 top-2 flex size-6 items-center justify-center rounded-full text-ink-3 ${active ? "opacity-100" : "opacity-0"} transition-[opacity,background-color,color,transform] duration-150 ease-out hover:bg-surface-4 hover:text-ink focus-visible:opacity-100 active:scale-[0.94] group-hover:opacity-100 [@media(hover:none)]:opacity-100`}>
                <Play size={10} weight="fill" aria-hidden />
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
