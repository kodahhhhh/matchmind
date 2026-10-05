import { useReducedMotion } from "motion/react";
import type { MatchDetail, Side } from "../../api/types";
import { clock } from "../../lib/format";
import { AnimatedNumber } from "../ui/AnimatedNumber";

interface Scorer { name: string; minutes: string }

/** Broadcast scorebug: team names, big score, scorers underneath. */
export function Scoreboard({ match }: { match: MatchDetail }) {
  const reduce = useReducedMotion();
  const pens = match.score.penalties;
  const players = new Map([...match.lineups.home, ...match.lineups.away].map((p) => [p.player_id, p.short_name]));
  const scorers = (side: Side): Scorer[] => {
    const by = new Map<string, string[]>();
    for (const m of match.markers) {
      if (m.type !== "goal" || m.team !== side) continue;
      const name = m.detail === "own_goal" ? "Own goal" : players.get(m.player_id ?? -1) ?? "Unknown";
      by.set(name, [...(by.get(name) ?? []), clock(m.period, m.minute) + (m.detail === "penalty" ? " (pen)" : "")]);
    }
    return [...by.entries()].map(([name, ms]) => ({ name, minutes: ms.join(", ") }));
  };
  const extraTime = match.periods.some((p) => p.period >= 3);
  const status = pens ? `${pens.home}-${pens.away} on penalties` : extraTime ? "After extra time" : "Full time";

  return (
    <div className="flex w-full items-start justify-center gap-3 lg:w-auto lg:gap-4">
      <TeamBlock side="home" name={match.teams.home.name} scorers={scorers("home")} />
      <div className="flex shrink-0 flex-col items-center">
        <div className="flex h-[52px] items-center overflow-hidden rounded-2xl bg-surface-3 ring-1 ring-line-strong"
          aria-label={`${match.score.home}-${match.score.away}`} role="img">
          <span className="h-full w-1.5 bg-home" />
          <span className="numeral w-14 text-center text-[40px] leading-none text-ink">
            <AnimatedNumber value={match.score.home} from={reduce ? undefined : 0} ms={900} />
          </span>
          <span className="h-6 w-px bg-line-strong" />
          <span className="numeral w-14 text-center text-[40px] leading-none text-ink">
            <AnimatedNumber value={match.score.away} from={reduce ? undefined : 0} ms={900} />
          </span>
          <span className="h-full w-1.5 bg-away" />
        </div>
        <p className="tabular mt-1.5 whitespace-nowrap text-[12px] font-medium text-ink-3">{status}</p>
      </div>
      <TeamBlock side="away" name={match.teams.away.name} scorers={scorers("away")} />
    </div>
  );
}

function TeamBlock({ side, name, scorers }: { side: Side; name: string; scorers: Scorer[] }) {
  const right = side === "home";
  const size = name.length <= 12 ? "text-[18px] lg:text-[26px]" : name.length <= 17 ? "text-[15px] lg:text-[21px]" : "text-[13px] lg:text-[18px]";
  const all = scorers.map((s) => `${s.name} ${s.minutes}`).join(", ");
  return (
    <div className={`flex min-w-0 flex-1 flex-col lg:w-[230px] lg:flex-none lg:max-[1399px]:w-[176px] ${right ? "items-end text-right" : "items-start text-left"}`}>
      <p title={name} className={`flex h-[52px] max-w-full items-center font-semibold leading-none tracking-[-0.03em] text-ink ${size}`}>
        <span className="truncate">{name}</span>
      </p>
      <p title={all || undefined} className="tabular mt-1.5 hidden max-w-full truncate text-[11px] text-ink-3 sm:block lg:text-[12px]">
        {scorers.length ? scorers.map((s, i) => (
          <span key={s.name} className={i > 0 ? "ml-2.5" : undefined}>
            <span className="text-ink-2">{s.name}</span> {s.minutes}
          </span>
        )) : <span className="text-ink-4">No goals</span>}
      </p>
    </div>
  );
}
