import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, MotionConfig } from "motion/react";
import { CaretDown } from "@phosphor-icons/react";
import { scaleLinear, scaleLog } from "d3-scale";
import { api } from "../../api/client";
import type { LeaderboardRow, PlayerProfile } from "../../api/types";
import { usePlayerUi } from "../../store/ui";
import { Line, RevealImage, Stagger } from "../ui/motion";
import { SiteHeader } from "../ui/SiteHeader";
import { useSize } from "../ui/useSize";
import { initials } from "../ui/focusTrap";
import { LoadError, PageFooter } from "../ui/PageFooter";
import { eur } from "../../lib/format";
import { pickUnderrated } from "./underrated";

const EASE = [0.22, 1, 0.36, 1] as const;
/** [api key, control label, chart label] */
const METRICS: [string, string, string][] = [
  ["vaep_per90", "Value added per 90", "Value added per 90"],
  ["xg", "Expected goals", "Expected goals"],
  ["prog_per90", "Progression per 90", "Progression per 90"],
];
const COMPS: [string, string, string][] = [
  ["1. Bundesliga", "2015/2016", "Bundesliga 2015/16"],
  ["1. Bundesliga", "2023/2024", "Bundesliga 2023/24"],
  ["La Liga", "2015/2016", "La Liga 2015/16"],
  ["Premier League", "2015/2016", "Premier League 2015/16"],
  ["FIFA World Cup", "2022", "World Cup 2022"],
  ["UEFA Euro", "2024", "Euro 2024"],
  ["Copa America", "2024", "Copa América 2024"],
];

// profiles carry the photos; cache them so switching back is instant
const profiles = new Map<number, Promise<PlayerProfile | null>>();
const profile = (id: number) => {
  if (!profiles.has(id)) profiles.set(id, api.player(id).catch(() => null));
  return profiles.get(id)!;
};

/** Value added vs market value: who did the market underrate? */
export function LeaderboardPage() {
  const [metric, setMetric] = useState("vaep_per90");
  const [comp, setComp] = useState(0);
  const [data, setData] = useState<{ key: string; rows: LeaderboardRow[] } | null>(null);
  const [err, setErr] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const openPlayer = usePlayerUi((s) => s.openPlayer);
  const scroller = useRef<HTMLDivElement>(null);
  const key = `${metric}|${comp}`;

  useEffect(() => {
    let live = true;
    const [competition, season] = COMPS[comp];
    const tournament = !competition.includes("Bundesliga") && !competition.includes("Liga") && !competition.includes("Premier");
    api.leaderboard({ metric, min_minutes: tournament ? 270 : 900, competition, season })
      .then((r) => { if (live) { setData({ key, rows: r.rows }); setErr(false); } })
      .catch(() => live && setErr(true));
    return () => { live = false; };
  }, [metric, comp, key, attempt]);

  const rows = useMemo(() => data?.rows ?? [], [data]);
  const stale = data != null && data.key !== key;
  const underrated = useMemo(() => pickUnderrated(rows), [rows]);
  const [, label, chartLabel] = METRICS.find(([k]) => k === metric) ?? METRICS[0];
  const compLabel = COMPS[comp][2];
  const retry = useCallback(() => { setErr(false); setAttempt((a) => a + 1); }, []);

  return (
    <MotionConfig reducedMotion="user">
      <div ref={scroller} className="scroll-thin h-full overflow-y-auto">
        <a href="#board" className="sr-only rounded-full bg-ink px-4 py-2 text-[13px] font-medium text-bg focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-30">
          Skip to the leaderboard
        </a>
        <SiteHeader scroller={scroller} />

        <main>
          <section className="mx-auto max-w-[1280px] px-5 pb-12 pt-8 md:px-8 lg:pt-14">
            <Stagger onMount>
              <Line n={1} as="h1" className="max-w-[18ch] text-balance text-[38px] font-semibold leading-[1.06] tracking-[-0.04em] text-ink md:text-[48px]">
                Who did the market underrate?
              </Line>
              <Line n={2} as="p" className="mt-6 max-w-[58ch] text-pretty text-[17px] leading-[1.6] text-ink-2">
                Every player with enough minutes (900 in a league season, 270 at a tournament), ranked by the value our models say they added, against what the transfer market said they were worth at the time.
              </Line>
              <Line n={3} as="div" className="mt-9">
                <div className="flex flex-wrap items-center gap-3">
                  <div role="group" aria-label="Metric" className="-mx-5 max-w-[calc(100%+40px)] overflow-x-auto px-5 sm:mx-0 sm:max-w-full sm:px-0">
                    <div className="flex w-max gap-1 rounded-full bg-surface-1 p-1 ring-1 ring-line">
                      {METRICS.map(([k, l]) => {
                        const on = k === metric;
                        return (
                          <button key={k} type="button" aria-pressed={on} onClick={() => setMetric(k)}
                            className={`relative shrink-0 whitespace-nowrap rounded-full px-4 py-1.5 text-[13.5px] font-medium transition-[color,transform] duration-[250ms] active:scale-[0.97] ${on ? "text-bg" : "text-ink-3 hover:text-ink"}`}>
                            {on && <motion.span layoutId="metric-pill" className="absolute inset-0 rounded-full bg-ink" transition={{ duration: 0.25, ease: EASE }} />}
                            <span className="relative">{l}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  <label className="relative inline-flex items-center">
                    <span className="sr-only">Competition</span>
                    <select value={comp} onChange={(e) => setComp(Number(e.target.value))}
                      className="cursor-pointer appearance-none rounded-full bg-surface-1 py-2 pl-4 pr-10 text-base font-medium text-ink ring-1 ring-line transition-[box-shadow,background-color] duration-150 hover:bg-surface-2 hover:ring-line-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-ink sm:text-[13.5px]">
                      {COMPS.map(([, , l], i) => <option key={l} value={i}>{l}</option>)}
                    </select>
                    <CaretDown size={14} weight="bold" className="pointer-events-none absolute right-4 text-ink-3" aria-hidden />
                  </label>
                  <p role="status" className="tabular text-[13.5px] text-ink-3 sm:ml-auto">
                    {data && !stale ? `${rows.length} players in ${compLabel}` : <span className="sr-only">Loading players</span>}
                  </p>
                </div>
              </Line>
            </Stagger>
          </section>

          <section id="board" aria-label={`${label} against market value, ${compLabel}`} className="mx-auto max-w-[1280px] scroll-mt-20 px-5 md:px-8">
            {err ? <LoadError title="Unable to load the leaderboard" onRetry={retry} /> : (
              <div className={`grid grid-cols-1 gap-3 transition-opacity duration-200 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)] ${stale ? "opacity-60" : "opacity-100"}`} aria-busy={stale || !data}>
                <div className="flex min-w-0 flex-col rounded-[20px] bg-surface-1 p-6 ring-1 ring-line md:p-8">
                  <h2 className="text-[19px] font-semibold tracking-[-0.015em] text-ink">{label} against market value</h2>
                  <p className="mt-1.5 text-[14px] text-ink-3">Top left is underrated: high output, low price. Select a dot to open the profile.</p>
                  <div className="mt-6 min-h-[340px] flex-1 sm:min-h-[440px]">
                    {!data ? <div className="h-full min-h-[340px] rounded-2xl bg-surface-2 motion-safe:animate-pulse" aria-hidden />
                      : <Scatter key={data.key} rows={rows} label={chartLabel} highlight={new Set(underrated.map((r) => r.player_id + r.season))} onPick={openPlayer} />}
                  </div>
                </div>
                <Underrated rows={underrated} ready={!!data} label={label} compLabel={compLabel} dataKey={data?.key ?? ""} />
              </div>
            )}
          </section>
        </main>

        <PageFooter />
      </div>
    </MotionConfig>
  );
}

function Underrated({ rows, ready, label, compLabel, dataKey }: { rows: LeaderboardRow[]; ready: boolean; label: string; compLabel: string; dataKey: string }) {
  const openPlayer = usePlayerUi((s) => s.openPlayer);
  const [photos, setPhotos] = useState<Record<number, PlayerProfile | null>>({});

  useEffect(() => {
    let live = true;
    Promise.all(rows.map((r) => profile(r.player_id).then((p) => [r.player_id, p] as const))).then((ps) => {
      if (live) setPhotos((prev) => ({ ...prev, ...Object.fromEntries(ps) }));
    });
    return () => { live = false; };
  }, [rows]);

  const credits = rows.map((r) => photos[r.player_id]).filter((p): p is PlayerProfile => !!p?.photo_url && !!p.photo_credit);

  return (
    <div className="flex min-w-0 flex-col rounded-[20px] bg-surface-1 p-6 ring-1 ring-line md:p-8">
      <h2 className="text-[19px] font-semibold tracking-[-0.015em] text-ink">Most underrated</h2>
      <p className="mt-1.5 text-[14px] text-ink-3">{label}, set against market value.</p>

      {!ready ? (
        <ul className="mt-5 space-y-1" aria-hidden>
          {Array.from({ length: 8 }, (_, i) => (
            <li key={i} className="flex items-center gap-3 px-2 py-2">
              <span className="size-11 shrink-0 rounded-xl bg-surface-2 motion-safe:animate-pulse" />
              <span className="flex-1 space-y-2"><span className="block h-3.5 w-32 rounded-full bg-surface-2 motion-safe:animate-pulse" /><span className="block h-3 w-20 rounded-full bg-surface-2 motion-safe:animate-pulse" /></span>
            </li>
          ))}
        </ul>
      ) : rows.length === 0 ? (
        <div className="mt-5 rounded-2xl bg-surface-2 px-5 py-10 text-center">
          <p className="text-[15px] font-medium text-ink">No standouts in {compLabel}</p>
          <p className="mt-1.5 text-[14px] text-ink-3">No player with enough minutes ranks well above their market value here. Try another competition.</p>
        </div>
      ) : (
        <ol className="-mx-2 mt-5 space-y-0.5">
          {rows.map((r, i) => {
            const p = photos[r.player_id];
            const name = r.short_name || r.name;
            return (
              <motion.li key={`${dataKey}-${r.player_id}${r.season}`}
                initial={{ opacity: 0, y: 6, filter: "blur(2px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                transition={{ duration: 0.3, delay: Math.min(i * 0.04, 0.28), ease: EASE }}>
                <button type="button" onClick={() => openPlayer(r.player_id)} aria-label={`${i + 1}. ${name}, ${r.team}. Open profile`}
                  className="group flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left transition-[background-color,transform] duration-150 ease-out hover:bg-surface-2 active:scale-[0.98]">
                  <span className="numeral w-5 shrink-0 text-right text-[17px] text-ink-4">{i + 1}</span>
                  <span className="relative size-11 shrink-0 overflow-hidden rounded-xl">
                    {p === undefined ? <span className="block size-full bg-surface-3 motion-safe:animate-pulse" /> : (
                      <RevealImage key={p?.photo_url ?? "none"} src={p?.photo_url ?? null} alt=""
                        className="size-full" fallback={<span className="grid size-full place-items-center bg-surface-3 text-[14px] font-semibold text-ink-3">{initials(name)}</span>} />
                    )}
                    <span className="pointer-events-none absolute inset-0 rounded-xl outline outline-1 -outline-offset-1 outline-white/10" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[14.5px] font-medium text-ink">{name}</span>
                    <span className="block truncate text-[12.5px] text-ink-3">{r.team}</span>
                  </span>
                  <span className="shrink-0 text-right">
                    <span className="tabular block text-[14px] font-medium text-ink">{r.value.toFixed(2)}</span>
                    <span className="tabular block text-[12.5px] text-ink-3">{eur(r.market_value_eur)}</span>
                  </span>
                </button>
              </motion.li>
            );
          })}
        </ol>
      )}

      <p className="mt-auto pt-6 text-pretty text-[12.5px] leading-[1.6] text-ink-3">
        Among the top 40% on {label.toLowerCase()}, the players who rank furthest above their market value. Market values from Transfermarkt (CC0 dataset), at the end of that season.
      </p>
      {credits.length > 0 && (
        <p className="mt-3 text-[12px] leading-[1.6] text-ink-4">
          Photos from Wikimedia Commons: {credits.map((p, i) => (
            <span key={p.player_id}>{p.short_name} by {p.photo_credit!.replace(/\s*\(talk\).*$/, "")} ({p.photo_license}){i < credits.length - 1 ? ", " : "."}</span>
          ))}
        </p>
      )}
    </div>
  );
}

function Scatter({ rows, label, highlight, onPick }: { rows: LeaderboardRow[]; label: string; highlight: Set<string>; onPick: (id: number) => void }) {
  const [ref, { width, height }] = useSize<HTMLDivElement>();
  const [hover, setHover] = useState<LeaderboardRow | null>(null);
  const [last, setLast] = useState<LeaderboardRow | null>(null);
  if (hover && hover !== last) setLast(hover);
  const shown = hover ?? last;
  // fills the panel, which stretches to the height of the list beside it
  const H = height || 440;
  const P = { l: 48, r: 16, t: 26, b: 40 };
  const pts = rows.filter((r) => r.market_value_eur && r.market_value_eur > 0);

  if (!pts.length) {
    return (
      <div ref={ref} className="grid h-full min-h-[340px] place-items-center rounded-2xl bg-surface-2 px-6 text-center">
        <div>
          <p className="text-[15px] font-medium text-ink">No players to plot</p>
          <p className="mt-1.5 text-[14px] text-ink-3">None of these players has a market value on record. Try another competition.</p>
        </div>
      </div>
    );
  }
  const vals = pts.map((r) => r.market_value_eur!);
  const x = scaleLog().domain([Math.min(...vals) * 0.8, Math.max(...vals) * 1.2]).range([P.l, Math.max(P.l + 1, width - P.r)]);
  const y = scaleLinear().domain([Math.min(0, ...pts.map((r) => r.value)), Math.max(...pts.map((r) => r.value)) * 1.08]).nice(5).range([H - P.b, P.t]);
  const xt = [1e5, 1e6, 1e7, 1e8].filter((t) => t >= x.domain()[0] && t <= x.domain()[1]);
  const id = (r: LeaderboardRow) => r.player_id + r.season;
  // highlighted dots draw last so they sit on top
  const ordered = [...pts].sort((a, b) => Number(highlight.has(id(a))) - Number(highlight.has(id(b))));
  const tipBelow = shown ? y(shown.value) < 90 : false;

  return (
    <div ref={ref} className="relative h-full min-h-[340px]">
      {width > 0 && (
        <motion.svg width={width} height={H} className="block overflow-visible" role="img"
          aria-label={`${label} against market value for ${pts.length} players. Highlighted: ${pts.filter((r) => highlight.has(id(r))).map((r) => r.short_name || r.name).join(", ")}.`}
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3, ease: EASE }}>
          {y.ticks(5).map((t) => (
            <g key={t}>
              <line x1={P.l} x2={width - P.r} y1={y(t)} y2={y(t)} stroke="var(--grid)" />
              <text x={P.l - 10} y={y(t) + 4} fontSize={11} fill="var(--ink-3)" textAnchor="end" className="tabular">{t.toFixed(y.domain()[1] >= 5 ? 0 : 2)}</text>
            </g>
          ))}
          {xt.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={P.t} y2={H - P.b} stroke="var(--grid)" />
              <text x={x(t)} y={H - P.b + 18} fontSize={11} fill="var(--ink-3)" textAnchor="middle" className="tabular">{eur(t)}</text>
            </g>
          ))}
          <text x={width - P.r} y={H - 4} fontSize={11.5} fill="var(--ink-2)" textAnchor="end">Market value, log scale</text>
          <text x={P.l} y={P.t - 12} fontSize={11.5} fill="var(--ink-2)">{label}</text>
          {ordered.map((r) => {
            const hl = highlight.has(id(r));
            const on = hover === r;
            return (
              <g key={id(r)} style={{ cursor: "pointer" }} onClick={() => onPick(r.player_id)}
                onPointerEnter={() => setHover(r)} onPointerLeave={() => setHover(null)}>
                <circle cx={x(r.market_value_eur!)} cy={y(r.value)} r={12} fill="transparent" />
                <circle cx={x(r.market_value_eur!)} cy={y(r.value)} r={on ? 7 : hl ? 6 : 4.5}
                  fill={hl || on ? "var(--ink)" : "var(--ink-3)"} fillOpacity={hl || on ? 1 : 0.5}
                  stroke="var(--surface-1)" strokeWidth={2} />
              </g>
            );
          })}
          {(() => {
            // label the highlighted players, skipping any label that would collide with one already placed
            const placed: { x: number; y: number }[] = [];
            return pts.filter((r) => highlight.has(id(r))).map((r) => {
              const lx = x(r.market_value_eur!) + 10, ly = y(r.value) + 4;
              if (lx > width - 60 || placed.some((q) => Math.abs(q.y - ly) < 15 && Math.abs(q.x - lx) < 96)) return null;
              placed.push({ x: lx, y: ly });
              return <text key={`l-${id(r)}`} x={lx} y={ly} fontSize={11.5} fill="var(--ink-2)" pointerEvents="none">{r.short_name}</text>;
            });
          })()}
        </motion.svg>
      )}
      {shown && width > 0 && (
        <div className="pointer-events-none absolute z-10 w-0"
          style={{ left: Math.min(Math.max(x(shown.market_value_eur!), 120), width - 120), top: tipBelow ? y(shown.value) + 16 : y(shown.value) - 14, transform: tipBelow ? undefined : "translateY(-100%)" }}>
          <div data-open={hover != null}
            className="t-tt relative w-max max-w-[240px] rounded-lg bg-surface-3 px-3 py-2 text-[12px] shadow-[0_8px_24px_-8px_rgba(0,0,0,0.6)] ring-1 ring-line-strong">
            <p className="font-medium text-ink">{shown.short_name || shown.name}</p>
            <p className="text-ink-3">{shown.team}</p>
            <p className="tabular mt-1 text-ink-2"><span className="font-medium text-ink">{shown.value.toFixed(2)}</span> {label.toLowerCase()}, {eur(shown.market_value_eur)}, {Math.round(shown.minutes).toLocaleString("en-GB")} minutes</p>
          </div>
        </div>
      )}
    </div>
  );
}
