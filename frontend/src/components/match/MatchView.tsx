import { useEffect, type CSSProperties, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import { motion } from "motion/react";
import { useMatch, type RightTab } from "../../store/match";
import { Pitch } from "../pitch/Pitch";
import { Timeline } from "../timeline/Timeline";
import { AnalystPanel } from "../analyst/AnalystPanel";
import { Sequences } from "../sequences/Sequences";
import { Players } from "../players/Players";
import { WhatIf } from "../whatif/WhatIf";
import { Scoreboard } from "./Scoreboard";
import { PitchOverlays } from "./WindowBar";
import { Logo } from "../ui/Logo";

const TABS: [RightTab, string][] = [["analyst", "Analyst"], ["sequences", "Moments"], ["players", "Players"], ["whatif", "What if"]];

export function MatchView() {
  const { id = "" } = useParams();
  const { status, error, data, load, rightTab, setRightTab, focusTurningPoint, ask } = useMatch();

  useEffect(() => { void load(decodeURIComponent(id)); }, [id, load]);

  if (status === "error") return <Centered>Couldn't load this match. <span className="text-ink-4">{error}</span></Centered>;
  if (!data) return <Centered><span className="shimmer text-sm font-medium">Loading match</span></Centered>;

  const { match } = data;
  const vars = { "--home": match.teams.home.color, "--away": match.teams.away.color } as CSSProperties;
  const findTurningPoint = () => {
    const tp = data.turningPoints[0];
    if (tp) focusTurningPoint(tp.id);
    void ask("Find the turning point");
  };

  return (
    <div className="flex h-full min-h-[780px] flex-col" style={vars}>
      <header className="relative flex h-[92px] shrink-0 items-center px-6">
        <div className="flex w-[300px] items-center gap-4">
          <Link to="/" className="rounded-xl p-1 transition hover:bg-white/5" aria-label="All matches"><Logo /></Link>
          <div className="min-w-0 leading-tight">
            <div className="truncate text-[13px] font-semibold text-ink">{match.competition} {match.season}</div>
            <div className="truncate text-[11.5px] text-ink-3">{[match.stage, match.venue].filter(Boolean).join(" · ")}</div>
          </div>
        </div>
        <div className="flex flex-1 justify-center pt-1"><Scoreboard match={match} /></div>
        <div className="flex w-[300px] justify-end">
          <button onClick={findTurningPoint}
            className="ai-button flex items-center gap-2.5 rounded-2xl px-5 py-3 text-sm font-semibold text-white transition">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M1.5 12.5 6 8l3.2 3.2L16.5 4" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /><circle cx="9.2" cy="11.2" r="2" fill="#fff" /></svg>
            Find the turning point
          </button>
        </div>
      </header>

      <main className="flex min-h-0 flex-1 gap-4 px-4 pb-4">
        <section className="flex min-w-0 flex-1 flex-col gap-4">
          <motion.div initial={{ opacity: 0, scale: 0.99 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.5 }}
            className="relative min-h-0 flex-1 overflow-hidden rounded-[var(--radius)] shadow-[0_30px_80px_-40px_rgba(0,0,0,0.9)] ring-1 ring-white/10">
            <Pitch />
            <PitchOverlays />
          </motion.div>
          <div className="rounded-[var(--radius)] bg-surface-1 px-5 pb-2 pt-4 ring-1 ring-line">
            <Timeline />
          </div>
        </section>

        <aside className="flex w-[440px] shrink-0 flex-col overflow-hidden rounded-[var(--radius)] bg-surface-1 ring-1 ring-line">
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
          <div className="min-h-0 flex-1">
            {rightTab === "analyst" && <AnalystPanel />}
            {rightTab === "sequences" && <Sequences />}
            {rightTab === "players" && <Players />}
            {rightTab === "whatif" && <WhatIf />}
          </div>
        </aside>
      </main>
    </div>
  );
}

function Centered({ children }: { children: ReactNode }) {
  return <div className="flex h-full items-center justify-center gap-2 text-sm text-ink-2">{children}</div>;
}
