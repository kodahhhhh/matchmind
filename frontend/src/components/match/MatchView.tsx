import { useEffect, type CSSProperties } from "react";
import { Link, useParams } from "react-router";
import { useMatch, type RightTab } from "../../store/match";
import { Pitch } from "../pitch/Pitch";
import { Timeline } from "../timeline/Timeline";
import { AnalystPanel } from "../analyst/AnalystPanel";
import { Sequences } from "../sequences/Sequences";
import { Players } from "../players/Players";
import { WhatIf } from "../whatif/WhatIf";
import { Scoreboard } from "./Scoreboard";
import { WindowBar } from "./WindowBar";
import { Logo } from "../ui/Logo";

const TABS: [RightTab, string][] = [["analyst", "Analyst"], ["sequences", "Sequences"], ["players", "Players"], ["whatif", "What if"]];

export function MatchView() {
  const { id = "" } = useParams();
  const { status, error, data, load, rightTab, setRightTab, focusTurningPoint, ask } = useMatch();

  useEffect(() => { void load(decodeURIComponent(id)); }, [id, load]);

  if (status === "error") return <Centered>Couldn't load this match. <span className="text-ink-4">{error}</span></Centered>;
  if (!data) return <Centered><span className="animate-pulse text-ink-3">Loading match…</span></Centered>;

  const { match } = data;
  const vars = { "--home": match.teams.home.color, "--away": match.teams.away.color } as CSSProperties;
  const findTurningPoint = () => {
    const tp = data.turningPoints[0];
    if (tp) focusTurningPoint(tp.id);
    void ask("Find the turning point");
  };

  return (
    <div className="flex h-full min-h-[760px] flex-col" style={vars}>
      <header className="flex h-[68px] shrink-0 items-center gap-6 border-b border-line px-5">
        <Link to="/" className="flex items-center gap-2.5"><Logo /></Link>
        <div className="hidden min-w-0 text-xs leading-tight text-ink-3 lg:block">
          <div className="truncate text-ink-2">{match.competition} {match.season}</div>
          <div className="truncate">{[match.stage, match.venue, match.match_date].filter(Boolean).join(" · ")}</div>
        </div>
        <div className="flex flex-1 justify-center"><Scoreboard match={match} /></div>
        <button onClick={findTurningPoint}
          className="group relative flex items-center gap-2 overflow-hidden rounded-xl border border-[var(--ai-line)] bg-ai-soft px-4 py-2 text-sm font-semibold text-ink transition hover:shadow-[0_0_24px_rgba(184,166,255,0.25)]">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M1 11 5 7l3 3 6-7" stroke="var(--ai)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /><circle cx="8" cy="10" r="1.6" fill="var(--ai)" /></svg>
          Find the turning point
        </button>
      </header>

      <main className="flex min-h-0 flex-1">
        <section className="flex min-w-0 flex-1 flex-col gap-3 px-5 py-4">
          <div className="relative min-h-0 flex-1 rounded-[var(--radius)] border border-line bg-surface-1/60 p-2">
            <Pitch />
          </div>
          <div className="rounded-[var(--radius)] border border-line bg-surface-1/60 px-4 pb-2 pt-3">
            <WindowBar />
            <div className="mt-2"><Timeline /></div>
          </div>
        </section>

        <aside className="flex w-[440px] shrink-0 flex-col border-l border-line bg-surface-1/50 xl:w-[480px]">
          <nav className="flex h-12 shrink-0 items-end gap-1 border-b border-line px-4">
            {TABS.map(([t, label]) => (
              <button key={t} onClick={() => setRightTab(t)}
                className={`relative px-3 pb-3 text-sm transition ${rightTab === t ? "text-ink" : "text-ink-3 hover:text-ink-2"}`}>
                {t === "analyst" && <span className="mr-1.5 inline-block h-1.5 w-1.5 -translate-y-[1px] rounded-full bg-ai" />}
                {label}
                {rightTab === t && <span className="absolute inset-x-2 -bottom-px h-[2px] rounded-full bg-ink" />}
              </button>
            ))}
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

function Centered({ children }: { children: React.ReactNode }) {
  return <div className="flex h-full items-center justify-center gap-2 text-sm text-ink-2">{children}</div>;
}
