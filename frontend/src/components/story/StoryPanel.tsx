import { useMemo, type ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import { ArrowRight, CaretDown, ChatCircleDots, GitFork, Play, TrendUp } from "@phosphor-icons/react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Explain } from "@/components/ui/explain";
import type { Side } from "../../api/types";
import type { GlossaryKey } from "../../lib/glossary";
import { pct, undash, xg } from "../../lib/format";
import { keyMoments, matchVerdict, type KeyMoment } from "../../lib/story";
import { useMatch } from "../../store/match";
import { CommentaryFeed } from "../sequences/CommentaryFeed";

const EASE = [0.22, 1, 0.36, 1] as const;

/** The default match tab: the story in one glance (verdict, who was on top, the moments that decided it), then ways to dig in. */
export function StoryPanel() {
  const data = useMatch((s) => s.data);
  const reel = useMatch((s) => s.reel);
  const commentaryStatus = useMatch((s) => s.commentaryStatus);
  const reduce = useReducedMotion();
  const verdict = useMemo(() => (data ? matchVerdict(data) : null), [data]);
  const moments = useMemo(() => (data ? keyMoments(data) : []), [data]);
  if (!data || !verdict) return null;
  const st = useMatch.getState;
  const enter = (i: number) => ({
    initial: reduce ? { opacity: 0 } : { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.35, delay: 0.05 + i * 0.05, ease: EASE },
  });
  const canReplay = data.has.events && moments.some((m) => m.seq);
  const tp = data.turningPoints.length ? [...data.turningPoints].sort((a, b) => a.rank - b.rank)[0] : null;

  return (
    <div className="scroll-thin h-full overflow-y-auto px-5 pb-6">
      {data.has.lite && (
        <p className="mb-4 rounded-2xl bg-surface-2 px-4 py-3 text-pretty text-[13px] leading-[1.5] text-ink-2 ring-1 ring-line">
          <span className="font-semibold text-ink">Shots and stats only.</span> We have the score, line-ups and shots for this match, but not every touch, so there's no replay or What if.
        </p>
      )}
      <motion.section {...enter(0)} aria-labelledby="story-title" className="pt-1">
        <p className="text-[12.5px] font-medium text-ink-3">The story</p>
        <h2 id="story-title" className="mt-1 text-balance text-[20px] font-semibold leading-[1.25] tracking-[-0.02em] text-ink">{verdict.headline}</h2>
        {verdict.lead && <p className="mt-2 text-pretty text-[15px] leading-[1.55] text-ink-2">{verdict.lead}</p>}
        {verdict.notes.length > 0 && (
          <ul className="mt-2 space-y-1">
            {verdict.notes.map((n) => <li key={n} className="text-pretty text-[14px] leading-[1.55] text-ink-3">{n}</li>)}
          </ul>
        )}
      </motion.section>

      {(canReplay || tp) && (
        <motion.div {...enter(1)} className="mt-4 flex flex-wrap gap-2">
          {canReplay && (
            <button type="button" onClick={() => (reel ? st().stopHighlights() : (st().playHighlights(), st().pingPitch()))}
              className="flex h-10 items-center gap-2 rounded-full bg-ink pl-3.5 pr-4 text-[13.5px] font-semibold text-bg transition-[transform,background-color] duration-150 ease-out hover:bg-ink-2 active:scale-[0.97]">
              <Play size={13} weight="fill" aria-hidden />{reel ? "Stop the highlights" : "Watch the highlights"}
            </button>
          )}
          {tp && (
            <button type="button" onClick={() => { st().focusTurningPoint(tp.id); st().pingPitch(); }}
              className="flex h-10 items-center gap-2 rounded-full bg-surface-2 pl-3.5 pr-4 text-[13.5px] font-semibold text-ink ring-1 ring-line transition-[transform,background-color] duration-150 ease-out hover:bg-surface-3 active:scale-[0.97]">
              <TrendUp size={15} weight="bold" aria-hidden />Where it turned
            </button>
          )}
        </motion.div>
      )}

      {data.has.timeline && <motion.div {...enter(2)}><WhoWasOnTop /></motion.div>}

      {moments.length > 0 && (
        <motion.section {...enter(3)} aria-labelledby="moments-title" className="mt-7">
          <h3 id="moments-title" className="mb-2.5 text-[15px] font-semibold tracking-[-0.01em] text-ink">Moments that decided it</h3>
          <ol className="overflow-hidden rounded-2xl bg-surface-2 ring-1 ring-line">
            {moments.map((m, i) => <MomentRow key={m.key} m={m} first={i === 0} />)}
          </ol>
          {data.has.events && <p className="mt-2 px-1 text-[12.5px] text-ink-3">Tap a moment to replay it on the pitch.</p>}
        </motion.section>
      )}

      {commentaryStatus === "ready" && (
        <motion.div {...enter(4)} className="mt-7">
          <Collapsible className="group/pbp rounded-2xl bg-surface-2 ring-1 ring-line">
            <CollapsibleTrigger className="flex w-full items-center justify-between gap-3 px-4 py-3.5 text-left">
              <span>
                <span className="block text-[15px] font-semibold tracking-[-0.01em] text-ink">Play by play</span>
                <span className="mt-0.5 block text-[12.5px] text-ink-3">Every attack in a line, written by AI from the match events</span>
              </span>
              <CaretDown size={14} weight="bold" className="shrink-0 text-ink-3 transition-transform duration-200 group-data-[state=open]/pbp:rotate-180" aria-hidden />
            </CollapsibleTrigger>
            <CollapsibleContent data-feed-scroll className="relative max-h-[520px] overflow-y-auto scroll-thin">
              <CommentaryFeed />
            </CollapsibleContent>
          </Collapsible>
        </motion.div>
      )}

      <motion.section {...enter(5)} aria-label="Dig deeper" className="mt-7 grid grid-cols-2 gap-2.5">
        <NextStep icon={<ChatCircleDots size={17} weight="fill" />} ai title="Ask why" body="Questions answered with the moments behind them" onClick={() => st().setRightTab("ask")} />
        {data.has.events
          ? <NextStep icon={<GitFork size={17} weight="bold" />} title="What if" body="Take away a goal or a red card and see what might have happened" onClick={() => st().setRightTab("whatif")} />
          : <NextStep icon={<ArrowRight size={17} weight="bold" />} title="Players" body="Who played and who made a difference" onClick={() => st().setRightTab("players")} />}
      </motion.section>
    </div>
  );
}

function NextStep({ icon, title, body, onClick, ai }: { icon: ReactNode; title: string; body: string; onClick: () => void; ai?: boolean }) {
  return (
    <button type="button" onClick={onClick}
      className={`group flex flex-col items-start gap-2.5 rounded-2xl bg-surface-2 p-3.5 text-left ring-1 ring-line transition-[background-color,box-shadow,transform] duration-150 ease-out hover:bg-surface-3 active:scale-[0.98] ${ai ? "hover:ring-[var(--ai-line)]" : "hover:ring-line-strong"}`}>
      <span className={`grid size-8 place-items-center rounded-[10px] ${ai ? "bg-ai-soft text-ai" : "bg-surface-4 text-ink-2"}`} aria-hidden>{icon}</span>
      <span>
        <span className="flex items-center gap-1 text-[14px] font-semibold text-ink">{title}<ArrowRight size={12} weight="bold" className="text-ink-3 transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden /></span>
        <span className="mt-0.5 block text-pretty text-[12.5px] leading-snug text-ink-3">{body}</span>
      </span>
    </button>
  );
}

function MomentRow({ m, first }: { m: KeyMoment; first: boolean }) {
  const focus = useMatch((s) => s.focus);
  const replay = useMatch((s) => s.replay);
  const data = useMatch((s) => s.data!);
  const active = (m.seq && (replay?.sequenceId === m.seq || (focus?.kind === "sequence" && focus.id === m.seq)))
    || (m.tp && focus?.kind === "turning" && focus.id === m.tp)
    || (m.ev && focus?.kind === "event" && focus.id === m.ev);
  const raw = useMatch((s) => (m.seq ? s.commentaryBySeq.get(m.seq)?.text : undefined));
  const caption = raw ? undash(raw) : undefined;
  const go = () => {
    const st = useMatch.getState();
    if (m.tp) { st.focusTurningPoint(m.tp); st.pingPitch(); }
    else if (m.seq && data.has.events) st.showMoment({ seq: m.seq, replay: true });
    else if (m.ev) st.showMoment({ ev: m.ev });
  };
  const sub = m.sub ?? caption ?? null;
  const tag = m.kind === "goal" ? "Goal" : m.kind === "red" ? "Red card" : m.kind === "swing" ? "Turning point" : "Chance";
  return (
    <li className={first ? "" : "border-t border-line"}>
      <button type="button" onClick={go} aria-current={active || undefined}
        aria-label={`${m.clock}, ${tag}: ${m.title}.${m.score ? ` Score ${m.score}.` : ""} ${m.seq && data.has.events ? "Replay on the pitch" : "Show on the pitch"}`}
        className={`group flex w-full items-start gap-3 px-3.5 py-3 text-left transition-colors duration-150 ${active ? "bg-surface-4" : "hover:bg-surface-3"}`}>
        <span className="numeral w-12 shrink-0 pt-px text-[18px] leading-none text-ink">{m.clock}</span>
        <span className={`mt-0.5 h-4 w-1 shrink-0 rounded-full ${m.kind === "red" ? "bg-card-red" : ""}`} style={m.kind === "red" ? undefined : { background: `var(--${m.team})` }} aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-2">
            <span className={`text-[14px] font-semibold leading-snug ${m.kind === "swing" ? "text-ai" : "text-ink"}`}>{m.title}</span>
          </span>
          {sub && <span className="mt-0.5 line-clamp-2 block text-pretty text-[12.5px] leading-snug text-ink-3">{sub}</span>}
        </span>
        {m.score
          ? <span className="numeral shrink-0 text-[18px] leading-none text-ink-2">{m.score}</span>
          : m.seq && data.has.events && <span className="grid size-6 shrink-0 place-items-center rounded-full bg-surface-4 text-ink-2 transition-colors duration-150 group-hover:bg-ink group-hover:text-bg" aria-hidden><Play size={9} weight="fill" /></span>}
      </button>
    </li>
  );
}

/** Two-sided bars for the full match, in team colours: the broadcast stat panel. */
function WhoWasOnTop() {
  const data = useMatch((s) => s.data!);
  const { teams } = data.match;
  const rows = useMemo(() => {
    const tl = data.timeline;
    const sum = (s: Side, k: "shots" | "xg") => tl.reduce((a, m) => a + m[s][k], 0);
    const avg = (s: Side, k: "possession" | "field_tilt") => tl.reduce((a, m) => a + m[s][k], 0) / Math.max(tl.length, 1);
    const rows = [
      { label: "Chances", term: "chances" as GlossaryKey, a: sum("home", "xg"), b: sum("away", "xg"), fmt: xg },
      { label: "Territory", term: "territory" as GlossaryKey, a: avg("home", "field_tilt"), b: avg("away", "field_tilt"), fmt: (v: number) => pct(v) },
      { label: "Possession", term: "possession" as GlossaryKey, a: avg("home", "possession"), b: avg("away", "possession"), fmt: (v: number) => pct(v) },
      { label: "Shots", term: "shots" as GlossaryKey, a: sum("home", "shots"), b: sum("away", "shots"), fmt: (v: number) => String(v) },
    ];
    // lite matches only measure chances and shots
    return data.has.possession ? rows : rows.filter((r) => r.term === "chances" || r.term === "shots");
  }, [data]);
  return (
    <section aria-labelledby="ontop-title" className="mt-7">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 id="ontop-title" className="text-[15px] font-semibold tracking-[-0.01em] text-ink">Who was on top</h3>
        <span className="flex min-w-0 items-center gap-3 text-[12px] text-ink-3">
          <span className="flex min-w-0 items-center gap-1.5"><span className="size-2 shrink-0 rounded-[2px] bg-home" aria-hidden /><span className="truncate">{teams.home.short || teams.home.name}</span></span>
          <span className="flex min-w-0 items-center gap-1.5"><span className="size-2 shrink-0 rounded-[2px] bg-away" aria-hidden /><span className="truncate">{teams.away.short || teams.away.name}</span></span>
        </span>
      </div>
      <dl className="space-y-3.5 rounded-2xl bg-surface-2 p-4 ring-1 ring-line">
        {rows.map((r) => {
          const total = r.a + r.b || 1;
          const lead = r.a > r.b ? "home" : r.b > r.a ? "away" : null;
          return (
            <div key={r.label}>
              <div className="mb-1.5 grid grid-cols-[1fr_auto_1fr] items-baseline gap-2">
                <dd className={`numeral text-[19px] leading-none ${lead === "home" ? "text-ink" : "text-ink-3"}`}>{r.fmt(r.a)}</dd>
                <dt className="text-center text-[12.5px] text-ink-2"><Explain term={r.term}>{r.label}</Explain></dt>
                <dd className={`numeral text-right text-[19px] leading-none ${lead === "away" ? "text-ink" : "text-ink-3"}`}>{r.fmt(r.b)}</dd>
              </div>
              <div className="flex h-[5px] gap-[3px]" aria-hidden>
                <div className="rounded-full bg-home" style={{ width: `${(r.a / total) * 100}%`, opacity: lead === "away" ? 0.55 : 1 }} />
                <div className="flex-1 rounded-full bg-away" style={{ opacity: lead === "home" ? 0.55 : r.b === 0 ? 0.15 : 1 }} />
              </div>
            </div>
          );
        })}
      </dl>
    </section>
  );
}
