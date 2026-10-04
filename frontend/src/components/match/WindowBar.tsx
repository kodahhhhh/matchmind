import { useMemo } from "react";
import { Explain } from "@/components/ui/explain";
import type { GlossaryKey } from "../../lib/glossary";
import type { Side } from "../../api/types";
import { useMatch } from "../../store/match";
import { pct, undash, xg } from "../../lib/format";
import { usePitchEvents } from "../pitch/Pitch";
import { AnimatePresence, motion } from "motion/react";
import { SkipForward, X } from "@phosphor-icons/react";
import { AnimatedNumber } from "../ui/AnimatedNumber";
import { resolveSequence } from "../../store/match";

const EASE = [0.22, 1, 0.36, 1] as const;

/** Glass overlays on the pitch: what's shown (top left), window stats and legend (bottom), highlights reel and captions. */
export function PitchOverlays() {
  const data = useMatch((s) => s.data);
  const win = useMatch((s) => s.window);
  const focus = useMatch((s) => s.focus);
  const setWindow = useMatch((s) => s.setWindow);
  const setFocus = useMatch((s) => s.setFocus);
  const stopReplay = useMatch((s) => s.stopReplay);
  const focusTurningPoint = useMatch((s) => s.focusTurningPoint);
  const { mode, events, seq } = usePitchEvents();
  const caption = useMatch((st) => (seq ? st.commentaryBySeq.get(seq.id) : undefined));
  const reel = useMatch((st) => st.reel);
  const replay = useMatch((st) => st.replay);
  const nextHighlight = useMatch((st) => st.nextHighlight);
  const stopHighlights = useMatch((st) => st.stopHighlights);

  const stats = useMemo(() => {
    if (!data) return null;
    const rows = win ? data.timeline.slice(win.from, win.to + 1) : data.timeline;
    const sum = (s: Side, k: "shots" | "xg") => rows.reduce((a, m) => a + m[s][k], 0);
    const avg = (s: Side, k: "possession" | "field_tilt") => rows.reduce((a, m) => a + m[s][k], 0) / Math.max(rows.length, 1);
    return {
      range: win ? [rows[0]?.label ?? "", rows[rows.length - 1]?.label ?? ""] as const : null,
      rows: [
        { label: "Possession", term: "possession", a: avg("home", "possession"), b: avg("away", "possession"), fmt: (v: number) => pct(v), share: true },
        { label: "Territory", term: "territory", a: avg("home", "field_tilt"), b: avg("away", "field_tilt"), fmt: (v: number) => pct(v), share: true },
        { label: "Chances", term: "chances", a: sum("home", "xg"), b: sum("away", "xg"), fmt: xg, share: false },
        { label: "Shots", term: "shots", a: sum("home", "shots"), b: sum("away", "shots"), fmt: (v: number) => String(v), share: false },
      ],
    };
  }, [data, win]);
  if (!data || !stats) return null;
  const turning = focus?.kind === "turning";
  const { home, away } = data.match.teams;
  const what = mode === "sequence"
    ? `${seq ? data.match.teams[seq.team].name : ""} move from ${seq?.start.label ?? ""}`
    : mode === "detail" ? `${events.length} actions` : "Shot map";
  const reset = () => { setWindow(null); setFocus(null); stopReplay(); };

  const reelItem = reel ? reel.items[reel.index] : null;
  const reelSeqLen = reelItem ? resolveSequence(data, reelItem.sequenceId)?.event_ids.length ?? 1 : 1;
  const reelProgress = replay && reelItem && replay.sequenceId === reelItem.sequenceId ? (replay.playing ? (replay.step + 1) / reelSeqLen : 1) : 0;
  const pillBtn = "rounded-full transition-[transform,background-color,color] duration-150 ease-out active:scale-[0.97]";

  return (
    <>
      <AnimatePresence>
        {reel && reelItem && (
          <motion.div key="reel" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0, transition: { duration: 0.25, ease: EASE } }}
            exit={{ opacity: 0, y: -8, transition: { duration: 0.15, ease: EASE } }}
            className="absolute left-1/2 top-3 z-10 w-[min(560px,calc(100%-1.5rem))] -translate-x-1/2 md:top-4">
            <div className="glass overflow-hidden rounded-2xl">
              <div className="flex items-center gap-3 pb-2 pl-3 pr-2 pt-2">
                <span className="flex shrink-0 items-center gap-1.5 rounded-full bg-ink py-0.5 pl-2 pr-2.5 text-[12px] font-semibold text-bg">
                  <span className="size-1.5 rounded-full bg-bg motion-safe:animate-pulse" aria-hidden />Highlights
                </span>
                <AnimatePresence mode="wait" initial={false}>
                  <motion.span key={reelItem.sequenceId} initial={{ opacity: 0, x: 6 }} animate={{ opacity: 1, x: 0, transition: { duration: 0.2, ease: EASE } }}
                    exit={{ opacity: 0, x: -6, transition: { duration: 0.12, ease: EASE } }}
                    className="flex min-w-0 flex-1 items-center gap-2 text-[13.5px] font-semibold text-ink">
                    <span className="size-2 shrink-0 rounded-full" style={{ background: `var(--${reelItem.team})` }} aria-hidden />
                    <span className="truncate">{reelItem.label}</span>
                    {reelItem.kind === "goal" && <span className="shrink-0 rounded-full bg-ink/15 px-2 text-[11.5px] font-semibold text-ink">Goal</span>}
                  </motion.span>
                </AnimatePresence>
                <span className="tabular shrink-0 text-[12px] text-ink-3">{reel.index + 1} of {reel.items.length}</span>
                <span className="flex shrink-0 items-center">
                  <button onClick={nextHighlight} aria-label="Next highlight"
                    className={`grid size-8 place-items-center text-ink-2 hover:bg-ink/10 hover:text-ink ${pillBtn}`}>
                    <SkipForward size={15} weight="fill" aria-hidden />
                  </button>
                  <button onClick={stopHighlights} aria-label="Stop highlights"
                    className={`grid size-8 place-items-center text-ink-2 hover:bg-ink/10 hover:text-ink ${pillBtn}`}>
                    <X size={15} weight="bold" aria-hidden />
                  </button>
                </span>
              </div>
              <div className="flex gap-[3px] px-3.5 pb-2.5" aria-hidden>
                {reel.items.map((it, i) => (
                  <div key={it.sequenceId} className="h-[3px] flex-1 overflow-hidden rounded-full bg-ink/15">
                    <div className="h-full rounded-full transition-[width] duration-500 ease-out motion-reduce:transition-none"
                      style={{ width: `${i < reel.index ? 100 : i === reel.index ? reelProgress * 100 : 0}%`, background: `var(--${it.team})` }} />
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className={`pointer-events-none absolute left-3 top-3 flex flex-wrap items-center gap-2 transition-opacity duration-200 md:left-4 md:top-4 ${reel ? "opacity-0" : ""}`}>
        <div className="glass pointer-events-auto flex h-10 items-center gap-3 rounded-full pl-3.5 pr-1 md:h-11 md:pl-4 md:pr-1.5">
          <span className="flex items-baseline gap-2 whitespace-nowrap">
            {turning && <span className="text-[13.5px] font-semibold tracking-[-0.01em] text-ai">Turning point</span>}
            {stats.range
              ? <span className="text-ink"><span className="numeral text-[19px] leading-none">{stats.range[0]}</span><span className="mx-1.5 text-[13px] text-ink-3">to</span><span className="numeral text-[19px] leading-none">{stats.range[1]}</span></span>
              : <span className="text-[14px] font-semibold tracking-[-0.01em] text-ink">Full match</span>}
          </span>
          <span className="hidden h-5 w-px bg-line-strong sm:block" aria-hidden />
          <span className="hidden whitespace-nowrap text-[12.5px] text-ink-2 sm:inline">{what}</span>
          {(win || focus) ? (
            <button onClick={reset} className={`h-8 whitespace-nowrap bg-ink/10 px-3 text-[12.5px] font-medium text-ink hover:bg-ink/15 ${pillBtn}`}>
              Show full match
            </button>
          ) : <span className="w-1.5" />}
        </div>
        {turning && data.turningPoints.length > 1 && (
          <div className="glass pointer-events-auto flex h-11 items-center gap-1 rounded-full py-1 pl-4 pr-1.5" role="group" aria-label="Turning points">
            <span className="pr-1.5 text-[12.5px] text-ink-3">Shifts</span>
            {data.turningPoints.map((tp) => {
              const on = focus?.kind === "turning" && focus.id === tp.id;
              return (
                <button key={tp.id} onClick={() => focusTurningPoint(tp.id)} aria-pressed={on}
                  className={`flex h-8 items-center gap-1.5 px-3 text-[12.5px] font-semibold tabular ${pillBtn} ${on ? "bg-ai text-bg" : "text-ink-2 hover:bg-ink/10 hover:text-ink"}`}>
                  <span className="size-2 rounded-full" style={{ background: `var(--${tp.team_gaining})` }} aria-hidden />
                  {tp.start.label}
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className={`glass pointer-events-none absolute bottom-4 right-4 hidden items-center gap-4 rounded-2xl px-4 py-2.5 transition-opacity duration-200 md:flex ${mode === "sequence" ? "opacity-0" : ""}`}>
        <div className="flex max-w-[104px] flex-col gap-1.5 text-[12px] font-semibold text-ink">
          <span className="flex min-w-0 items-center gap-1.5" title={home.name}><span className="size-2 shrink-0 rounded-full bg-home" aria-hidden /><span className="truncate">{home.name}</span></span>
          <span className="flex min-w-0 items-center gap-1.5" title={away.name}><span className="size-2 shrink-0 rounded-full bg-away" aria-hidden /><span className="truncate">{away.name}</span></span>
        </div>
        {stats.rows.map((r) => {
          const total = r.share ? 1 : r.a + r.b || 1;
          return (
            <div key={r.label} className="w-[78px]">
              <div className="mb-1 text-[11px] text-ink-3"><Explain term={r.term as GlossaryKey}>{r.label}</Explain></div>
              <div className="flex items-baseline justify-between text-[12.5px] font-semibold tabular text-ink">
                <span><AnimatedNumber value={r.a} format={r.fmt} /></span><span className="text-ink-2"><AnimatedNumber value={r.b} format={r.fmt} /></span>
              </div>
              <div className="mt-1 flex h-[4px] gap-[2px]">
                <div className="rounded-full transition-[width] duration-500 ease-[var(--ease-smooth-out)] motion-reduce:transition-none" style={{ width: `${(r.a / total) * 100}%`, background: "var(--home)" }} />
                <div className="flex-1 rounded-full transition-opacity duration-500" style={{ background: "var(--away)", opacity: r.b === 0 && !r.share ? 0.15 : 1 }} />
              </div>
            </div>
          );
        })}
      </div>

      {mode === "sequence" && caption && (
        <div className="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center px-3 md:bottom-4 md:px-4">
          <div className="glass flex max-w-[720px] items-stretch overflow-hidden rounded-2xl">
            <span className="w-1.5 shrink-0" style={{ background: `var(--${caption.team})` }} aria-hidden />
            <div className="flex items-start gap-3 py-2.5 pl-3.5 pr-4">
              <span className="numeral pt-px text-[20px] leading-none text-ink">{caption.start.label}</span>
              <div className="min-w-0">
                <p className="text-pretty text-[14.5px] font-medium leading-snug text-ink">{undash(caption.text)}</p>
                <p className="mt-0.5 text-[12px] text-ink-3">{data.match.teams[caption.team].name}, <span className="text-ai">commentary by Luna</span></p>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className={`glass pointer-events-none absolute bottom-4 left-4 hidden items-center gap-3 rounded-full px-3.5 py-2 text-[12px] text-ink-2 md:flex ${mode === "sequence" && caption ? "md:hidden" : ""}`}>
        <span className="flex items-center gap-1.5"><svg width="12" height="12" aria-hidden><circle cx="6" cy="6" r="4.5" fill="var(--ink)" fillOpacity={0.25} stroke="var(--ink)" strokeWidth="1" /></svg>Shot, bigger means a better chance</span>
        <span className="flex items-center gap-1.5"><svg width="12" height="12" aria-hidden><circle cx="6" cy="6" r="5" fill="var(--ink)" /><circle cx="6" cy="6" r="1.8" fill="var(--grass-2)" /></svg>Goal</span>
        {mode !== "overview" && <span className="flex items-center gap-1.5"><svg width="18" height="8" aria-hidden><line x1="1" y1="4" x2="17" y2="4" stroke="var(--ink)" strokeWidth="1.5" /></svg>Pass</span>}
        {mode !== "overview" && <span className="flex items-center gap-1.5"><svg width="18" height="8" aria-hidden><line x1="1" y1="4" x2="17" y2="4" stroke="var(--ink)" strokeWidth="1.5" strokeDasharray="1 3" strokeLinecap="round" /></svg>Carry</span>}
      </div>
    </>
  );
}
