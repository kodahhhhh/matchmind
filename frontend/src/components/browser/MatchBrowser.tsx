import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { motion, MotionConfig, useInView } from "motion/react";
import { ArrowDown, ArrowRight, MagnifyingGlass } from "@phosphor-icons/react";
import { api } from "../../api/client";
import type { Backtest, Competition, MatchCard, MatchEvent, TimelineMinute, TurningPoint } from "../../api/types";
import { isShot } from "../../lib/format";
import { useUi } from "../../store/ui";
import { LearnChevron, Line, SpinningNumber, Stagger } from "../ui/motion";
import { SiteHeader } from "../ui/SiteHeader";
import { PageFooter } from "../ui/PageFooter";
import { FeaturedPitch } from "./FeaturedPitch";
import { MomentumPreview } from "./MomentumPreview";
import { MatchGrid } from "./MatchGrid";
import { PlayersSection } from "./PlayersSection";

const FEATURED = "sb:3869685";
const FEATURED_LABEL = "World Cup final, 2022";
const COMP_ORDER = ["FIFA World Cup", "UEFA Euro", "Copa America", "1. Bundesliga", "Major League Soccer"];
const EASE = [0.22, 1, 0.36, 1] as const;

interface Featured { shots: MatchEvent[]; move: MatchEvent[]; goals: MatchEvent[]; minutes: TimelineMinute[]; turning: TurningPoint | null }

export function MatchBrowser() {
  const [comps, setComps] = useState<Competition[]>([]);
  const [matches, setMatches] = useState<MatchCard[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [feat, setFeat] = useState<Featured | null>(null);
  const [backtest, setBacktest] = useState<Backtest | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  const load = useCallback(() => {
    Promise.all([api.competitions(), api.matches()]).then(([c, m]) => {
      setComps([...c].sort((a, b) => COMP_ORDER.indexOf(a.competition) - COMP_ORDER.indexOf(b.competition) || b.season.localeCompare(a.season)));
      setMatches(m);
      setStatus("ready");
    }).catch(() => setStatus("error"));
  }, []);

  useEffect(() => {
    load();
    Promise.all([api.events(FEATURED), api.timeline(FEATURED), api.turningPoints(FEATURED).catch(() => [])]).then(([ev, minutes, tps]) => {
      const inPlay = ev.filter((e) => e.period < 5);
      const goals = inPlay.filter((e) => e.result === "goal" && isShot(e.type));
      // loop the best team goal: the open-play goal whose move has the most passes
      const best = goals.filter((g) => g.type === "shot")
        .map((g) => ev.filter((e) => e.sequence_id === g.sequence_id && e.team === g.team && e.x != null))
        .sort((a, b) => b.filter((e) => e.type === "pass").length - a.filter((e) => e.type === "pass").length)[0];
      setFeat({
        shots: inPlay.filter((e) => isShot(e.type) && e.x != null),
        move: best ? best.slice(-9) : [],
        goals,
        minutes,
        turning: [...tps].sort((a, b) => a.rank - b.rank)[0] ?? null,
      });
    }).catch(() => {});
    api.backtest().then(setBacktest).catch(() => {});
  }, [load]);

  const featured = matches.find((m) => m.match_id === FEATURED);

  return (
    <MotionConfig reducedMotion="user">
      <div ref={scroller} className="scroll-thin h-full overflow-y-auto motion-safe:scroll-smooth">
        <a href="#matches" className="sr-only rounded-full bg-ink px-4 py-2 text-[13px] font-medium text-bg focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-30">
          Skip to matches
        </a>
        <SiteHeader scroller={scroller} />

        <main>
          <section className="mx-auto grid max-w-[1280px] grid-cols-1 items-center gap-12 px-5 pb-20 pt-8 md:px-8 lg:grid-cols-[minmax(0,1.12fr)_minmax(0,1fr)] lg:gap-12 lg:pb-24 lg:pt-14">
            <Stagger onMount>
              <Line n={1} as="h1" className="text-[38px] font-semibold leading-[1.06] tracking-[-0.04em] text-ink sm:text-[50px] lg:text-[42px] xl:text-[54px]">
                <span className="block">Stats say what happened.</span>
                <span className="block text-ink-3">We show why.</span>
              </Line>
              <Line n={2} as="p" className="mt-6 max-w-[42ch] text-pretty text-[17px] leading-[1.6] text-ink-2">
                Replay any match on a tactical pitch, find where it turned, and ask an analyst that cites every event.
              </Line>
              <Line n={3} as="div" className="mt-9">
                <div className="flex flex-wrap items-center gap-x-7 gap-y-4">
                <Link to={`/match/${encodeURIComponent(FEATURED)}`}
                  className="group inline-flex items-center gap-3 rounded-full bg-ink py-1.5 pl-5 pr-1.5 text-[14.5px] font-semibold text-bg transition-[transform,background-color] duration-150 ease-out hover:bg-ink-2 active:scale-[0.97]">
                  Open the World Cup final
                  <span className="grid size-8 place-items-center rounded-full bg-bg/10 transition-transform duration-200 ease-[var(--ease-smooth-out)] group-hover:translate-x-0.5">
                    <ArrowRight size={14} weight="bold" aria-hidden />
                  </span>
                </Link>
                <a href="#matches" className="group inline-flex items-center gap-2 text-[14.5px] font-medium text-ink-2 transition-colors duration-150 hover:text-ink">
                  Browse all matches
                  <ArrowDown size={14} weight="bold" className="transition-transform duration-200 ease-[var(--ease-smooth-out)] group-hover:translate-y-0.5" aria-hidden />
                </a>
                </div>
              </Line>
            </Stagger>
            {featured && feat
              ? <FeaturedPitch m={featured} shots={feat.shots} move={feat.move} label={FEATURED_LABEL} />
              : <div className="aspect-[111/88] rounded-[24px] bg-surface-1 ring-1 ring-line motion-safe:animate-pulse" aria-hidden />}
          </section>

          <Stats matches={matches.length || 493} />

          <section aria-labelledby="features-title" className="mx-auto max-w-[1280px] px-5 pt-28 md:px-8">
            <Stagger>
              <Line n={1} as="h2" className="max-w-[22ch] text-balance text-[30px] font-semibold leading-[1.1] tracking-[-0.03em] text-ink md:text-[38px]">
                <span id="features-title">Go deeper than the scoreline</span>
              </Line>
            </Stagger>
            <div className="mt-10 grid grid-cols-1 gap-3 md:grid-cols-3">
              <Cell className="md:col-span-2" i={0}>
                <CellText title="See where the match turned">
                  Momentum minute by minute in the 2022 final, with the swing our model ranks highest.
                </CellText>
                <div className="mt-8">
                  {featured && feat?.minutes.length
                    ? <MomentumPreview m={featured} minutes={feat.minutes} turning={feat.turning} goals={feat.goals} />
                    : <div className="h-[200px] rounded-xl bg-surface-2 motion-safe:animate-pulse" aria-hidden />}
                </div>
              </Cell>
              <SearchCell i={1} />
              <Cell i={2} className="flex flex-col">
                <CellText title="Ask why, get the receipts">
                  The analyst answers in plain words and links every claim to the events behind it. It never makes up a number.
                </CellText>
                <CellLink to={`/match/${encodeURIComponent(FEATURED)}`} ai>Ask about the final</CellLink>
              </Cell>
              <BacktestCell bt={backtest} i={3} />
            </div>
          </section>

          <PlayersSection />

          <MatchGrid comps={comps} matches={matches} status={status} onRetry={() => { setStatus("loading"); load(); }} />
        </main>

        <PageFooter className="" />
      </div>
    </MotionConfig>
  );
}

function InView({ children, i = 0, className }: { children: ReactNode; i?: number; className?: string }) {
  return (
    <motion.div className={className} initial={{ opacity: 0, y: 12, filter: "blur(3px)" }} whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      viewport={{ once: true, amount: 0.25 }} transition={{ duration: 0.5, delay: i * 0.06, ease: EASE }}>
      {children}
    </motion.div>
  );
}

function Stats({ matches }: { matches: number }) {
  const ref = useRef<HTMLDListElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.6 });
  const items: [number, string][] = [
    [matches, "Matches to replay"],
    [5962491, "Plays the models learned from"],
    [82580, "Lines of AI commentary"],
    [52151, "Player profiles"],
  ];
  return (
    <section aria-label="MatchPulse in numbers" className="mx-auto max-w-[1280px] px-5 md:px-8">
      <dl ref={ref} className="grid grid-cols-2 gap-x-6 gap-y-8 border-t border-line pt-6 md:grid-cols-4">
        {items.map(([n, label], i) => (
          <div key={label} className="flex flex-col-reverse justify-end gap-1">
            <dt className={`text-[14px] text-ink-3 transition-opacity duration-500 ease-out motion-reduce:transition-none ${inView ? "opacity-100" : "opacity-0"}`} style={{ transitionDelay: `${300 + i * 120}ms` }}>{label}</dt>
            <dd className="numeral text-[40px] leading-none text-ink md:text-[46px]">
              <SpinningNumber value={n} active={inView} delay={250 + i * 120} />
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Cell({ children, className = "", i }: { children: ReactNode; className?: string; i: number }) {
  return (
    <InView i={i} className={`rounded-[20px] bg-surface-1 p-6 ring-1 ring-line md:p-8 ${className}`}>
      {children}
    </InView>
  );
}

function CellText({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h3 className="text-[19px] font-semibold tracking-[-0.015em] text-ink">{title}</h3>
      <p className="mt-2 max-w-[52ch] text-pretty text-[15px] leading-[1.6] text-ink-3">{children}</p>
    </div>
  );
}

function CellLink({ to, children, ai }: { to: string; children: ReactNode; ai?: boolean }) {
  return (
    <Link to={to} className={`t-learn mt-auto inline-flex items-center gap-1 self-start pt-8 text-[14.5px] font-medium transition-colors duration-150 ${ai ? "text-ai hover:text-ink" : "text-ink hover:text-ink-2"}`}>
      {children}
      <LearnChevron />
    </Link>
  );
}

const SEARCH_EXAMPLES = ["Mbappé penalty", "header from a corner", "counter-attack goal"];

function SearchCell({ i }: { i: number }) {
  const open = (seed: string) => useUi.getState().setSearchOpen(true, seed);
  return (
    <Cell i={i} className="flex flex-col">
      <CellText title="Search every moment">
        Describe a moment in plain words and find it across 82,580 lines of match commentary.
      </CellText>
      <div className="mt-auto pt-8">
        <button type="button" onClick={() => open("")}
          className="flex w-full items-center gap-3 rounded-full bg-surface-2 py-2 pl-4 pr-2 text-left text-[14px] text-ink-3 ring-1 ring-line transition-[background-color,box-shadow,transform] duration-150 hover:bg-surface-3 hover:text-ink-2 hover:ring-line-strong active:scale-[0.98]">
          <MagnifyingGlass size={16} className="shrink-0" aria-hidden />
          <span className="flex-1 truncate">Search moments</span>
          <kbd className="shrink-0 rounded-md bg-surface-4 px-1.5 py-0.5 font-mono text-[11px] text-ink-2">⌘K</kbd>
        </button>
        <p className="mb-2 mt-5 text-[13px] text-ink-3">Try</p>
        <ul className="flex flex-wrap gap-2">
          {SEARCH_EXAMPLES.map((ex) => (
            <li key={ex}>
              <button type="button" onClick={() => open(ex)}
                className="rounded-full bg-surface-2 px-3 py-1.5 text-[13px] text-ink-2 transition-[background-color,color,transform] duration-150 hover:bg-surface-3 hover:text-ink active:scale-[0.97]">
                {ex}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </Cell>
  );
}

function BacktestCell({ bt, i }: { bt: Backtest | null; i: number }) {
  const s = bt?.strategies.find((x) => x.id === "pinnacle-closing-flat") ?? bt?.strategies.find((x) => x.market === "pinnacle");
  return (
    <Cell i={i} className="flex flex-col md:col-span-2">
      <div className="grid gap-8 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
        <CellText title="Would it beat the bookies?">
          We tested our match model against Pinnacle and Polymarket prices. Confidence intervals and every bet are on the page.
        </CellText>
        {s && (
          <dl className="flex gap-10">
            <div className="flex flex-col-reverse justify-end gap-1.5">
              <dt className="text-[13px] text-ink-3">Our model</dt>
              <dd className="numeral text-[40px] leading-none text-ink">{s.brier_model.toFixed(3)}</dd>
            </div>
            <div className="flex flex-col-reverse justify-end gap-1.5">
              <dt className="text-[13px] text-ink-3">Pinnacle</dt>
              <dd className="numeral text-[40px] leading-none text-ink-2">{s.brier_market.toFixed(3)}</dd>
            </div>
          </dl>
        )}
      </div>
      <div className="mt-auto flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <CellLink to="/backtest">See the market backtest</CellLink>
        {s && <p className="text-[13px] text-ink-3">Brier score on {s.n_matches} matches. Lower is better.</p>}
      </div>
    </Cell>
  );
}
