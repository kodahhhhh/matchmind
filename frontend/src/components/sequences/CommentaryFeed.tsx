import { useEffect, useMemo, useRef } from "react";
import { bucketKey, useMatch } from "../../store/match";

/** Luna's line-by-line commentary for the current window; click a line to draw the move, ▶ to replay it. */
export function CommentaryFeed() {
  const data = useMatch((s) => s.data);
  const lines = useMatch((s) => s.commentary);
  const win = useMatch((s) => s.window);
  const focus = useMatch((s) => s.focus);
  const replay = useMatch((s) => s.replay);
  const focusSequence = useMatch((s) => s.focusSequence);
  const startReplay = useMatch((s) => s.startReplay);
  const activeRef = useRef<HTMLLIElement>(null);
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
    activeRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeId]);

  if (!data) return null;
  if (!lines.length) {
    return (
      <div className="px-5 py-10 text-center">
        <div className="shimmer text-[13px] font-medium">Commentary is being written</div>
        <p className="mt-1 text-[12px] text-ink-4">GPT-6 Luna writes a line for every move in every match.</p>
      </div>
    );
  }

  return (
    <div className="px-4 pb-4">
      <div className="flex items-center justify-between px-1 pb-2">
        <span className="text-[12px] text-ink-3">{win && !activeId ? `${shown.length} moves in this window` : `${lines.length} moves`}</span>
        <span className="flex items-center gap-1.5 text-[11px] text-ink-4"><span className="h-1.5 w-1.5 rounded-full bg-ai" />written by GPT-6 Luna from match events</span>
      </div>
      <ol className="relative space-y-0.5 before:absolute before:bottom-2 before:left-[52px] before:top-2 before:w-px before:bg-line">
        {shown.map((l) => {
          const active = l.sequence_id === activeId;
          const big = l.outcome === "goal";
          return (
            <li key={l.sequence_id} ref={active ? activeRef : undefined}>
              <div role="button" tabIndex={0} onClick={() => focusSequence(l.sequence_id)} onKeyDown={(e) => e.key === "Enter" && focusSequence(l.sequence_id)}
                className={`group relative flex cursor-pointer gap-3 rounded-xl py-2 pl-1 pr-2 transition ${active ? "bg-surface-3" : "hover:bg-surface-2"}`}>
                <span className={`display w-10 shrink-0 text-right text-[15px] leading-6 ${big ? "text-ink" : "text-ink-3"}`}>{l.start.label}</span>
                <span className="relative z-10 mt-[7px] h-2.5 w-2.5 shrink-0 rounded-full ring-4 ring-surface-1" style={{ background: `var(--${l.team})` }} />
                <span className={`min-w-0 flex-1 text-[13.5px] leading-6 ${big ? "font-semibold text-ink" : l.outcome === "shot" ? "text-ink" : "text-ink-2"}`}>
                  {big && <span className="mr-1.5 rounded bg-white px-1 py-[1px] align-[1px] text-[9.5px] font-bold uppercase tracking-wider text-bg">Goal</span>}
                  {l.text}
                </span>
                <button onClick={(e) => { e.stopPropagation(); startReplay(l.sequence_id); }} aria-label="Replay"
                  className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-ink-3 opacity-0 transition hover:bg-white/10 hover:text-ink group-hover:opacity-100">
                  <svg width="8" height="10" viewBox="0 0 10 12"><path d="M1.5 1.2 9 6l-7.5 4.8z" fill="currentColor" /></svg>
                </button>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
