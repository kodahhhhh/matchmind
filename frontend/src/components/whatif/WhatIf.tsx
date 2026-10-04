import { useEffect, useRef, useState, type ReactNode } from "react";
import { scaleLinear } from "d3-scale";
import { area, line } from "d3-shape";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowRight, ArrowsLeftRight, CaretDown, Target } from "@phosphor-icons/react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { api } from "../../api/client";
import type { Counterfactual, Marker, MatchEvent, ShotAlternatives, Side } from "../../api/types";
import { useMatch } from "../../store/match";
import { clock, pct, signed, xg } from "../../lib/format";
import { PitchMarkings } from "../pitch/PitchMarkings";
import { PITCH, sy } from "../pitch/geometry";

const EASE = [0.22, 1, 0.36, 1] as const;

const CHANGE: Record<string, { change: Counterfactual["change"]; verb: string }> = {
  goal: { change: "remove_goal", verb: "never happened" },
  sub: { change: "no_sub", verb: "wasn't made" },
  card: { change: "remove_red_card", verb: "wasn't shown" },
};

type Pick = { kind: "marker"; marker: Marker } | { kind: "shot"; shot: MatchEvent };
type Outcome = { kind: "marker"; r: Counterfactual } | { kind: "shot"; r: ShotAlternatives };

/** Staggered entrance shared by every result block. */
function useEnter() {
  const reduce = useReducedMotion();
  return (i: number) => ({
    // No blur filter: animating filters inside the scrolling panel left cards half-painted in some browsers.
    initial: reduce ? { opacity: 0 } : { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.35, delay: Math.min(i * 0.04, 0.16), ease: EASE },
  });
}

export function WhatIf() {
  const data = useMatch((s) => s.data);
  const focusEvent = useMatch((s) => s.focusEvent);
  const [picked, setPicked] = useState<Pick | null>(null);
  const [result, setResult] = useState<Outcome | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const resultRef = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();
  useEffect(() => {
    if (result) resultRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  }, [result, reduce]);

  if (!data) return null;
  const nameOf = (id: number | null | undefined) =>
    [...data.match.lineups.home, ...data.match.lineups.away].find((p) => p.player_id === id)?.short_name ?? "Unknown";
  const options = data.match.markers.filter((m) => m.type === "goal" || m.type === "sub" || (m.type === "card" && m.detail !== "yellow"));
  const shots = data.events.filter((e) => e.type === "shot" && e.period < 5);
  const title = (m: Marker) =>
    m.type === "goal" ? `${nameOf(m.player_id)}'s goal` : m.type === "sub" ? `the ${nameOf(m.player_off_id)} substitution` : `${nameOf(m.player_id)}'s red card`;
  const label = (m: Marker) => (m.type === "sub" ? `${nameOf(m.player_off_id)} → ${nameOf(m.player_id)}` : nameOf(m.player_id));

  const run = (next: Pick, request: () => Promise<Outcome>) => {
    setPicked(next);
    setFailed(false);
    focusEvent(next.kind === "marker" ? next.marker.event_id : next.shot.id);
    setLoading(true);
    request()
      .then(setResult)
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  };
  const pickMarker = (m: Marker) =>
    run({ kind: "marker", marker: m }, () =>
      api.counterfactual(data.match.match_id, m.event_id, CHANGE[m.type].change).then((r) => ({ kind: "marker", r })));
  const pickShot = (e: MatchEvent) =>
    run({ kind: "shot", shot: e }, () =>
      api.shotAlternatives(data.match.match_id, e.id).then((r) => ({ kind: "shot", r })));

  const firsts = options.filter((m) => m.type !== "sub");
  const groups: [string, Marker[]][] = [
    [firsts.some((m) => m.type === "card") ? "Goals and red cards" : "Goals", firsts],
    ["Substitutions", options.filter((m) => m.type === "sub")],
  ];
  const pickedId = picked ? (picked.kind === "marker" ? picked.marker.event_id : picked.shot.id) : null;
  const chip = (on: boolean) =>
    `flex min-h-8 items-center gap-2 rounded-full py-1.5 pl-2.5 pr-3 text-[13px] font-medium ring-1 transition-[background-color,color,box-shadow,transform] duration-150 ease-out active:scale-[0.97] ${on ? "bg-ink text-bg ring-ink" : "bg-surface-2 text-ink-2 ring-line hover:bg-surface-3 hover:text-ink"}`;
  const shown = result && picked && result.kind === picked.kind ? result : null;

  return (
    <div className="scroll-thin h-full overflow-y-auto px-5 pb-5">
      <div className="pt-1">
        <div className="flex items-center gap-2">
          <h2 className="text-[16px] font-semibold leading-snug tracking-[-0.015em] text-ink">What if</h2>
          <span className="rounded-full bg-ai-soft px-2 py-[1px] text-[12px] font-medium text-ai ring-1 ring-[var(--ai-line)]">Modelled</span>
        </div>
        <p className="mt-1 text-pretty text-[13.5px] leading-[1.55] text-ink-3">
          Pick a moment and see how the next 15 minutes look without it. Or pick a shot to see if a pass was the better option.
        </p>
      </div>

      {groups.map(([group, ms]) => ms.length > 0 && (
        <section key={group} aria-label={group} className="mt-5">
          <h3 className="mb-2.5 text-[14px] font-semibold tracking-[-0.01em] text-ink">{group}</h3>
          <div className="flex flex-wrap gap-1.5">
            {ms.map((m) => {
              const on = pickedId === m.event_id;
              return (
                <button key={m.event_id + m.type} type="button" aria-pressed={on} onClick={() => pickMarker(m)} className={chip(on)}>
                  <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: `var(--${m.team})` }} aria-hidden />
                  <span className={`tabular ${on ? "text-bg/60" : "text-ink-3"}`}>{clock(m.period, m.minute)}</span>
                  {label(m)}
                </button>
              );
            })}
          </div>
        </section>
      ))}

      {shots.length > 0 && (
        <section aria-label="Shots" className="mt-5">
          <h3 className="text-[14px] font-semibold tracking-[-0.01em] text-ink">Shots</h3>
          <p className="mb-2.5 mt-0.5 text-[12.5px] text-ink-3">Should they have passed instead? The number is the chance it went in.</p>
          <div className="flex flex-wrap gap-1.5">
            {shots.map((e) => {
              const on = pickedId === e.id;
              return (
                <button key={e.id} type="button" aria-pressed={on} onClick={() => pickShot(e)} className={chip(on)}>
                  <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: `var(--${e.team})` }} aria-hidden />
                  <span className={`tabular ${on ? "text-bg/60" : "text-ink-3"}`}>{clock(e.period, e.minute)}</span>
                  {e.player ?? "Unknown"}
                  <span className={`tabular ${on ? "text-bg/60" : "text-ink-3"}`}>{e.xg == null ? "" : pct(e.xg)}</span>
                </button>
              );
            })}
          </div>
        </section>
      )}

      {picked && (
        <div ref={resultRef} className="mt-7 scroll-mt-4" aria-busy={loading}>
          <h3 className="text-balance text-[17px] font-semibold leading-snug tracking-[-0.015em] text-ink">
            {picked.kind === "marker"
              ? `What if ${title(picked.marker)} ${CHANGE[picked.marker.type].verb}?`
              : `What if ${picked.shot.player ?? "the shooter"} had passed instead of shooting?`}
          </h3>
          <p className="mt-1 text-[13px] text-ink-3">
            {picked.kind === "marker"
              ? `How the rest of the match looks from ${clock(picked.marker.period, picked.marker.minute)}, with and without it.`
              : `Every teammate ${picked.shot.player ?? "the shooter"} could have passed to at ${clock(picked.shot.period, picked.shot.minute)}.`}
          </p>
          <p role="status" className="sr-only">{loading ? "Running the model" : failed ? "Unable to run the model" : shown ? "Modelled result ready" : ""}</p>
          {failed && !loading ? (
            <div className="mt-4 rounded-2xl bg-surface-2 px-4 py-5 ring-1 ring-line">
              <p className="text-[14px] font-medium text-ink">Unable to run the model for this moment</p>
              <p className="mt-1 text-[13px] text-ink-3">
                {picked.kind === "shot"
                  ? "No player positions were recorded for this shot. Try another one."
                  : "Check that the API is running, then pick the moment again or try another one."}
              </p>
            </div>
          ) : loading && !shown ? <ResultSkeleton /> : shown && (
            <div className={`transition-opacity duration-200 ${loading ? "opacity-50" : "opacity-100"}`}>
              <AnimatePresence mode="wait" initial={false}>
                {shown.kind === "marker"
                  ? <Result key={`${shown.r.event_id}-${shown.r.change}`} r={shown.r} />
                  : <ShotBranch key={shown.r.event_id} r={shown.r} />}
              </AnimatePresence>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ResultSkeleton() {
  return (
    <div className="mt-4 space-y-3" aria-hidden>
      <div className="h-11 rounded-xl bg-surface-2 motion-safe:animate-pulse" />
      {[0, 1].map((i) => (
        <div key={i} className="space-y-3 rounded-2xl bg-surface-2 p-4 ring-1 ring-line">
          <div className="h-4 w-28 rounded-full bg-surface-3 motion-safe:animate-pulse" />
          <div className="flex gap-6">
            <div className="h-9 w-16 rounded-lg bg-surface-3 motion-safe:animate-pulse" />
            <div className="h-9 w-32 rounded-lg bg-surface-3 motion-safe:animate-pulse" />
          </div>
          <div className="h-[88px] rounded-xl bg-surface-3 motion-safe:animate-pulse" />
        </div>
      ))}
    </div>
  );
}

const scoreText = (s: string) => {
  const n = Number(s);
  if (!Number.isFinite(n)) return `score ${s}`;
  return n === 0 ? "level" : n > 0 ? `leading by ${n}` : `trailing by ${-n}`;
};

/** Signed change, or "no change" when it rounds to zero. */
const delta = (v: number, digits: number, unit: string) =>
  Math.abs(v) < 0.5 * 10 ** -digits ? "no change" : `${signed(v, digits)}${unit}`;

function Figure({ label, value, range, accent }: { label: string; value: string; range?: [number, number]; accent?: boolean }) {
  return (
    <div className="flex min-w-0 flex-col-reverse gap-1">
      {range && <dd className="tabular whitespace-nowrap text-[11.5px] text-ink-3">{xg(range[0])} to {xg(range[1])}</dd>}
      <dd className="numeral text-[30px] leading-none text-ink">{value}</dd>
      <dt className={`whitespace-nowrap text-[12px] ${accent ? "text-ai" : "text-ink-3"}`}>{label}</dt>
    </div>
  );
}

/** "See the numbers" disclosure: the technical detail lives here, closed by default. */
function Details({ label = "See the numbers", children }: { label?: string; children: ReactNode }) {
  return (
    <Collapsible className="group/details rounded-2xl bg-surface-1 ring-1 ring-line">
      <CollapsibleTrigger className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-[13.5px] font-medium text-ink-2 transition-colors hover:text-ink">
        {label}
        <CaretDown size={14} weight="bold" className="shrink-0 text-ink-3 transition-transform duration-200 group-data-[state=open]/details:rotate-180" aria-hidden />
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-3 px-3 pb-3">{children}</CollapsibleContent>
    </Collapsible>
  );
}

function Result({ r }: { r: Counterfactual }) {
  const data = useMatch((s) => s.data!);
  const teams = data.match.teams;
  const enter = useEnter();
  const swap = r.lineup_change;
  const out = r.result;
  const chance = r.scoring_chance;

  // Headline: the biggest shift in how the match ends (falls back to the 15-minute view).
  const shift = out ? (["home", "away"] as Side[]).map((s) => ({ s, d: out.modelled[s] - out.factual[s] })).sort((a, b) => b.d - a.d)[0] : null;
  const headline = r.negligible || !shift || shift.d < 0.03
    ? "Almost no difference."
    : shift.d >= 0.2 ? `A big swing towards ${teams[shift.s].name}.`
    : shift.d >= 0.07 ? `A swing towards ${teams[shift.s].name}.`
    : `A small swing towards ${teams[shift.s].name}.`;
  const sc = out?.score;
  const scoreChanged = sc && (sc.factual.home !== sc.modelled.home || sc.factual.away !== sc.modelled.away);
  const at = clock(r.anchor.period, r.anchor.minute);
  const explain = scoreChanged
    ? `Without it, the score at ${at} is ${sc.modelled.home}-${sc.modelled.away} instead of ${sc.factual.home}-${sc.factual.away}.`
    : swap?.removed ? `Keeping ${swap.restored.name} on instead of ${swap.removed.name}.`
    : swap ? `${swap.restored.name} stays on, so it's eleven against eleven.`
    : "";
  const end = out?.block === "extra_time" ? "after extra time" : "at full time";
  const level = out?.level_means === "extra_time" ? "Goes to extra time" : out?.level_means === "penalties" ? "Goes to penalties" : "Draw";
  const rows = out ? ([["home", `${teams.home.name} win`], ["level", level], ["away", `${teams.away.name} win`]] as const) : [];

  return (
    <motion.div exit={{ opacity: 0, transition: { duration: 0.12 } }} className="mt-4 space-y-3">
      <motion.div {...enter(0)} className="rounded-2xl bg-ai-soft px-4 py-3.5 ring-1 ring-[var(--ai-line)]">
        <p className="text-[12px] font-medium text-ai">What the model says</p>
        <p className="mt-0.5 text-balance text-[18px] font-semibold leading-snug tracking-[-0.01em] text-ink">{headline}</p>
        <p className="mt-1 text-pretty text-[13px] leading-[1.5] text-ink-2">
          {explain} {r.negligible ? "The model sees the rest of the match playing out about the same." : "Estimated from what happened next in thousands of similar matches."}
        </p>
      </motion.div>

      {out && (
        <motion.section {...enter(1)} aria-labelledby="ending-title" className="rounded-2xl bg-surface-2 p-4 ring-1 ring-line">
          <h4 id="ending-title" className="text-[14px] font-semibold text-ink">How it ends {end}</h4>
          <p className="mt-0.5 text-[12.5px] text-ink-3">Chance of each result, as it was and with the change</p>
          <ul className="mt-3 space-y-3">
            {rows.map(([k, label]) => {
              const a = out.factual[k], b = out.modelled[k];
              const color = k === "level" ? "var(--ink-3)" : `var(--${k})`;
              return (
                <li key={k}>
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="flex min-w-0 items-center gap-2 text-[13.5px] font-medium text-ink">
                      <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: color }} aria-hidden />
                      <span className="truncate">{label}</span>
                    </span>
                    <span className="tabular flex shrink-0 items-baseline gap-2 text-[13px]">
                      <span className="text-ink-3">{pct(a)}</span>
                      <ArrowRight size={12} weight="bold" className="text-ink-4" aria-hidden />
                      <span className="numeral text-[22px] leading-none text-ink">{pct(b)}</span>
                    </span>
                  </div>
                  <div className="mt-1.5 space-y-[3px]" aria-hidden>
                    <div className="h-[4px] rounded-full bg-surface-4"><div className="h-full rounded-full opacity-40" style={{ width: `${a * 100}%`, background: color }} /></div>
                    <div className="h-[4px] rounded-full bg-surface-4"><div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${b * 100}%`, background: color }} /></div>
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 text-[12.5px] text-ink-3">In the real match: {realEnding(data, out.block)}</p>
        </motion.section>
      )}

      {swap && (
        <motion.p {...enter(2)} className="flex items-start gap-2.5 rounded-xl bg-surface-2 px-3.5 py-2.5 text-[13px] leading-[1.5] text-ink-2 ring-1 ring-line">
          <ArrowsLeftRight size={15} weight="bold" className="mt-[2px] shrink-0 text-ink-3" aria-hidden />
          <span>
            {swap.removed
              ? <>Keeps <b className="font-semibold text-ink">{swap.restored.name}</b> on instead of bringing on <b className="font-semibold text-ink">{swap.removed.name}</b>. Across their other matches, {impactCompare(swap.restored, swap.removed)}.</>
              : <>Keeps <b className="font-semibold text-ink">{swap.restored.name}</b> on the pitch, so the team plays with eleven.</>}
          </span>
        </motion.p>
      )}

      {chance && (
        <motion.section {...enter(3)} aria-labelledby="next15-title" className="rounded-2xl bg-surface-2 p-4 ring-1 ring-line">
          <h4 id="next15-title" className="text-[14px] font-semibold text-ink">Chance of scoring in the next {r.horizon_minutes} minutes</h4>
          <ul className="mt-2.5 space-y-2">
            {(["home", "away"] as Side[]).map((s) => (
              <li key={s} className="flex items-center gap-3">
                <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: `var(--${s})` }} aria-hidden />
                <span className="min-w-0 flex-1 truncate text-[13.5px] font-medium text-ink">{teams[s].name}</span>
                <span className="tabular flex items-baseline gap-2 text-[13px]">
                  <span className="text-ink-3">{pct(chance.factual[s])}</span>
                  <ArrowRight size={12} weight="bold" className="text-ink-4" aria-hidden />
                  <span className="numeral text-[22px] leading-none text-ink">{pct(chance.modelled[s])}</span>
                </span>
                <span className="w-[96px] shrink-0 text-right text-[12px] leading-tight text-ink-3">
                  Really: {r.actual[s].goals > 0 ? `scored ${r.actual[s].goals === 1 ? "once" : `${r.actual[s].goals}`}` : "no goal"}
                </span>
              </li>
            ))}
          </ul>
        </motion.section>
      )}

      <motion.div {...enter(4)}>
        <Details>
          <DetailNumbers r={r} />
        </Details>
      </motion.div>
      <p className="text-pretty text-[12px] leading-[1.55] text-ink-3">{r.caveat}</p>
    </motion.div>
  );
}

/** What actually happened at the end of the block the model is predicting. */
function realEnding(data: NonNullable<ReturnType<typeof useMatch.getState>["data"]>, block: "normal_time" | "extra_time") {
  const goals = data.match.markers.filter((m) => m.type === "goal" && m.period <= (block === "extra_time" ? 4 : 2));
  const h = goals.filter((m) => m.team === "home").length;
  const a = goals.filter((m) => m.team === "away").length;
  const { home, away } = data.match.teams;
  const when = block === "extra_time" ? "after extra time" : "at full time";
  if (h !== a) return `${h}-${a} ${when}, ${h > a ? home.name : away.name} won.`;
  const pens = data.match.score.penalties;
  if (pens) return `${h}-${a} ${when}, ${pens.home > pens.away ? home.name : away.name} won on penalties.`;
  const total = data.match.score;
  if (block === "normal_time" && (total.home !== h || total.away !== a)) {
    return `${h}-${a} ${when}, ${total.home > total.away ? home.name : away.name} won in extra time.`;
  }
  return `${h}-${a} ${when}.`;
}

/** Compare two players' career impact in words, never as a bare rating. */
function impactCompare(kept: { name: string; vaep_per90: number }, sub: { name: string; vaep_per90: number }) {
  const diff = kept.vaep_per90 - sub.vaep_per90;
  if (Math.abs(diff) < 0.02) return "both have had about the same impact per game";
  return diff > 0 ? `${kept.name} has had more impact per game` : `${sub.name} has had more impact per game`;
}

/** The analyst-grade view: expected goals, ranges, the chart, model accuracy and similar real games. */
function DetailNumbers({ r }: { r: Counterfactual }) {
  const teams = useMatch((s) => s.data!.match.teams);
  const base = r.factual ?? r.modelled;
  const swap = r.lineup_change;
  return (
    <>
      <p className="px-1 text-pretty text-[12.5px] leading-[1.5] text-ink-3">
        Chances are built from expected goals (xG): the quality of the chances a team creates, where 1.00 is one goal's worth.
        Ranges show where the real number lands 8 times in 10.
      </p>
      {(["home", "away"] as Side[]).map((s) => (
        <section key={s} aria-label={`${teams[s].name} details`} className="rounded-xl bg-surface-2 p-3.5 ring-1 ring-line">
          <h5 className="mb-2.5 flex items-center gap-2 text-[13px] font-semibold text-ink">
            <span className="size-2 shrink-0 rounded-[3px]" style={{ background: `var(--${s})` }} aria-hidden />{teams[s].name}, xG
          </h5>
          <dl className="grid grid-cols-3 gap-3">
            <Figure label="What happened" value={xg(r.actual[s].xg)} />
            <Figure label="Model, as it was" value={xg(base[s].xg.p50)} range={[base[s].xg.p10, base[s].xg.p90]} />
            <Figure label="Model, changed" accent value={xg(r.modelled[s].xg.p50)} range={[r.modelled[s].xg.p10, r.modelled[s].xg.p90]} />
          </dl>
          {r.effect && (
            <p className="tabular mt-3 text-pretty text-[12px] text-ink-3">
              Change: <span className="text-ink-2">{delta(r.effect[s].xg, 2, " xG")}</span>, possession <span className="text-ink-2">{delta(r.effect[s].possession * 100, 1, " points")}</span> from <span className="text-ink-2">{pct(base[s].possession.p50)}</span>.
            </p>
          )}
          <RangeChart r={r} side={s} />
        </section>
      ))}
      {swap && (
        <p className="px-1 text-[12px] text-ink-3">
          Player impact (VAEP per 90 minutes, from every other match): {swap.restored.name} <span className="tabular text-ink-2">{swap.restored.vaep_per90.toFixed(2)}</span>
          {swap.removed && <>, {swap.removed.name} <span className="tabular text-ink-2">{swap.removed.vaep_per90.toFixed(2)}</span></>}.
        </p>
      )}
      {r.model && (
        <p className="flex items-start gap-2 px-1 text-[12px] leading-[1.5] text-ink-3">
          <Target size={14} weight="bold" className="mt-[1px] shrink-0 text-ai" aria-hidden />
          <span>
            Trained on <span className="tabular">{r.model.trained_matches.toLocaleString("en-GB")}</span> matches. The real outcome lands inside its range <span className="tabular">{Math.round(r.model.coverage_p10_p90.xg * 100)}%</span> of the time
            {r.model.skill_vs_constant && <>, and it beats a one-size-fits-all guess by <span className="tabular">{Math.round(r.model.skill_vs_constant.possession * 100)}%</span> for possession and <span className="tabular">{Math.round(r.model.skill_vs_constant.xg * 100)}%</span> for chances</>}.
          </span>
        </p>
      )}
      <section aria-labelledby="analogs-title">
        <div className="mb-2 px-1">
          <h5 id="analogs-title" className="text-[13px] font-semibold text-ink">Real games in the same situation</h5>
          <p className="text-[12px] text-ink-3">How alike they are, then xG for and against in the next {r.horizon_minutes} minutes</p>
        </div>
        <ul className="overflow-hidden rounded-xl bg-surface-2 ring-1 ring-line">
          {r.analogs.map((a, i) => (
            <li key={a.match_id + a.minute + i} className={`flex items-center gap-3 px-3.5 py-2.5 ${i ? "border-t border-line" : ""}`}>
              <span className="tabular w-9 shrink-0 text-[12.5px] font-semibold text-ink-2">
                {Math.round(a.similarity * 100)}%<span className="sr-only"> similar</span>
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] font-medium text-ink">{a.home} v {a.away}</div>
                <div className="text-pretty text-[12px] leading-snug text-ink-3">{a.minute}', {scoreText(a.score_state)} · {a.competition} {a.season}</div>
              </div>
              <div className="tabular shrink-0 text-right text-[12px] leading-snug text-ink-3">
                <span className="text-ink-2">{xg(a.next15.xg_for)}</span> for
                <span className="block"><span className="text-ink-2">{xg(a.next15.xg_against)}</span> against</span>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}

/** Actual cumulative xG over the horizon, ending in range bars: model as it was, model changed, similar matches. */
function RangeChart({ r, side }: { r: Counterfactual; side: Side }) {
  const W = 380, H = 112, P = { l: 4, r: 150, t: 10, b: 18 };
  const m = r.modelled[side].xg;
  const f = r.factual?.[side].xg;
  const a = r.analog_summary?.[side].xg;
  const max = Math.max(m.p90, f?.p90 ?? 0, a?.p90 ?? 0, ...r.series.map((d) => d.actual[side]), 0.2);
  const x = scaleLinear().domain([0, r.horizon_minutes]).range([P.l, W - P.r]);
  const y = scaleLinear().domain([0, max]).nice().range([H - P.b, P.t]);
  type D = (typeof r.series)[number];
  const act = line<D>().x((d) => x(d.offset_min)).y((d) => y(d.actual[side]));
  const legacy = r.series.every((d) => d.modelled)
    ? area<D>().x((d) => x(d.offset_min)).y0((d) => y(d.modelled![side].p10)).y1((d) => y(d.modelled![side].p90))(r.series)
    : null;
  const bar = (bx: number, b: { p10: number; p50: number; p90: number }, color: string, label: string) => (
    <g>
      <rect x={bx - 7} y={y(b.p90)} width={14} height={Math.max(y(b.p10) - y(b.p90), 2)} rx={7} fill={color} opacity={0.28} />
      <line x1={bx - 9} x2={bx + 9} y1={y(b.p50)} y2={y(b.p50)} stroke={color} strokeWidth={2.4} strokeLinecap="round" />
      <text x={bx} y={H - 3} textAnchor="middle" fontSize={9.5} fill="var(--ink-3)">{label}</text>
    </g>
  );
  const last = r.series[r.series.length - 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-3 w-full" role="img"
      aria-label={`What happened: ${xg(r.actual[side].xg)} xG.${f ? ` Model as it was ${xg(f.p10)} to ${xg(f.p90)}.` : ""} Model changed ${xg(m.p10)} to ${xg(m.p90)}${a ? `, similar matches ${xg(a.p10)} to ${xg(a.p90)}` : ""}.`}>
      <line x1={P.l} x2={W - 4} y1={y(0)} y2={y(0)} stroke="var(--axis)" />
      {legacy && <path d={legacy} fill="var(--ai)" opacity={0.14} />}
      <path d={act(r.series) ?? ""} fill="none" stroke={`var(--${side})`} strokeWidth={2.2} strokeLinecap="round" />
      {last && <circle cx={x(last.offset_min)} cy={y(last.actual[side])} r={3.5} fill={`var(--${side})`} stroke="var(--surface-2)" strokeWidth={2} />}
      <line x1={W - P.r + 12} x2={W - P.r + 12} y1={P.t} y2={H - P.b} stroke="var(--border-strong)" strokeDasharray="2 3" />
      {f && bar(W - P.r + 38, f, "var(--ink-3)", "As was")}
      {bar(W - P.r + 82, m, "var(--ai)", "Changed")}
      {a && bar(W - P.r + 126, a, "var(--ink-2)", "Similar")}
      <text x={P.l} y={H - 3} fontSize={9.5} fill="var(--ink-3)">{r.anchor.label}</text>
      <text x={W - P.r} y={H - 3} fontSize={9.5} fill="var(--ink-3)" textAnchor="end">+{r.horizon_minutes}'</text>
      <text x={P.l} y={P.t + 2} fontSize={9.5} fill="var(--ink-3)">What happened</text>
    </svg>
  );
}

function ShotBranch({ r }: { r: ShotAlternatives }) {
  const enter = useEnter();
  const best = r.options[0];
  const listed = r.options.slice(0, 5);
  const top = Math.max(...r.options.map((o) => o.value), r.shot.xg, 0.01);
  // Home attacks right, away attacks left in the API frame. Crop to the players
  // and the goal, padded, at least 4:3 so the panel stays short.
  const goalX = r.shot.team === "home" ? PITCH.L : 0;
  const xs = [r.shot.x, goalX, ...r.options.map((o) => o.x)];
  const ys = [r.shot.y, PITCH.W / 2 - 9, PITCH.W / 2 + 9, ...r.options.map((o) => o.y)];
  let x0 = Math.min(...xs) - 6, x1 = Math.max(...xs) + 6;
  let y0 = Math.min(...ys) - 5, y1 = Math.max(...ys) + 5;
  const minW = ((y1 - y0) * 4) / 3;
  if (x1 - x0 < minW) {
    const grow = minW - (x1 - x0);
    if (goalX === 0) x1 += grow;
    else x0 -= grow;
  }
  const minH = (x1 - x0) * 0.55;
  if (y1 - y0 < minH) {
    const c = (y0 + y1) / 2;
    y0 = c - minH / 2;
    y1 = c + minH / 2;
  }
  const vb = { x: x0, y: PITCH.W - y1, w: x1 - x0, h: y1 - y0 };
  const font = vb.w / 30;
  const surname = (n: string) => n.split(" ").slice(-1)[0];
  const headline =
    r.comparison === "pass_higher" && best ? `Passing to ${best.player} was the better bet.`
    : r.comparison === "shot_higher" ? "Shooting was the right call."
    : r.comparison === "similar" ? "It was a coin flip between shooting and passing."
    : "There was nobody to pass to.";
  const howOften = (p: number) =>
    p >= 0.85 ? "almost always" : p >= 0.65 ? "most of the time" : p >= 0.4 ? "about half the time" : p >= 0.2 ? "now and then" : "rarely";

  return (
    <motion.div exit={{ opacity: 0, transition: { duration: 0.12 } }} className="mt-4 space-y-3">
      <motion.div {...enter(0)} className="rounded-2xl bg-ai-soft px-4 py-3.5 ring-1 ring-[var(--ai-line)]">
        <p className="text-[12px] font-medium text-ai">What the model says</p>
        <p className="mt-0.5 text-balance text-[18px] font-semibold leading-snug tracking-[-0.01em] text-ink">{headline}</p>
        <p className="mt-1 text-pretty text-[13px] leading-[1.5] text-ink-2">
          Based on where every player stood when {r.shot.player} shot. The model assumes a clean first touch, so treat it as a rough guide.
        </p>
      </motion.div>

      <motion.dl {...enter(1)} className="grid grid-cols-2 gap-3">
        <div className="flex flex-col-reverse gap-1 rounded-2xl bg-surface-2 p-4 ring-1 ring-line">
          <dd className="text-[12.5px] leading-snug text-ink-3">Actually: {r.shot.outcome.toLowerCase()}</dd>
          <dd className="numeral text-[32px] leading-none text-ink">{pct(r.shot.xg)}</dd>
          <dt className="text-[12.5px] text-ink-3">Shooting: chance of a goal</dt>
        </div>
        <div className="flex flex-col-reverse gap-1 rounded-2xl bg-surface-2 p-4 ring-1 ring-[var(--ai-line)]">
          {best ? (
            <>
              <dd className="text-[12.5px] leading-snug text-ink-3">The pass gets there {howOften(best.p_complete)}</dd>
              <dd className="numeral text-[32px] leading-none text-ink">{pct(best.value)}</dd>
              <dt className="text-[12.5px] text-ai">Passing to {surname(best.player)}: chance of a goal</dt>
            </>
          ) : (
            <><dd className="text-[13px] text-ink-3">No teammates nearby</dd><dt className="text-[12.5px] text-ai">Passing</dt></>
          )}
        </div>
      </motion.dl>

      <motion.div {...enter(2)} className="overflow-hidden rounded-2xl ring-1 ring-line">
        <svg viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`} className="block w-full" role="img"
          aria-label={`${r.shot.player} shot from here. ${best ? `Best pass: ${best.player}.` : "No teammates in the frame."}`}>
          <PitchMarkings pad={40} padX={40} texture={false} lineWidth={0.3} />
          <line x1={r.shot.x} y1={sy(r.shot.y)} x2={goalX} y2={PITCH.W / 2} stroke={`var(--${r.shot.team})`} strokeWidth={0.45} strokeDasharray="1.2 1" opacity={0.9} />
          {listed.map((o, i) => (
            <line key={i} x1={r.shot.x} y1={sy(r.shot.y)} x2={o.x} y2={sy(o.y)}
              stroke={i === 0 ? "var(--ai)" : "var(--ink-2)"} strokeWidth={0.25 + 0.9 * (o.value / top)} opacity={i === 0 ? 1 : 0.45} strokeLinecap="round" />
          ))}
          {r.options.map((o, i) => (
            <g key={`p${i}`}>
              <circle cx={o.x} cy={sy(o.y)} r={1.25} fill={i === 0 ? "var(--ai)" : "var(--surface-4)"} stroke="var(--ink)" strokeWidth={0.2} />
              {i < 3 && (
                <text x={o.x + 1.8} y={sy(o.y) + font * 0.35} fontSize={font} fill="var(--ink)" stroke="var(--on-grass)" strokeWidth={font * 0.18} paintOrder="stroke">
                  {surname(o.player)}
                </text>
              )}
            </g>
          ))}
          <circle cx={r.shot.x} cy={sy(r.shot.y)} r={1.5} fill={`var(--${r.shot.team})`} stroke="var(--ink)" strokeWidth={0.25} />
        </svg>
        <p className="flex flex-wrap gap-x-4 gap-y-1 bg-surface-2 px-3.5 py-2 text-[12px] text-ink-3">
          <span><span className="mr-1.5 inline-block size-2 rounded-full align-middle" style={{ background: `var(--${r.shot.team})` }} aria-hidden />Shooter</span>
          <span><span className="mr-1.5 inline-block size-2 rounded-full bg-ai align-middle" aria-hidden />Best pass</span>
          <span>Thicker line = better option</span>
        </p>
      </motion.div>

      {listed.length > 0 && (
        <motion.div {...enter(3)}>
          <Details label="See every passing option">
            <table className="tabular w-full overflow-hidden rounded-xl bg-surface-2 text-[12.5px] ring-1 ring-line">
              <thead>
                <tr className="text-left text-[12px] text-ink-3">
                  <th className="px-3 py-2 font-normal">Teammate</th>
                  <th className="px-2 py-2 text-right font-normal">Pass arrives</th>
                  <th className="px-2 py-2 text-right font-normal">Then scores</th>
                  <th className="px-3 py-2 text-right font-normal">Overall</th>
                </tr>
              </thead>
              <tbody>
                {listed.map((o, i) => (
                  <tr key={i} className="border-t border-line">
                    <td className={`max-w-0 truncate px-3 py-2 font-medium ${i === 0 ? "text-ai" : "text-ink"}`}>{o.player}</td>
                    <td className="px-2 py-2 text-right text-ink-2">{pct(o.p_complete)}</td>
                    <td className="px-2 py-2 text-right text-ink-2">{pct(Math.max(o.xg_if_shot, o.xt))}</td>
                    <td className="px-3 py-2 text-right font-semibold text-ink">{pct(o.value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="px-1 text-pretty text-[12px] leading-[1.5] text-ink-3">
              "Then scores" is the better of shooting straight away or keeping the move going from that spot. Overall = pass arrives × then scores.
              {" "}{r.model.name}, trained on <span className="tabular">{r.model.trained_passes.toLocaleString("en-GB")}</span> passes from <span className="tabular">{r.model.trained_matches}</span> matches; knowing where defenders stand lifts its accuracy score (AUC) from <span className="tabular">{r.model.baseline_auc.toFixed(2)}</span> to <span className="tabular">{r.model.auc.toFixed(2)}</span>.
            </p>
          </Details>
        </motion.div>
      )}
      <p className="text-pretty text-[12px] leading-[1.55] text-ink-3">{r.caveat}</p>
    </motion.div>
  );
}
