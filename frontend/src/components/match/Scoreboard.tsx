import type { MatchDetail, Side } from "../../api/types";
import { clock } from "../../lib/format";
import { AnimatedNumber } from "../ui/AnimatedNumber";

/** Broadcast scorebug: team blocks, big score, scorers underneath. */
export function Scoreboard({ match }: { match: MatchDetail }) {
  const pens = match.score.penalties;
  const players = new Map([...match.lineups.home, ...match.lineups.away].map((p) => [p.player_id, p.short_name]));
  const scorers = (side: Side) => {
    const by = new Map<string, string[]>();
    for (const m of match.markers) {
      if (m.type !== "goal" || m.team !== side) continue;
      const name = m.detail === "own_goal" ? "OG" : players.get(m.player_id ?? -1) ?? "?";
      by.set(name, [...(by.get(name) ?? []), clock(m.period, m.minute) + (m.detail === "penalty" ? " P" : "")]);
    }
    return [...by.entries()].map(([n, ms]) => `${n} ${ms.join(", ")}`);
  };

  return (
    <div className="flex items-start gap-3">
      <TeamBlock side="home" name={match.teams.home.name} scorers={scorers("home")} />
      <div className="flex flex-col items-center">
        <div className="flex h-[52px] items-center overflow-hidden rounded-xl bg-surface-3 ring-1 ring-white/10">
          <span className="h-full w-1.5 bg-home" />
          <span className="display w-14 text-center text-[40px] leading-none text-ink"><AnimatedNumber value={match.score.home} from={0} ms={900} /></span>
          <span className="h-6 w-px bg-white/15" />
          <span className="display w-14 text-center text-[40px] leading-none text-ink"><AnimatedNumber value={match.score.away} from={0} ms={900} /></span>
          <span className="h-full w-1.5 bg-away" />
        </div>
        <div className="mt-1.5 text-[11px] font-medium text-ink-3">
          {pens ? <>{pens.home}–{pens.away} pens · <span className="text-ink-2">FT</span></> : "Full time"}
        </div>
      </div>
      <TeamBlock side="away" name={match.teams.away.name} scorers={scorers("away")} />
    </div>
  );
}

function TeamBlock({ side, name, scorers }: { side: Side; name: string; scorers: string[] }) {
  const right = side === "home";
  return (
    <div className={`flex w-[230px] flex-col ${right ? "items-end text-right" : "items-start text-left"}`}>
      <div className={`display flex h-[52px] items-center leading-none text-ink ${name.length <= 12 ? "text-[30px]" : name.length <= 17 ? "text-[24px]" : "text-[20px]"}`}>{name}</div>
      <div className="mt-1.5 line-clamp-1 text-[11.5px] text-ink-3">
        {scorers.length ? scorers.map((s, i) => (
          <span key={s}>{i > 0 && <span className="mx-1 text-ink-4">·</span>}{s}</span>
        )) : <span className="text-ink-4">No goals</span>}
      </div>
    </div>
  );
}
