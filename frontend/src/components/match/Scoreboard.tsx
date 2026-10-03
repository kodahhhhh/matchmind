import type { MatchDetail } from "../../api/types";

export function Scoreboard({ match }: { match: MatchDetail }) {
  const { home, away } = match.teams;
  const pens = match.score.penalties;
  return (
    <div className="flex items-center gap-4">
      <Team name={home.name} short={home.short} side="home" align="right" />
      <div className="flex flex-col items-center leading-none">
        <div className="flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-4 py-1.5 font-display text-[28px] font-semibold tracking-wide">
          <span>{match.score.home}</span>
          <span className="text-ink-4">–</span>
          <span>{match.score.away}</span>
        </div>
        {pens && (
          <span className="mt-1 text-[11px] text-ink-3">
            {pens.home}–{pens.away} on penalties
          </span>
        )}
      </div>
      <Team name={away.name} short={away.short} side="away" align="left" />
    </div>
  );
}

function Team({ name, short, side, align }: { name: string; short: string; side: "home" | "away"; align: "left" | "right" }) {
  return (
    <div className={`flex items-center gap-2.5 ${align === "right" ? "flex-row-reverse text-right" : ""}`}>
      <span className="h-7 w-1.5 rounded-full" style={{ background: `var(--${side})` }} />
      <div className="leading-tight">
        <div className="font-display text-xl font-semibold uppercase tracking-wide">{name}</div>
        <div className="text-[11px] uppercase tracking-[0.14em] text-ink-3">{side === "home" ? "Home" : "Away"} · {short}</div>
      </div>
    </div>
  );
}
