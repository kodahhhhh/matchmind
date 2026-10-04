import { useEffect, type CSSProperties, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import { AnimatePresence, motion } from "motion/react";
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

const TABS: [RightTab, string][] = [["analyst", "Analyst"], ["sequences", "Moments"], ["players", "Players"], ["whatif", "What if"]];

export function MatchView() {
  const { id = "" } = useParams();
  const { status, error, data, load, rightTab, setRightTab, focusTurningPoint, ask } = useMatch();

  useEffect(() => { void load(decodeURIComponent(id)); }, [id, load]);
  useMatchShortcuts();

  if (status === "error") return <Centered>Couldn't load this match. <span className="text-ink-4">{error}</span></Centered>;
  if (!data) return <MatchSkeleton />;

  const { match } = data;
  const vars = { "--home": match.teams.home.color, "--away": match.teams.away.color } as CSSProperties;
  const findTurningPoint = () => {
    const tp = data.turningPoints[0];
    if (tp) focusTurningPoint(tp.id);
    void ask("Find the turning point");
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto lg:min-h-[780px] lg:overflow-hidden" style={vars}>
      <header className="relative flex shrink-0 flex-wrap items-center justify-between gap-x-4 gap-y-3 px-4 py-3 lg:grid lg:h-[92px] lg:grid-cols-[1fr_auto_1fr] lg:px-6 lg:py-0">
        <div className="flex min-w-0 items-center gap-4">
          <Link to="/" className="rounded-xl p-1 transition hover:bg-white/5" aria-label="All matches"><Logo /></Link>
          <div className="hidden min-w-0 leading-tight xl:block">
            <div className="truncate text-[13px] font-semibold text-ink">{match.competition} {match.season}</div>
            <div className="truncate text-[11.5px] text-ink-3">{[match.stage, match.venue].filter(Boolean).join(" · ")}</div>
          </div>
        </div>
        <div className="order-3 flex w-full justify-center pt-1 lg:order-none lg:w-auto"><Scoreboard match={match} /></div>
        <div className="flex min-w-0 items-center justify-end gap-2">
          <div className="hidden lg:block"><KeyboardHelp /></div>
          <SearchButton compact />
          <button onClick={() => useMatch.getState().playHighlights()} title="Play highlights (H)"
            className="flex shrink-0 items-center gap-2 rounded-2xl bg-surface-2 px-3.5 py-2.5 text-sm font-semibold text-ink ring-1 ring-line transition hover:bg-surface-3">
            <svg width="12" height="14" viewBox="0 0 12 14"><path d="M1.5 1.5 10.5 7l-9 5.5z" fill="currentColor" /></svg>
            <span className="hidden sm:inline">Highlights</span>
          </button>
          <button onClick={findTurningPoint}
            className="ai-button flex shrink-0 items-center gap-2.5 rounded-2xl px-4 py-2.5 text-sm font-semibold text-white transition">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M1.5 12.5 6 8l3.2 3.2L16.5 4" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /><circle cx="9.2" cy="11.2" r="2" fill="#fff" /></svg>
            <span className="hidden sm:inline">Find the turning point</span>
            <span className="sm:hidden">Turning point</span>
          </button>
        </div>
      </header>

      <main className="flex flex-col gap-4 px-3 pb-4 lg:min-h-0 lg:flex-1 lg:flex-row lg:px-4">
        <section className="flex min-w-0 flex-1 flex-col gap-4">
          <motion.div initial={{ opacity: 0, scale: 0.99 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.5 }}
            className="relative aspect-[1.5] overflow-hidden rounded-[var(--radius)] shadow-[0_30px_80px_-40px_rgba(0,0,0,0.9)] ring-1 ring-white/10 lg:aspect-auto lg:min-h-0 lg:flex-1">
            <Pitch />
            <PitchOverlays />
          </motion.div>
          <div className="relative rounded-[var(--radius)] bg-surface-1 px-3 pb-2 pt-4 ring-1 ring-line lg:px-5">
            <Timeline />
          </div>
        </section>

        <aside className="flex h-[640px] w-full shrink-0 flex-col overflow-hidden rounded-[var(--radius)] bg-surface-1 ring-1 ring-line lg:h-auto lg:w-[440px]">
          <nav className="shrink-0 p-3">
            <div className="flex rounded-xl bg-surface-2 p-1">
              {TABS.map(([t, label]) => (
                <button key={t} onClick={() => setRightTab(t)}
                  className={`relative flex-1 rounded-lg py-2 text-[13px] font-medium transition ${rightTab === t ? "text-ink" : "text-ink-3 hover:text-ink-2"}`}>
                  {rightTab === t && <motion.span layoutId="tab" className="absolute inset-0 rounded-lg bg-surface-4 shadow" transition={{ type: "spring", bounce: 0.15, duration: 0.4 }} />}
                  <span className="relative flex items-center justify-center gap-1.5">
                    {t === "analyst" && <span className="h-1.5 w-1.5 rounded-full bg-ai" />}
                    {label}
                  </span>
                </button>
              ))}
            </div>
          </nav>
          <div className="relative min-h-0 flex-1">
            <AnimatePresence mode="wait" initial={false}>
              <motion.div key={rightTab} className="absolute inset-0"
                initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }} transition={{ duration: 0.18, ease: "easeOut" }}>
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
  );
}

function KeyboardHelp() {
  const keys: [string, string][] = [["← →", "Move the window 5 minutes"], ["Space", "Replay the selected move"], ["H", "Play / stop highlights"], ["T", "Jump to the turning point"], ["⌘K", "Search every moment"], ["Esc", "Back to the full match"]];
  return (
    <div className="group relative">
      <button aria-label="Keyboard shortcuts" className="flex h-[42px] w-[42px] items-center justify-center rounded-xl bg-surface-2 text-ink-3 ring-1 ring-line transition hover:text-ink">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><rect x="1.5" y="4" width="15" height="10" rx="2" stroke="currentColor" strokeWidth="1.3" /><path d="M4.5 7h1M8.5 7h1M12.5 7h1M5 10.5h8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" /></svg>
      </button>
      <div className="pointer-events-none absolute right-0 top-12 z-30 w-[260px] translate-y-1 rounded-2xl bg-surface-2 p-3 opacity-0 shadow-2xl ring-1 ring-white/10 transition group-hover:pointer-events-auto group-hover:translate-y-0 group-hover:opacity-100">
        <div className="eyebrow mb-2">Shortcuts</div>
        {keys.map(([k, l]) => (
          <div key={k} className="flex items-center justify-between py-1 text-[12.5px] text-ink-2">
            {l}<kbd className="rounded-md bg-surface-4 px-1.5 py-0.5 font-mono text-[11px] text-ink">{k}</kbd>
          </div>
        ))}
      </div>
    </div>
  );
}

function MatchSkeleton() {
  const block = "relative overflow-hidden rounded-[var(--radius)] bg-surface-1 ring-1 ring-line after:absolute after:inset-0 after:-translate-x-full after:animate-[sweep_1.4s_ease-in-out_infinite] after:bg-gradient-to-r after:from-transparent after:via-white/[0.04] after:to-transparent";
  return (
    <div className="flex h-full min-h-[780px] flex-col">
      <div className="grid h-[92px] grid-cols-[1fr_auto_1fr] items-center gap-4 px-6">
        <div className="h-9 w-40 rounded-xl bg-surface-2" />
        <div className="h-[52px] w-[560px] rounded-xl bg-surface-2" />
        <div className="ml-auto h-11 w-72 rounded-2xl bg-surface-2" />
      </div>
      <div className="flex min-h-0 flex-1 gap-4 px-4 pb-4">
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <div className={`${block} flex-1 !bg-[#143a26]/60`} />
          <div className={`${block} h-[218px]`} />
        </div>
        <div className={`${block} w-[440px]`} />
      </div>
    </div>
  );
}

function Centered({ children }: { children: ReactNode }) {
  return <div className="flex h-full items-center justify-center gap-2 text-sm text-ink-2">{children}</div>;
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
        st.reel ? st.stopHighlights() : st.playHighlights();
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

