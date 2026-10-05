import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { motion, MotionConfig, useInView } from "motion/react";
import { ArrowRight, ChatCircleDots, GitFork, MagnifyingGlass, Sparkle } from "@phosphor-icons/react";
import { api } from "../../api/client";
import type { Backtest, MatchCard, MatchDetail, TimelineMinute, TurningPoint } from "../../api/types";
import { useUi } from "../../store/ui";
import { useCatalogue } from "../../store/catalogue";
import { FAMOUS, compLabel, matchDate, matchPath } from "../../lib/matchSearch";
import { bookiesAnswer } from "../../lib/plain";
import { LearnChevron, Line, SpinningNumber, Stagger } from "../ui/motion";
import { SiteHeader } from "../ui/SiteHeader";
import { PageFooter } from "../ui/PageFooter";
import { MomentumPreview } from "./MomentumPreview";
import { MatchGrid } from "./MatchGrid";
import { PlayersSection } from "./PlayersSection";

const FEATURED = "sb:3869685";
const EASE = [0.22, 1, 0.36, 1] as const;

interface Featured { match: MatchDetail; minutes: TimelineMinute[]; turning: TurningPoint | null }

/** Home: find a match first (search, famous, latest, browse), then what MatchPulse can do. */
export function MatchBrowser() {
  const { matches, status, load } = useCatalogue();
  const scroller = useRef<HTMLDivElement>(null);
  const location = useLocation();

  useEffect(() => { void load(); }, [load]);

  // deep links from search ("/?comp=La Liga#matches") land on the browser
  useEffect(() => {
    if (location.hash !== "#matches") return;
    const t = setTimeout(() => document.getElementById("matches")?.scrollIntoView({ block: "start" }), 50);
    return () => clearTimeout(t);
  }, [location.key, location.hash]);

  const byId = useCatalogue((s) => s.byId);
  const famous = FAMOUS.map((f) => ({ ...f, m: byId.get(f.id) })).filter((f): f is typeof f & { m: MatchCard } => !!f.m);
  const latest = useMemo(() => [...matches].filter((m) => m.match_date).sort((a, b) => b.match_date!.localeCompare(a.match_date!)).slice(0, 8), [matches]);

  return (
    <MotionConfig reducedMotion="user">
      <div ref={scroller} className="scroll-thin h-full overflow-y-auto">
        <a href="#matches" className="sr-only rounded-full bg-ink px-4 py-2 text-[13px] font-medium text-bg focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-30">
          Skip to all matches
        </a>
        <SiteHeader scroller={scroller} />

        <main>
          <section className="mx-auto grid max-w-[1280px] grid-cols-1 items-center gap-10 px-4 pb-14 pt-6 sm:px-5 md:px-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-12 lg:pb-16 lg:pt-12">
            <Stagger onMount>
              <Line n={1} as="h1" className="text-balance text-[36px] font-semibold leading-[1.05] tracking-[-0.04em] text-ink sm:text-[48px] xl:text-[56px]">
                Every match, explained.
              </Line>
              <Line n={2} as="p" className="mt-4 max-w-[44ch] text-pretty text-[16px] leading-[1.6] text-ink-2 sm:mt-5 sm:text-[17px]">
                Replay the big moments, see who was on top and ask why. In plain words, with every claim linked to the moment on the pitch.
              </Line>
              <Line n={3} as="div" className="mt-7 sm:mt-8">
                <HeroSearch />
              </Line>
            </Stagger>
            <div className="hidden lg:block"><FeaturedMatch /></div>
          </section>

          <Rail id="famous" title="Famous matches" intro="Finals and comebacks people still talk about.">
            {status !== "ready" ? <CardSkeletons n={4} /> : famous.map((f, i) => <MatchTile key={f.id} m={f.m} hook={f.hook} i={i} />)}
          </Rail>

          <div className="px-4 pb-12 sm:px-5 md:px-8 lg:hidden"><FeaturedMatch /></div>

          <Rail id="latest" title="Latest matches" intro="The newest matches in the archive.">
            {status !== "ready" ? <CardSkeletons n={4} /> : latest.map((m, i) => <MatchTile key={m.match_id} m={m} i={i} />)}
          </Rail>

          <MatchGrid />

          <Showcase />
          <PlayersSection />
          <BookiesTeaser />
          <Stats matches={matches.length || 2924} />
        </main>

        <PageFooter />
      </div>
    </MotionConfig>
  );
}

/** The hero's search field: a real-looking input that opens the full search, carrying any typed key with it. */
function HeroSearch() {
  const open = (seed = "") => useUi.getState().setSearchOpen(true, seed);
  const chips = ["Liverpool", "Spain v England", "Messi", "header from a corner"];
  return (
    <div>
      <button type="button" onClick={() => open()} aria-label="Search matches, players and moments"
        onKeyDown={(e) => { if (e.key.length === 1 && !e.metaKey && !e.ctrlKey) { e.preventDefault(); open(e.key); } }}
        className="group flex h-14 w-full max-w-[520px] items-center gap-3 rounded-2xl bg-surface-1 pl-4 pr-2 text-left ring-1 ring-line-strong transition-[background-color,box-shadow,transform] duration-150 ease-out hover:bg-surface-2 hover:ring-ink-4 active:scale-[0.99]">
        <MagnifyingGlass size={20} className="shrink-0 text-ink-2" aria-hidden />
        <span className="min-w-0 flex-1 truncate text-[16px] text-ink-3">Search a team, a player or a moment</span>
        <span className="hidden shrink-0 rounded-xl bg-ink px-3.5 py-2 text-[13.5px] font-semibold text-bg sm:block">Search</span>
      </button>
      <ul className="mt-3 flex flex-wrap gap-2" aria-label="Example searches">
        {chips.map((c) => (
          <li key={c}>
            <button type="button" onClick={() => open(c)}
              className="rounded-full bg-surface-1 px-3 py-1.5 text-[13px] text-ink-2 ring-1 ring-line transition-[background-color,color,transform] duration-150 ease-out hover:bg-surface-2 hover:text-ink active:scale-[0.97]">
              {c}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Hero visual: the 2022 final's story as one momentum chart, linking into the match. Light: no event stream. */
let featuredReq: Promise<Featured> | null = null;
const loadFeatured = () => (featuredReq ??= Promise.all([api.match(FEATURED), api.timeline(FEATURED), api.turningPoints(FEATURED).catch(() => [])])
  .then(([match, minutes, tps]) => ({ match, minutes, turning: [...tps].sort((a, b) => a.rank - b.rank)[0] ?? null })));

function FeaturedMatch() {
  const [feat, setFeat] = useState<Featured | null>(null);
  useEffect(() => {
    let live = true;
    loadFeatured().then((f) => live && setFeat(f)).catch(() => { featuredReq = null; });
    return () => { live = false; };
  }, []);
  if (!feat) return <div className="h-[340px] rounded-[24px] bg-surface-1 ring-1 ring-line motion-safe:animate-pulse sm:h-[372px]" aria-hidden />;
  const { match: m } = feat;
  const card: MatchCard = {
    match_id: m.match_id, competition_key: "", competition: m.competition, season: m.season, stage: m.stage, match_date: m.match_date,
    reconstructed: m.reconstructed, home: m.teams.home, away: m.teams.away, home_score: m.score.home, away_score: m.score.away, has_detail: true,
  };
  const goals = m.markers.filter((k) => k.type === "goal").map((k) => ({ id: k.event_id, period: k.period, minute: k.minute, team: k.team }));
  const pens = m.score.penalties;
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15, duration: 0.6, ease: EASE }}>
      <Link to={matchPath(m.match_id)} aria-label={`Open ${m.teams.home.name} ${m.score.home}-${m.score.away} ${m.teams.away.name}, ${compLabel(m.competition, m.season)} final`}
        className="group block rounded-[24px] bg-surface-1 p-5 shadow-[0_40px_80px_-40px_rgba(0,8,4,0.9)] ring-1 ring-line transition-[box-shadow,background-color] duration-200 hover:bg-surface-2/60 hover:ring-line-strong sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-[13px] font-medium text-ink-3">Match of the day · {compLabel(m.competition, m.season)} final</p>
            <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[19px] font-semibold tracking-[-0.02em] text-ink sm:text-[22px]">
              <span className="flex items-center gap-2"><span className="size-3 rounded-[3px]" style={{ background: m.teams.home.color }} aria-hidden />{m.teams.home.name}</span>
              <span className="numeral text-[28px] leading-none">{m.score.home}<span className="px-1.5 text-ink-4">-</span>{m.score.away}</span>
              <span className="flex items-center gap-2">{m.teams.away.name}<span className="size-3 rounded-[3px]" style={{ background: m.teams.away.color }} aria-hidden /></span>
            </p>
            {pens && <p className="tabular mt-1 text-[13px] text-ink-3">{m.teams[pens.home > pens.away ? "home" : "away"].name} won {Math.max(pens.home, pens.away)}-{Math.min(pens.home, pens.away)} on penalties</p>}
          </div>
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-surface-3 text-ink-2 transition-[transform,background-color,color] duration-200 ease-[var(--ease-smooth-out)] group-hover:translate-x-0.5 group-hover:bg-ink group-hover:text-bg">
            <ArrowRight size={15} weight="bold" aria-hidden />
          </span>
        </div>
        <p className="mb-4 mt-5 text-[14px] text-ink-2">Who was on top, minute by minute</p>
        <MomentumPreview m={card} minutes={feat.minutes} turning={feat.turning} goals={goals} />
      </Link>
    </motion.div>
  );
}

function Rail({ id, title, intro, children }: { id: string; title: string; intro: string; children: ReactNode }) {
  return (
    <section aria-labelledby={`${id}-title`} className="mx-auto max-w-[1280px] pb-12 md:px-8">
      <div className="flex items-end justify-between gap-4 px-4 sm:px-5 md:px-0">
        <div>
          <h2 id={`${id}-title`} className="text-[22px] font-semibold tracking-[-0.025em] text-ink md:text-[26px]">{title}</h2>
          <p className="mt-1 text-[14.5px] text-ink-3">{intro}</p>
        </div>
      </div>
      <ul className="scroll-thin mt-5 flex snap-x snap-mandatory gap-3 overflow-x-auto scroll-px-4 px-4 pb-2 sm:scroll-px-5 sm:px-5 md:grid md:grid-cols-2 md:overflow-visible md:px-0 md:pb-0 lg:grid-cols-4">
        {children}
      </ul>
    </section>
  );
}

function CardSkeletons({ n }: { n: number }) {
  return <>{Array.from({ length: n }, (_, i) => <li key={i} className="h-[132px] w-[78vw] max-w-[300px] shrink-0 rounded-2xl bg-surface-1 ring-1 ring-line motion-safe:animate-pulse md:w-auto md:max-w-none" aria-hidden />)}</>;
}

/** A match card for the rails: competition, both teams with scores, and an optional one-line hook. */
function MatchTile({ m, hook, i }: { m: MatchCard; hook?: string; i: number }) {
  const winner = m.home_score > m.away_score ? "home" : m.away_score > m.home_score ? "away" : null;
  return (
    <motion.li className="w-[78vw] max-w-[300px] shrink-0 snap-start md:w-auto md:max-w-none"
      initial={{ opacity: 0, y: 8 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.3 }}
      transition={{ duration: 0.35, delay: Math.min(i * 0.04, 0.2), ease: EASE }}>
      <Link to={matchPath(m.match_id)}
        className="flex h-full flex-col rounded-2xl bg-surface-1 px-4 pb-4 pt-3.5 ring-1 ring-line transition-[background-color,box-shadow,transform] duration-150 ease-out hover:bg-surface-2 hover:ring-line-strong active:scale-[0.98]">
        <div className="mb-3 flex items-baseline justify-between gap-3 text-[12.5px] text-ink-3">
          <span className="truncate">{compLabel(m.competition, m.season)}{m.stage && m.stage !== "Regular Season" ? `, ${m.stage.toLowerCase()}` : ""}</span>
          <span className="tabular shrink-0">{hook ? "" : matchDate(m)}</span>
        </div>
        {(["home", "away"] as const).map((s) => (
          <div key={s} className="flex items-center gap-2.5 py-[3px]">
            <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: m[s].color }} aria-hidden />
            <span className={`flex-1 truncate text-[15px] ${winner === s ? "font-semibold text-ink" : "text-ink-2"}`}>{m[s].name}</span>
            <span className={`numeral text-[22px] leading-none ${winner === s ? "text-ink" : "text-ink-3"}`}>{s === "home" ? m.home_score : m.away_score}</span>
          </div>
        ))}
        {hook && <p className="mt-3 text-pretty text-[13.5px] leading-snug text-ink-2">{hook}</p>}
      </Link>
    </motion.li>
  );
}

/** What you can do once you're in a match, each with a link straight into it. */
function Showcase() {
  const final = matchPath(FEATURED);
  const items: { icon: ReactNode; title: string; body: string; cta: string; to?: string; onClick?: () => void; ai?: boolean }[] = [
    { icon: <Sparkle size={18} weight="fill" />, title: "The story in one glance", body: "Who was on top, the moments that decided it and the biggest swing, in a sentence or two.", cta: "See the 2022 final", to: final },
    { icon: <ChatCircleDots size={18} weight="fill" />, title: "Ask why, get the receipts", body: "Ask in your own words. Every answer links to the moments behind it, and the pitch jumps there.", cta: "Ask about the final", to: final, ai: true },
    { icon: <GitFork size={18} weight="bold" />, title: "What if it went differently", body: "Take away a goal, a red card or a substitution and see how the rest of the match was likely to go. Always labelled as modelled.", cta: "Try it on the final", to: final },
    { icon: <MagnifyingGlass size={18} weight="bold" />, title: "Find any moment", body: "Describe a moment the way you'd tell a friend, like “header from a corner”, and replay it.", cta: "Search moments", onClick: () => useUi.getState().setSearchOpen(true, "header from a corner") },
  ];
  return (
    <section aria-labelledby="showcase-title" className="mx-auto max-w-[1280px] px-4 pt-16 sm:px-5 md:px-8 md:pt-24">
      <Stagger>
        <Line n={1} as="h2" className="max-w-[24ch] text-balance text-[28px] font-semibold leading-[1.1] tracking-[-0.03em] text-ink md:text-[36px]">
          <span id="showcase-title">More than the scoreline</span>
        </Line>
        <Line n={2} as="p" className="mt-3 max-w-[60ch] text-pretty text-[15.5px] leading-[1.6] text-ink-3">
          Open any match and these are one tap away. No jargon needed: tap any underlined word for a plain explanation.
        </Line>
      </Stagger>
      <ul className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((it, i) => (
          <motion.li key={it.title} initial={{ opacity: 0, y: 10 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 0.4, delay: i * 0.05, ease: EASE }}
            className="flex flex-col rounded-[20px] bg-surface-1 p-6 ring-1 ring-line">
            <span className={`grid size-9 place-items-center rounded-xl ${it.ai ? "bg-ai-soft text-ai" : "bg-surface-3 text-ink-2"}`} aria-hidden>{it.icon}</span>
            <h3 className="mt-4 text-[17px] font-semibold tracking-[-0.015em] text-ink">{it.title}</h3>
            <p className="mt-1.5 text-pretty text-[14.5px] leading-[1.55] text-ink-3">{it.body}</p>
            {it.to
              ? <Link to={it.to} className={`t-learn mt-auto inline-flex items-center gap-1 self-start pt-6 text-[14px] font-medium transition-colors duration-150 ${it.ai ? "text-ai hover:text-ink" : "text-ink hover:text-ink-2"}`}>{it.cta}<LearnChevron /></Link>
              : <button type="button" onClick={it.onClick} className="t-learn mt-auto inline-flex items-center gap-1 self-start pt-6 text-[14px] font-medium text-ink transition-colors duration-150 hover:text-ink-2">{it.cta}<LearnChevron /></button>}
          </motion.li>
        ))}
      </ul>
    </section>
  );
}

/** Backtest teaser: the short answer in words, fetched only when the section scrolls into view. */
function BookiesTeaser() {
  const ref = useRef<HTMLElement>(null);
  const seen = useInView(ref, { once: true, margin: "200px" });
  const [bt, setBt] = useState<Backtest | null>(null);
  useEffect(() => { if (seen) api.backtest().then(setBt).catch(() => {}); }, [seen]);
  const answer = bt ? bookiesAnswer(bt) : null;
  return (
    <section ref={ref} aria-labelledby="bookies-title" className="mx-auto max-w-[1280px] px-4 pt-16 sm:px-5 md:px-8 md:pt-24">
      <div className="flex flex-col gap-6 rounded-[20px] bg-surface-1 p-6 ring-1 ring-line md:flex-row md:items-center md:justify-between md:p-8">
        <div className="min-w-0">
          <h2 id="bookies-title" className="text-[22px] font-semibold tracking-[-0.025em] text-ink md:text-[26px]">Would it beat the bookies?</h2>
          <p className="mt-2 max-w-[60ch] text-pretty text-[15px] leading-[1.6] text-ink-3">
            We tested our match model against real betting prices, using only what was known at the time.{" "}
            {answer ? <span className="text-ink-2">{answer}</span> : <span className="inline-block h-4 w-48 translate-y-0.5 rounded-full bg-surface-3 align-middle motion-safe:animate-pulse" aria-hidden />}
          </p>
        </div>
        <Link to="/backtest" className="t-learn inline-flex shrink-0 items-center gap-1 self-start text-[14.5px] font-medium text-ink transition-colors duration-150 hover:text-ink-2 md:self-center">
          See the full test<LearnChevron />
        </Link>
      </div>
    </section>
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
    <section aria-label="MatchPulse in numbers" className="mx-auto max-w-[1280px] px-4 pt-16 sm:px-5 md:px-8 md:pt-24">
      <dl ref={ref} className="grid grid-cols-2 gap-x-6 gap-y-8 border-t border-line pt-6 md:grid-cols-4">
        {items.map(([n, label], i) => (
          <div key={label} className="flex flex-col-reverse justify-end gap-1">
            <dt className={`text-[14px] text-ink-3 transition-opacity duration-500 ease-out motion-reduce:transition-none ${inView ? "opacity-100" : "opacity-0"}`} style={{ transitionDelay: `${300 + i * 120}ms` }}>{label}</dt>
            <dd className="numeral text-[34px] leading-none text-ink md:text-[42px]">
              <SpinningNumber value={n} active={inView} delay={250 + i * 120} />
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
