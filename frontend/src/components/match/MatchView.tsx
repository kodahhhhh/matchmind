import { useEffect, type CSSProperties } from "react";
import { Link, useParams } from "react-router";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { ArrowLeft, ChartLineUp, Keyboard, Play } from "@phosphor-icons/react";
import { useMatch, type RightTab } from "../../store/match";
import { usePlayerUi, useUi } from "../../store/ui";
import { Pitch } from "../pitch/Pitch";
import { Timeline } from "../timeline/Timeline";
import { AnalystPanel } from "../analyst/AnalystPanel";
import { Sequences } from "../sequences/Sequences";
import { Players } from "../players/Players";
import { WhatIf } from "../whatif/WhatIf";
import { Scoreboard } from "./Scoreboard";
import { PitchOverlays } from "./WindowBar";
import { Logo } from "../ui/Logo";
import { SearchButton } from "../search/SearchPalette";

const EASE = [0.22, 1, 0.36, 1] as const;
const TABS: [RightTab, string][] = [["analyst", "Analyst"], ["sequences", "Moments"], ["players", "Players"], ["whatif", "What if"]];

export function MatchView() {
  const { id = "" } = useParams();
  const { status, error, data, load, rightTab, setRightTab, focusTurningPoint, ask } = useMatch();

  useEffect(() => { void load(decodeURIComponent(id)); }, [id, load]);
  useMatchShortcuts();

  if (status === "error") return <LoadError error={error} />;
  if (!data) return <MatchSkeleton />;

  const { match } = data;
  const vars = { "--home": match.teams.home.color, "--away": match.teams.away.color } as CSSProperties;
  const findTurningPoint = () => {
    const tp = data.turningPoints[0];
    if (tp) focusTurningPoint(tp.id);
    void ask("Find the turning point");
  };

  return (
    <MotionConfig reducedMotion="user">
    <div className="flex h-full flex-col overflow-y-auto lg:min-h-[780px] lg:overflow-hidden" style={vars}>
      <h1 className="sr-only">{match.teams.home.name} {match.score.home}-{match.score.away} {match.teams.away.name}, {match.competition} {match.season}</h1>
      <header className="relative flex shrink-0 flex-wrap items-center justify-between gap-x-4 gap-y-3 px-4 py-3 lg:grid lg:h-[92px] lg:grid-cols-[1fr_auto_1fr] lg:px-6 lg:py-0">
        <div className="flex min-w-0 items-center gap-4">
          <Link to="/" className="rounded-xl p-1 transition-colors duration-150 hover:bg-surface-2" aria-label="All matches"><Logo /></Link>
          <div className="hidden min-w-0 leading-tight xl:block">
            <p className="truncate text-[13.5px] font-semibold tracking-[-0.01em] text-ink">{match.competition} {match.season}</p>
            <p className="mt-0.5 truncate text-[12px] text-ink-3">{[match.stage, match.venue].filter(Boolean).join(" · ")}</p>
          </div>
        </div>
        <div className="order-3 flex w-full justify-center pt-1 lg:order-none lg:w-auto"><Scoreboard match={match} /></div>
        <div className="flex min-w-0 items-center justify-end gap-2">
          <div className="hidden xl:block"><KeyboardHelp /></div>
          <SearchButton compact className="h-10 rounded-full" />
          <button onClick={() => useMatch.getState().playHighlights()} title="Play highlights (H)" aria-label="Play highlights"
            className="flex h-10 shrink-0 items-center gap-2 rounded-full bg-surface-2 px-3.5 text-[13.5px] font-semibold text-ink ring-1 ring-line transition-[transform,background-color] duration-150 ease-out hover:bg-surface-3 active:scale-[0.97] sm:pr-4 lg:max-[1399px]:pr-3.5">
            <Play size={14} weight="fill" aria-hidden />
            <span className="hidden sm:inline lg:max-[1399px]:hidden">Play highlights</span>
          </button>
          <button onClick={findTurningPoint}
            className="ai-button flex h-10 shrink-0 items-center gap-2 rounded-full pl-3.5 pr-4 text-[13.5px] font-semibold text-white">
            <ChartLineUp size={16} weight="bold" aria-hidden />
            Find the turning point
          </button>
        </div>
      </header>

      <main className="flex flex-col gap-3 px-3 pb-4 lg:min-h-0 lg:flex-1 lg:flex-row lg:gap-4 lg:px-4">
        <section aria-label="Pitch and timeline" className="flex min-w-0 flex-1 flex-col gap-3 lg:gap-4">
          <motion.div initial={{ opacity: 0, scale: 0.99 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.5, ease: EASE }}
            className="relative aspect-[1.5] overflow-hidden rounded-[20px] shadow-[0_30px_80px_-40px_rgba(0,0,0,0.9)] ring-1 ring-line-strong lg:aspect-auto lg:min-h-0 lg:flex-1">
            <Pitch />
            <PitchOverlays />
          </motion.div>
          <div className="relative rounded-[20px] bg-surface-1 px-3 pb-2 pt-4 ring-1 ring-line lg:px-5">
            <Timeline />
          </div>
        </section>

        <aside aria-label="Match tools" className="flex h-[max(680px,calc(100dvh-1.5rem))] w-full shrink-0 flex-col overflow-hidden rounded-[20px] bg-surface-1 ring-1 ring-line lg:h-auto lg:w-[440px]">
          <nav aria-label="Panel" className="shrink-0 p-3">
            <div className="flex rounded-full bg-surface-2 p-1 ring-1 ring-line">
              {TABS.map(([t, label]) => (
                <button key={t} onClick={() => setRightTab(t)} aria-pressed={rightTab === t}
                  className={`relative h-9 flex-1 rounded-full text-[13.5px] font-medium transition-colors duration-150 ${rightTab === t ? "text-ink" : "text-ink-3 hover:text-ink-2"}`}>
                  {rightTab === t && <motion.span layoutId="match-tab" className="absolute inset-0 rounded-full bg-surface-4 shadow-[0_1px_2px_rgba(0,0,0,0.4)]" transition={{ duration: 0.25, ease: EASE }} />}
                  <span className="relative">{label}</span>
                </button>
              ))}
            </div>
          </nav>
          <div className="relative min-h-0 flex-1">
            <AnimatePresence mode="wait" initial={false}>
              <motion.div key={rightTab} className="absolute inset-0"
                initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0, transition: { duration: 0.2, ease: EASE } }}
                exit={{ opacity: 0, x: -8, transition: { duration: 0.12, ease: EASE } }}>
                {rightTab === "analyst" && <AnalystPanel />}
                {rightTab === "sequences" && <Sequences />}
                {rightTab === "players" && <Players />}
                {rightTab === "whatif" && <WhatIf />}
              </motion.div>
            </AnimatePresence>
          </div>
        </aside>
      </main>
    </div>
    </MotionConfig>
  );
}

const SHORTCUTS: [string, string][] = [
  ["← →", "Move the window 5 minutes"],
  ["Space", "Replay the selected move"],
  ["H", "Play or stop highlights"],
  ["T", "Jump to the turning point"],
  ["⌘K", "Search every moment"],
  ["Esc", "Back to the full match"],
];

/** Shortcut sheet: opens on hover or keyboard focus, fades in fast and out faster. */
function KeyboardHelp() {
  return (
    <div className="group relative">
      <button aria-label="Keyboard shortcuts" aria-describedby="match-shortcuts"
        className="grid size-10 place-items-center rounded-full bg-surface-2 text-ink-3 ring-1 ring-line transition-[transform,color,background-color] duration-150 ease-out hover:bg-surface-3 hover:text-ink active:scale-[0.97]">
        <Keyboard size={18} aria-hidden />
      </button>
      <div id="match-shortcuts" role="tooltip"
        className="pointer-events-none absolute right-0 top-12 z-30 w-[272px] origin-top-right scale-[0.97] rounded-2xl bg-surface-2 p-3.5 opacity-0 shadow-2xl ring-1 ring-line-strong transition-[opacity,scale] duration-[50ms] ease-out group-hover:pointer-events-auto group-hover:scale-100 group-hover:opacity-100 group-hover:duration-150 group-focus-within:scale-100 group-focus-within:opacity-100 group-focus-within:duration-150 motion-reduce:scale-100">
        <h2 className="mb-2 text-[13.5px] font-semibold tracking-[-0.01em] text-ink">Keyboard shortcuts</h2>
        <dl>
          {SHORTCUTS.map(([k, l]) => (
            <div key={k} className="flex items-center justify-between gap-3 py-1 text-[12.5px] text-ink-2">
              <dt>{l}</dt>
              <dd><kbd className="rounded-md bg-surface-4 px-1.5 py-0.5 font-mono text-[11px] text-ink">{k}</kbd></dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}

function MatchSkeleton() {
  const block = "rounded-[20px] bg-surface-1 ring-1 ring-line motion-safe:animate-pulse";
  return (
    <div className="flex h-full flex-col overflow-hidden lg:min-h-[780px]" aria-busy="true" aria-label="Loading match">
      <div className="flex h-[92px] shrink-0 items-center justify-between gap-4 px-4 lg:grid lg:grid-cols-[1fr_auto_1fr] lg:px-6">
        <div className="h-9 w-40 rounded-xl bg-surface-2 motion-safe:animate-pulse" />
        <div className="hidden h-[52px] w-[560px] rounded-2xl bg-surface-2 motion-safe:animate-pulse lg:block" />
        <div className="ml-auto h-10 w-40 rounded-full bg-surface-2 motion-safe:animate-pulse lg:w-80" />
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-3 px-3 pb-4 lg:flex-row lg:gap-4 lg:px-4">
        <div className="flex min-w-0 flex-col gap-3 lg:flex-1 lg:gap-4">
          <div className="aspect-[1.5] rounded-[20px] bg-[var(--grass-2)] opacity-60 ring-1 ring-line motion-safe:animate-pulse lg:aspect-auto lg:flex-1" />
          <div className={`${block} h-[218px] shrink-0`} />
        </div>
        <div className={`${block} hidden lg:block lg:w-[440px]`} />
      </div>
    </div>
  );
}

function LoadError({ error }: { error: string | null }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
      <div>
        <h1 className="text-[17px] font-semibold tracking-[-0.015em] text-ink">Couldn't load this match</h1>
        {error && <p className="mt-1 text-[13px] text-ink-3">{error}</p>}
      </div>
      <Link to="/" className="inline-flex h-10 items-center gap-2 rounded-full bg-surface-2 px-4 text-[13.5px] font-medium text-ink ring-1 ring-line transition-[transform,background-color] duration-150 ease-out hover:bg-surface-3 active:scale-[0.97]">
        <ArrowLeft size={14} weight="bold" aria-hidden />
        Back to all matches
      </Link>
    </div>
  );
}

/** ←/→ move the window, Space replays the focused move, H highlights, T turning point, Esc resets. */
function useMatchShortcuts() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (useUi.getState().searchOpen || usePlayerUi.getState().playerId != null) return;
      const st = useMatch.getState();
      const d = st.data;
      if (!d) return;
      const n = d.timeline.length;
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        const w = st.window ?? { from: 0, to: 9 };
        const span = w.to - w.from;
        const dir = e.key === "ArrowRight" ? 5 : -5;
        const from = Math.max(0, Math.min(n - 1 - span, (st.window ? w.from : -5) + dir));
        st.setFocus(null);
        st.setWindow({ from, to: from + span });
      } else if (e.key === " ") {
        e.preventDefault();
        const seq = st.replay?.sequenceId ?? (st.focus?.kind === "sequence" ? st.focus.id : null) ?? d.sequences[0]?.id;
        if (seq) st.startReplay(seq);
      } else if (e.key.toLowerCase() === "h") {
        if (st.reel) st.stopHighlights();
        else st.playHighlights();
      } else if (e.key.toLowerCase() === "t") {
        const tp = d.turningPoints[0];
        if (tp) st.focusTurningPoint(tp.id);
      } else if (e.key === "Escape") {
        st.stopHighlights();
        st.setFocus(null);
        st.setWindow(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

