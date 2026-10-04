import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { AnimatePresence, motion } from "motion/react";
import { scaleLinear, scaleTime } from "d3-scale";
import { area, curveStepAfter, line } from "d3-shape";
import { api } from "../../api/client";
import type { LeaderboardRow, PlayerProfile } from "../../api/types";
import { usePlayerUi } from "../../store/ui";
import { eur } from "../../lib/format";
import { minMinutes, pickUnderrated } from "../players/underrated";
import { LearnChevron, Line, RevealImage, Stagger, Tilt } from "../ui/motion";
import { useSize } from "../ui/useSize";

const COMPS = [
  { key: "wc22", competition: "FIFA World Cup", season: "2022", label: "World Cup 2022", where: "at the World Cup" },
  { key: "euro24", competition: "UEFA Euro", season: "2024", label: "Euro 2024", where: "at Euro 2024" },
  { key: "copa24", competition: "Copa America", season: "2024", label: "Copa América 2024", where: "at the Copa América" },
] as const;
type CompKey = (typeof COMPS)[number]["key"];

const EASE = [0.22, 1, 0.36, 1] as const;
const ordinal = (n: number) => {
  const r = Math.round(n);
  const s = r % 100 >= 11 && r % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[r % 10] ?? "th";
  return `${r}${s}`;
};

// module caches so switching tabs back is instant
const boards = new Map<CompKey, Promise<LeaderboardRow[]>>();
const profiles = new Map<number, Promise<PlayerProfile | null>>();
const board = (key: CompKey) => {
  if (!boards.has(key)) {
    const c = COMPS.find((x) => x.key === key)!;
    boards.set(key, api.leaderboard({ metric: "vaep_per90", min_minutes: minMinutes(c.competition), competition: c.competition, season: c.season }).then((r) => r.rows));
  }
  return boards.get(key)!;
};
const profile = (id: number) => {
  if (!profiles.has(id)) profiles.set(id, api.player(id).catch(() => null));
  return profiles.get(id)!;
};

interface Pick { row: LeaderboardRow; p: PlayerProfile | null }

/** Landing section: the most underrated players of a tournament, with photos, rank gap and price history. */
export function PlayersSection() {
  const [comp, setComp] = useState<CompKey>("wc22");
  const [data, setData] = useState<{ key: CompKey; picks: Pick[]; maxRank: number } | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let live = true;
    board(comp).then(async (rows) => {
      const top = pickUnderrated(rows, 7);
      const ps = await Promise.all(top.map((r) => profile(r.player_id)));
      const maxRank = Math.max(...rows.map((r) => Math.max(r.metric_rank, r.value_rank ?? 0)));
      if (live) { setData({ key: comp, picks: top.map((row, i) => ({ row, p: ps[i] })), maxRank }); setErr(false); }
    }).catch(() => live && setErr(true));
    return () => { live = false; };
  }, [comp]);

  const c = COMPS.find((x) => x.key === comp)!;
  const ready = data?.key === comp ? data : null;
  const credits = (ready?.picks ?? []).filter((x) => x.p?.photo_url && x.p.photo_credit);

  return (
    <section aria-labelledby="players-title" className="mx-auto max-w-[1280px] px-5 pt-28 md:px-8">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <Stagger>
          <Line n={1} as="h2" className="text-[30px] font-semibold leading-[1.1] tracking-[-0.03em] text-ink md:text-[38px]">
            <span id="players-title">The players the market missed</span>
          </Line>
          <Line n={2} as="p" className="mt-3 max-w-[60ch] text-pretty text-[15.5px] leading-[1.6] text-ink-3">
            Ranked by value added per 90 minutes, set against what Transfermarkt said they were worth.
          </Line>
        </Stagger>
        <div role="group" aria-label="Tournament" className="-mx-5 flex shrink-0 gap-1 overflow-x-auto px-5 lg:mx-0 lg:px-0">
          <div className="flex gap-1 rounded-full bg-surface-1 p-1 ring-1 ring-line">
            {COMPS.map((x) => {
              const on = x.key === comp;
              return (
                <button key={x.key} type="button" aria-pressed={on} onClick={() => setComp(x.key)}
                  className={`relative shrink-0 whitespace-nowrap rounded-full px-4 py-1.5 text-[13.5px] font-medium transition-colors duration-[250ms] ${on ? "text-bg" : "text-ink-3 hover:text-ink"}`}>
                  {on && <motion.span layoutId="players-pill" className="absolute inset-0 rounded-full bg-ink" transition={{ duration: 0.25, ease: EASE }} />}
                  <span className="relative">{x.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {err ? (
        <div className="mt-10 rounded-[20px] px-6 py-14 text-center ring-1 ring-line">
          <p className="text-[15px] font-medium text-ink">Unable to load player rankings</p>
          <p className="mt-1.5 text-[14px] text-ink-3">The full leaderboard may still work.</p>
          <Link to="/players" className="t-learn mt-4 inline-flex items-center gap-1 text-[14px] font-medium text-ink">Open the leaderboard<LearnChevron /></Link>
        </div>
      ) : (
        <div className="mt-10 grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.div key={ready ? `f-${comp}` : "f-skel"} className="min-w-0"
              initial={{ opacity: 0, filter: "blur(2px)", y: 6 }} animate={{ opacity: 1, filter: "blur(0px)", y: 0 }}
              exit={{ opacity: 0, filter: "blur(2px)", transition: { duration: 0.15, ease: "easeOut" } }}
              transition={{ duration: 0.4, ease: EASE }}>
              {ready ? <Featured pick={ready.picks[0]} maxRank={ready.maxRank} where={c.where} /> : <FeaturedSkeleton />}
            </motion.div>
          </AnimatePresence>
          <ol className="grid grid-cols-2 gap-3 sm:grid-cols-3" aria-label={`More underrated players ${c.where}`}>
            {(ready ? ready.picks.slice(1, 7) : Array.from({ length: 6 }, () => null)).map((pick, i) => (
              <motion.li key={pick ? `${comp}-${pick.row.player_id}` : `skel-${i}`}
                initial={{ opacity: 0, y: 8, filter: "blur(2px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                transition={{ duration: 0.4, delay: 0.05 + i * 0.04, ease: EASE }}>
                {pick ? <Tile pick={pick} rank={i + 2} /> : <div className="aspect-[4/5] rounded-2xl bg-surface-1 ring-1 ring-line motion-safe:animate-pulse" />}
              </motion.li>
            ))}
          </ol>
        </div>
      )}

      <div className="mt-6 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <Link to="/players" className="t-learn inline-flex shrink-0 items-center gap-1 text-[14.5px] font-medium text-ink transition-colors duration-150 hover:text-ink-2">
          See the full leaderboard<LearnChevron />
        </Link>
        {credits.length > 0 && (
          <p className="max-w-[80ch] text-[12px] leading-[1.6] text-ink-3 md:text-right">
            Photos from Wikimedia Commons: {credits.map((x, i) => (
              <span key={x.row.player_id}>{x.p!.short_name} by {x.p!.photo_credit!.replace(/\s*\(talk\).*$/, "")} ({x.p!.photo_license}){i < credits.length - 1 ? ", " : "."}</span>
            ))}
          </p>
        )}
      </div>
    </section>
  );
}

function Initials({ name, big }: { name: string; big?: boolean }) {
  const init = name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2);
  return <span className={`grid h-full w-full place-items-center bg-surface-3 font-semibold text-ink-3 ${big ? "text-[56px]" : "text-[28px]"}`}>{init}</span>;
}

function Featured({ pick, maxRank, where }: { pick: Pick; maxRank: number; where: string }) {
  const openPlayer = usePlayerUi((s) => s.openPlayer);
  const { row, p } = pick;
  const name = row.short_name || row.name;
  return (
    <article className="grid h-full grid-cols-1 overflow-hidden rounded-[20px] bg-surface-1 ring-1 ring-line sm:grid-cols-[minmax(0,0.85fr)_minmax(0,1fr)]">
      <Tilt max={6} className="sm:h-full" cardClassName="h-full">
        <button type="button" onClick={() => openPlayer(row.player_id)} aria-label={`Open ${name}'s profile`}
          className="block aspect-[4/3] h-full w-full sm:aspect-auto sm:min-h-[400px]">
          <RevealImage key={p?.photo_url ?? row.player_id} src={p?.photo_url ?? null} alt={name} className="h-full w-full outline outline-1 -outline-offset-1 outline-white/10" fallback={<Initials name={name} big />} />
        </button>
      </Tilt>
      <div className="flex min-w-0 flex-col p-6 md:p-8">
        <p className="text-[13.5px] font-medium text-ink-3">Most underrated {where}</p>
        <h3 className="mt-2 text-[30px] font-semibold leading-[1.1] tracking-[-0.03em] text-ink">{name}</h3>
        <p className="mt-1.5 text-[14.5px] text-ink-2">{[row.team, p?.position].filter(Boolean).join(", ")}</p>

        <dl className="mt-7 grid grid-cols-2 gap-4">
          <div className="flex flex-col-reverse justify-end gap-1">
            <dt className="text-[13px] text-ink-3">Value added per 90</dt>
            <dd className="numeral text-[34px] leading-none text-ink">{row.value.toFixed(2)}</dd>
          </div>
          <div className="flex flex-col-reverse justify-end gap-1">
            <dt className="text-[13px] text-ink-3">Market value then</dt>
            <dd className="numeral text-[34px] leading-none text-ink-2">{eur(row.market_value_eur)}</dd>
          </div>
        </dl>

        <RankGap perf={row.metric_rank} price={row.value_rank} maxRank={maxRank} />
        {p && p.valuations.length > 1 && <ValueHistory p={p} />}

        <button type="button" onClick={() => openPlayer(row.player_id)}
          className="t-learn mt-auto inline-flex items-center gap-1 self-start pt-7 text-[14.5px] font-medium text-ink transition-colors duration-150 hover:text-ink-2">
          Open profile<LearnChevron />
        </button>
      </div>
    </article>
  );
}

/** Dumbbell on one rank axis: where he ranks for output vs where the market priced him. */
function RankGap({ perf, price, maxRank }: { perf: number; price: number | null; maxRank: number }) {
  const [ref, { width }] = useSize<HTMLDivElement>();
  if (price == null) return null;
  const x = scaleLinear().domain([1, maxRank]).range([6, Math.max(7, width - 6)]);
  return (
    <div className="mt-7">
      <div ref={ref} className="relative h-6">
        {width > 0 && (
          <svg width={width} height={24} className="block overflow-visible" role="img"
            aria-label={`Ranked ${ordinal(perf)} for value added and ${ordinal(price)} by market value`}>
            <line x1={x(1)} x2={x(maxRank)} y1={12} y2={12} stroke="var(--axis)" strokeWidth={1} />
            <motion.line x1={x(perf)} y1={12} y2={12} stroke="var(--ink-3)" strokeWidth={2}
              initial={{ x2: x(perf) }} whileInView={{ x2: x(price) }} viewport={{ once: true }} transition={{ duration: 0.9, delay: 0.2, ease: EASE }} />
            <circle cx={x(perf)} cy={12} r={6} fill="var(--ink)" stroke="var(--surface-1)" strokeWidth={2} />
            <motion.circle cy={12} r={5} fill="var(--surface-1)" stroke="var(--ink-2)" strokeWidth={2}
              initial={{ cx: x(perf), opacity: 0 }} whileInView={{ cx: x(price), opacity: 1 }} viewport={{ once: true }} transition={{ duration: 0.9, delay: 0.2, ease: EASE }} />
          </svg>
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[12.5px] text-ink-3">
        <span className="flex items-center gap-2"><span className="size-2.5 rounded-full bg-ink" />{ordinal(perf)} for value added</span>
        <span className="flex items-center gap-2"><span className="size-2.5 rounded-full border-2 border-ink-2" />{ordinal(price)} by market value</span>
      </div>
    </div>
  );
}

/** Transfermarkt valuation history as a step line that draws on. */
function ValueHistory({ p }: { p: PlayerProfile }) {
  const [ref, { width }] = useSize<HTMLDivElement>();
  const H = 56;
  const pts = useMemo(() => p.valuations.map((v) => ({ d: new Date(v.date), v: v.value_eur })), [p]);
  if (pts.length < 2) return null;
  const x = scaleTime().domain([pts[0].d, pts[pts.length - 1].d]).range([0, width]);
  const y = scaleLinear().domain([0, Math.max(...pts.map((q) => q.v))]).range([H - 2, 4]);
  const path = line<(typeof pts)[number]>().x((q) => x(q.d)).y((q) => y(q.v)).curve(curveStepAfter)(pts) ?? "";
  const fill = area<(typeof pts)[number]>().x((q) => x(q.d)).y0(H).y1((q) => y(q.v)).curve(curveStepAfter)(pts) ?? "";
  const peak = Math.max(...pts.map((q) => q.v));
  return (
    <div className="mt-7">
      <div className="mb-2 flex items-baseline justify-between text-[12.5px] text-ink-3">
        <span>Market value, {pts[0].d.getFullYear()} to {pts[pts.length - 1].d.getFullYear()}</span>
        <span className="tabular">Peak {eur(peak)}</span>
      </div>
      <div ref={ref} style={{ height: H }}>
        {width > 0 && (
          <svg width={width} height={H} className="block" aria-hidden>
            <motion.path d={fill} fill="var(--ink)" initial={{ opacity: 0 }} whileInView={{ opacity: 0.06 }} viewport={{ once: true }} transition={{ duration: 0.6, delay: 0.5 }} />
            <motion.path d={path} fill="none" stroke="var(--ink-2)" strokeWidth={1.5} strokeLinejoin="round"
              initial={{ pathLength: 0 }} whileInView={{ pathLength: 1 }} viewport={{ once: true }} transition={{ duration: 1.1, ease: EASE }} />
          </svg>
        )}
      </div>
    </div>
  );
}

function Tile({ pick, rank }: { pick: Pick; rank: number }) {
  const openPlayer = usePlayerUi((s) => s.openPlayer);
  const { row, p } = pick;
  const name = row.short_name || row.name;
  return (
    <button type="button" onClick={() => openPlayer(row.player_id)} aria-label={`${rank}. ${name}, ${row.team}. Open profile`}
      className="group block w-full text-left transition-transform duration-150 ease-out active:scale-[0.97]">
      <Tilt max={10} cardClassName="aspect-[4/5] rounded-2xl ring-1 ring-line">
        <RevealImage key={p?.photo_url ?? row.player_id} src={p?.photo_url ?? null} alt="" className="h-full w-full" fallback={<Initials name={name} />} />
        <span className="pointer-events-none absolute inset-0 rounded-2xl outline outline-1 -outline-offset-1 outline-white/10" />
      </Tilt>
      <span className="mt-3 block px-0.5">
        <span className="flex items-baseline gap-2">
          <span className="numeral text-[15px] text-ink-4">{rank}</span>
          <span className="truncate text-[14.5px] font-medium text-ink transition-colors duration-150 group-hover:text-ink-2">{name}</span>
        </span>
        <span className="mt-0.5 flex items-baseline justify-between gap-2 text-[12.5px] text-ink-3">
          <span className="truncate">{row.team}</span>
          <span className="tabular shrink-0">{row.value.toFixed(2)} <span className="text-ink-4">for</span> {eur(row.market_value_eur)}</span>
        </span>
      </span>
    </button>
  );
}

function FeaturedSkeleton() {
  return (
    <div className="grid h-full min-h-[400px] grid-cols-1 overflow-hidden rounded-[20px] bg-surface-1 ring-1 ring-line sm:grid-cols-[minmax(0,0.85fr)_minmax(0,1fr)]" aria-hidden>
      <div className="aspect-[4/3] bg-surface-2 motion-safe:animate-pulse sm:aspect-auto" />
      <div className="space-y-4 p-8">
        <div className="h-4 w-40 rounded bg-surface-2 motion-safe:animate-pulse" />
        <div className="h-8 w-56 rounded bg-surface-2 motion-safe:animate-pulse" />
        <div className="h-4 w-32 rounded bg-surface-2 motion-safe:animate-pulse" />
      </div>
    </div>
  );
}
