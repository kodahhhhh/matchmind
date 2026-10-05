import { lazy, Suspense, useEffect, useRef, type CSSProperties, type KeyboardEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { AnimatePresence, MotionConfig, motion, useReducedMotion } from "motion/react";
import { ArrowLeft, Keyboard } from "@phosphor-icons/react";
import { useMatch, type RightTab } from "../../store/match";
import { usePlayerUi, useUi } from "../../store/ui";
import { Pitch } from "../pitch/Pitch";
import { Timeline } from "../timeline/Timeline";
import { StoryPanel } from "../story/StoryPanel";
import { Players } from "../players/Players";
import { WhatIf } from "../whatif/WhatIf";
import { Scoreboard } from "./Scoreboard";
import { PitchOverlays } from "./WindowBar";
import { MomentCard } from "./MomentCard";
import { Logo } from "../ui/Logo";
import { SearchButton } from "../search/SearchPalette";
import { MobileMenu } from "../ui/SiteHeader";

// the analyst pulls in markdown and code highlighting: load it only when it's first opened
const AnalystPanel = lazy(() => import("../analyst/AnalystPanel").then((m) => ({ default: m.AnalystPanel })));

const EASE = [0.22, 1, 0.36, 1] as const;

export function MatchView() {
  const { id = "" } = useParams();
  const { status, error, data, load, rightTab, setRightTab } = useMatch();
  const pitchRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const pitchPing = useMatch((s) => s.pitchPing);
  const panelPing = useMatch((s) => s.panelPing);
  const reduce = useReducedMotion();

  // deep links can open a panel straight away: /match/<id>?tab=ask
  const [params] = useSearchParams();
  const wantTab = params.get("tab");
  useEffect(() => {
    void load(decodeURIComponent(id)).then(() => {
      if (wantTab === "ask" || wantTab === "players" || wantTab === "whatif" || wantTab === "story") useMatch.getState().setRightTab(wantTab);
    });
  }, [id, load, wantTab]);
  useMatchShortcuts();

  // On phones the pitch and the panel are stacked: bring whichever the user just asked for into view.
  useEffect(() => {
    const el = pitchRef.current;
    if (!pitchPing || !el) return;
    const r = el.getBoundingClientRect();
    if (r.top < 0 || r.bottom > window.innerHeight) el.scrollIntoView({ block: "start", behavior: reduce ? "auto" : "smooth" });
  }, [pitchPing, reduce]);
  useEffect(() => {
    const el = panelRef.current;
    if (!panelPing || !el) return;
    const r = el.getBoundingClientRect();
    if (r.top > window.innerHeight * 0.5 || r.bottom < 80) el.scrollIntoView({ block: "start", behavior: reduce ? "auto" : "smooth" });
  }, [panelPing, reduce]);

  if (status === "error") return <LoadError error={error} />;
  if (!data) return <MatchSkeleton />;

  const { match, has } = data;
  const vars = { "--home": match.teams.home.color, "--away": match.teams.away.color } as CSSProperties;
  const tabs: [RightTab, string][] = [["story", "Story"], ["ask", "Ask"], ["players", "Players"], ...(has.events ? [["whatif", "What if"] as [RightTab, string]] : [])];
  const tab = tabs.some(([t]) => t === rightTab) ? rightTab : "story";
  const onTabKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const i = tabs.findIndex(([t]) => t === tab);
    const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length][0];
    setRightTab(next);
    requestAnimationFrame(() => document.getElementById(`tab-${next}`)?.focus());
  };
  const meta = [match.stage && match.stage !== "Regular Season" ? match.stage : null, match.venue].filter(Boolean).join(" · ");

  return (
    <MotionConfig reducedMotion="user">
    <div className="scroll-thin flex h-full flex-col overflow-y-auto lg:min-h-[780px] lg:overflow-hidden" style={vars}>
      <h1 className="sr-only">{match.teams.home.name} {match.score.home}-{match.score.away} {match.teams.away.name}, {match.competition} {match.season}</h1>
      <header className="relative shrink-0 px-3 pb-2 pt-3 lg:grid lg:h-[92px] lg:grid-cols-[1fr_auto_1fr] lg:items-center lg:px-6 lg:py-0">
        <div className="flex items-center justify-between gap-3 lg:justify-start lg:gap-4">
          <div className="flex min-w-0 items-center gap-2 lg:gap-3">
            <Link to="/" aria-label="All matches"
              className="grid size-10 shrink-0 place-items-center rounded-full bg-surface-2 text-ink-2 ring-1 ring-line transition-[background-color,color,transform] duration-150 ease-out hover:bg-surface-3 hover:text-ink active:scale-[0.97]">
              <ArrowLeft size={16} weight="bold" aria-hidden />
            </Link>
            <Link to="/" aria-label="MatchPulse home" className="hidden rounded-xl p-1 transition-colors duration-150 hover:bg-surface-2 sm:block"><Logo size={30} /></Link>
            <div className="min-w-0 leading-tight lg:hidden xl:block">
              <p className="truncate text-[13.5px] font-semibold tracking-[-0.01em] text-ink">{match.competition} {match.season}</p>
              {meta && <p className="mt-0.5 truncate text-[12px] text-ink-3">{meta}</p>}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2 lg:hidden">
            <SearchButton compact className="h-10 rounded-full" />
            <MobileMenu className="" />
          </div>
        </div>
        <div className="mt-3 flex justify-center lg:mt-0"><Scoreboard match={match} /></div>
        <div className="hidden items-center justify-end gap-2 lg:flex">
          <div className="hidden xl:block"><KeyboardHelp /></div>
          <SearchButton className="h-10 rounded-full" />
        </div>
      </header>

      <main className="flex flex-col gap-3 px-3 pb-4 lg:min-h-0 lg:flex-1 lg:flex-row lg:gap-4 lg:px-4">
        <section aria-label="Pitch and timeline" className="flex min-w-0 flex-1 flex-col gap-3 lg:gap-4">
          <motion.div ref={pitchRef} initial={{ opacity: 0, scale: 0.99 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.5, ease: EASE }}
            className="relative aspect-[1.5] scroll-mt-3 overflow-hidden rounded-[20px] shadow-[0_30px_80px_-40px_rgba(0,0,0,0.9)] ring-1 ring-line-strong lg:aspect-auto lg:min-h-0 lg:flex-1">
            <Pitch />
            {(has.events || has.shots) && <PitchOverlays />}
            <div className="hidden md:block"><MomentCard placement="overlay" /></div>
          </motion.div>
          <div className="md:hidden"><MomentCard placement="below" /></div>
          {has.timeline && (
            <div className="relative rounded-[20px] bg-surface-1 px-3 pb-2 pt-4 ring-1 ring-line lg:px-5">
              <Timeline />
            </div>
          )}
        </section>

        <aside ref={panelRef} aria-label="Match story and tools" className="flex w-full shrink-0 scroll-mt-3 flex-col rounded-[20px] bg-surface-1 ring-1 ring-line lg:h-auto lg:w-[440px] lg:overflow-hidden">
          <div role="tablist" aria-label="Match panels" onKeyDown={onTabKey} className="sticky top-0 z-10 shrink-0 rounded-t-[20px] bg-surface-1 p-3">
            <div className="flex rounded-full bg-surface-2 p-1 ring-1 ring-line">
              {tabs.map(([t, label]) => (
                <button key={t} id={`tab-${t}`} role="tab" aria-selected={tab === t} aria-controls="match-panel" tabIndex={tab === t ? 0 : -1}
                  onClick={() => setRightTab(t)}
                  className={`relative h-9 flex-1 rounded-full text-[13.5px] font-medium transition-colors duration-150 ${tab === t ? "text-ink" : "text-ink-3 hover:text-ink-2"}`}>
                  {tab === t && <motion.span layoutId="match-tab" className="absolute inset-0 rounded-full bg-surface-4 shadow-[0_1px_2px_rgba(0,0,0,0.4)]" transition={{ duration: 0.25, ease: EASE }} />}
                  <span className={`relative ${t === "ask" && tab !== t ? "text-ai" : ""}`}>{label}</span>
                </button>
              ))}
            </div>
          </div>
          <div id="match-panel" role="tabpanel" aria-labelledby={`tab-${tab}`} className="relative lg:min-h-0 lg:flex-1">
            <AnimatePresence mode="wait" initial={false}>
              <motion.div key={tab} className={tab === "ask" ? "h-[calc(100dvh-88px)] lg:absolute lg:inset-0 lg:h-auto" : "lg:absolute lg:inset-0"}
                initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0, transition: { duration: 0.2, ease: EASE } }}
                exit={{ opacity: 0, x: -8, transition: { duration: 0.12, ease: EASE } }}>
                {tab === "story" && <StoryPanel />}
                {tab === "ask" && <Suspense fallback={<PanelSkeleton />}><AnalystPanel /></Suspense>}
                {tab === "players" && <Players />}
                {tab === "whatif" && <WhatIf />}
              </motion.div>
            </AnimatePresence>
          </div>
        </aside>
      </main>
    </div>
    </MotionConfig>
  );
}

function PanelSkeleton() {
  return (
    <div className="space-y-3 px-5 pt-2" aria-busy="true" aria-label="Loading">
      <div className="h-5 w-40 rounded-full bg-surface-2 motion-safe:animate-pulse" />
      <div className="h-24 rounded-2xl bg-surface-2 motion-safe:animate-pulse" />
      <div className="h-24 rounded-2xl bg-surface-2 motion-safe:animate-pulse" />
    </div>
  );
}

const SHORTCUTS: [string, string][] = [
  ["← →", "Move through the match"],
  ["Space", "Replay the selected attack"],
  ["H", "Play or stop the highlights"],
  ["T", "Jump to where it turned"],
  ["/", "Search"],
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
      <div className="flex shrink-0 flex-col gap-3 px-3 pb-2 pt-3 lg:grid lg:h-[92px] lg:grid-cols-[1fr_auto_1fr] lg:items-center lg:px-6 lg:py-0">
        <div className="h-10 w-40 rounded-full bg-surface-2 motion-safe:animate-pulse" />
        <div className="mx-auto h-[52px] w-full max-w-[560px] rounded-2xl bg-surface-2 motion-safe:animate-pulse lg:w-[560px]" />
        <div className="hidden h-10 w-32 justify-self-end rounded-full bg-surface-2 motion-safe:animate-pulse lg:block" />
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
  const notFound = error?.startsWith("404");
  return (
    <div role="alert" className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
      <div>
        <h1 className="text-[17px] font-semibold tracking-[-0.015em] text-ink">{notFound ? "We don't have this match" : "Couldn't load this match"}</h1>
        <p className="mt-1 max-w-[42ch] text-pretty text-[14px] text-ink-3">{notFound ? "The link may be out of date. Search for the match, or pick one from the list." : "Check your connection and try again."}</p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {notFound && (
          <button type="button" onClick={() => useUi.getState().setSearchOpen(true)}
            className="inline-flex h-10 items-center rounded-full bg-ink px-4 text-[13.5px] font-semibold text-bg transition-[transform,background-color] duration-150 ease-out hover:bg-ink-2 active:scale-[0.97]">
            Search for a match
          </button>
        )}
        {!notFound && (
          <button type="button" onClick={() => { const st = useMatch.getState(); if (st.matchId) void st.load(st.matchId); }}
            className="inline-flex h-10 items-center rounded-full bg-ink px-4 text-[13.5px] font-semibold text-bg transition-[transform,background-color] duration-150 ease-out hover:bg-ink-2 active:scale-[0.97]">
            Try again
          </button>
        )}
        <Link to="/" className="inline-flex h-10 items-center gap-2 rounded-full bg-surface-2 px-4 text-[13.5px] font-medium text-ink ring-1 ring-line transition-[transform,background-color] duration-150 ease-out hover:bg-surface-3 active:scale-[0.97]">
          <ArrowLeft size={14} weight="bold" aria-hidden />
          All matches
        </Link>
      </div>
    </div>
  );
}

/** ←/→ move the window, Space replays the focused move, H highlights, T turning point, Esc resets. */
function useMatchShortcuts() {
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable)) return;
      if (el?.getAttribute("role") === "tab") return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (useUi.getState().searchOpen || usePlayerUi.getState().playerId != null) return;
      const st = useMatch.getState();
      const d = st.data;
      if (!d) return;
      const n = d.timeline.length;
      if ((e.key === "ArrowRight" || e.key === "ArrowLeft") && n) {
        e.preventDefault();
        const w = st.window ?? { from: 0, to: 9 };
        const span = w.to - w.from;
        const dir = e.key === "ArrowRight" ? 5 : -5;
        const from = Math.max(0, Math.min(n - 1 - span, (st.window ? w.from : -5) + dir));
        st.setFocus(null);
        st.setWindow({ from, to: from + span });
      } else if (e.key === " " && el?.tagName !== "BUTTON" && el?.tagName !== "A") {
        e.preventDefault();
        const seq = st.replay?.sequenceId ?? (st.focus?.kind === "sequence" ? st.focus.id : null)
          ?? (st.focus?.kind === "event" ? d.eventById.get(st.focus.id)?.sequence_id : null) ?? d.sequences[0]?.id;
        if (seq) st.startReplay(seq);
      } else if (e.key.toLowerCase() === "h") {
        if (st.reel) st.stopHighlights();
        else st.playHighlights();
      } else if (e.key.toLowerCase() === "t") {
        const tp = [...d.turningPoints].sort((a, b) => a.rank - b.rank)[0];
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
