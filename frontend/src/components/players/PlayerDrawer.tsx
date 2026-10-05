import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { X } from "@phosphor-icons/react";
import { scaleLinear, scaleTime } from "d3-scale";
import { area, line, curveStepAfter } from "d3-shape";
import { api } from "../../api/client";
import type { PlayerProfile } from "../../api/types";
import { useMatch } from "../../store/match";
import { usePlayerUi } from "../../store/ui";
import { PitchMarkings } from "../pitch/PitchMarkings";
import { PITCH } from "../pitch/geometry";
import { RevealImage } from "../ui/motion";
import { useSize } from "../ui/useSize";
import { initials, trapTab } from "../ui/focusTrap";
import { eur } from "../../lib/format";

const SOURCE_NAME: Record<string, string> = { transfermarkt: "Transfermarkt", wikidata: "Wikidata", statsbomb: "StatsBomb" };
const FOOT: Record<string, string> = { left: "Left foot", right: "Right foot", both: "Both feet" };
const DRAWER_EASE = [0.32, 0.72, 0, 1] as const;
const EASE = [0.22, 1, 0.36, 1] as const;
const monthFmt = new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric" });


/** Slide-over player profile; open it from anywhere with usePlayerUi().openPlayer(id). */
export function PlayerDrawer() {
  const playerId = usePlayerUi((s) => s.playerId);
  const openPlayer = usePlayerUi((s) => s.openPlayer);
  const matchId = useMatch((s) => s.matchId);
  const [p, setP] = useState<PlayerProfile | null>(null);
  const [err, setErr] = useState(false);
  const reduce = useReducedMotion();
  const panel = useRef<HTMLElement>(null);
  const closeBtn = useRef<HTMLButtonElement>(null);
  const open = playerId != null;

  useEffect(() => {
    if (playerId == null) return;
    let live = true;
    setP(null);
    setErr(false);
    api.player(playerId, matchId ?? undefined).then((r) => live && setP(r)).catch(() => live && setErr(true));
    return () => { live = false; };
  }, [playerId, matchId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && openPlayer(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openPlayer]);

  // move focus into the drawer on open and hand it back to the trigger on close
  useEffect(() => {
    if (!open) return;
    const trigger = document.activeElement as HTMLElement | null;
    closeBtn.current?.focus({ preventScroll: true });
    return () => { if (trigger?.isConnected) trigger.focus({ preventScroll: true }); };
  }, [open]);

  const shut = { transform: reduce ? "translateX(0%)" : "translateX(100%)", opacity: reduce ? 0 : 1 };

  return (
    <AnimatePresence>
      {open && (
        <div key="drawer" className="fixed inset-0 z-40">
          <motion.div aria-hidden className="absolute inset-0 bg-bg/60 backdrop-blur-[2px]"
            initial={{ opacity: 0 }} animate={{ opacity: 1, transition: { duration: 0.35, ease: DRAWER_EASE } }}
            exit={{ opacity: 0, transition: { duration: 0.2, ease: EASE } }}
            onMouseDown={() => openPlayer(null)} />
          <motion.aside ref={panel} role="dialog" aria-modal="true" aria-labelledby="player-drawer-title"
            initial={shut} animate={{ transform: "translateX(0%)", opacity: 1, transition: { duration: 0.35, ease: DRAWER_EASE } }}
            exit={{ ...shut, transition: { duration: 0.22, ease: DRAWER_EASE } }}
            onKeyDown={(e) => trapTab(e, panel.current)}
            className="scroll-thin absolute inset-y-0 right-0 w-full max-w-[560px] overflow-y-auto overscroll-contain bg-surface-1 shadow-[-30px_0_80px_-20px_rgba(0,0,0,0.8)] ring-1 ring-line-strong">
            <button ref={closeBtn} type="button" onClick={() => openPlayer(null)} aria-label="Close profile"
              className="absolute right-4 top-4 z-10 grid size-9 place-items-center rounded-full bg-surface-2 text-ink-2 ring-1 ring-line transition-[background-color,color,transform] duration-150 ease-out hover:bg-surface-3 hover:text-ink active:scale-[0.97]">
              <X size={16} weight="bold" aria-hidden />
            </button>
            {err ? (
              <div className="px-6 pb-10 pt-8 md:px-8">
                <h2 id="player-drawer-title" className="pr-12 text-[22px] font-semibold tracking-[-0.02em] text-ink">No profile yet</h2>
                <p className="mt-2 text-[14.5px] leading-[1.6] text-ink-3">We have no profile for this player. Close this panel and pick another player.</p>
              </div>
            ) : !p ? <ProfileSkeleton /> : <Profile p={p} />}
          </motion.aside>
        </div>
      )}
    </AnimatePresence>
  );
}

function ProfileSkeleton() {
  return (
    <div className="px-6 pt-8 md:px-8" aria-busy="true">
      <h2 id="player-drawer-title" className="sr-only">Loading player</h2>
      <div className="flex items-end gap-5" aria-hidden>
        <span className="size-[112px] shrink-0 rounded-2xl bg-surface-2 motion-safe:animate-pulse" />
        <span className="flex-1 space-y-3 pb-2">
          <span className="block h-7 w-48 rounded-full bg-surface-2 motion-safe:animate-pulse" />
          <span className="block h-3.5 w-32 rounded-full bg-surface-2 motion-safe:animate-pulse" />
        </span>
      </div>
      <div className="mt-10 h-[120px] rounded-2xl bg-surface-2 motion-safe:animate-pulse" aria-hidden />
      <div className="mt-8 h-[160px] rounded-2xl bg-surface-2 motion-safe:animate-pulse" aria-hidden />
    </div>
  );
}

function Block({ title, meta, children }: { title: string; meta?: ReactNode; children: ReactNode }) {
  return (
    <section>
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="text-[16px] font-semibold tracking-[-0.01em] text-ink">{title}</h3>
        {meta && <p className="tabular text-right text-[13px] text-ink-3">{meta}</p>}
      </div>
      {children}
    </section>
  );
}

function Profile({ p }: { p: PlayerProfile }) {
  const age = p.date_of_birth ? Math.floor((Date.now() - new Date(p.date_of_birth).getTime()) / 3.15576e10) : null;
  const display = p.nickname || p.short_name || p.name;
  const facts = [
    age != null && `${age} years old`,
    p.height_cm && `${p.height_cm} cm`,
    p.foot && (FOOT[p.foot.toLowerCase()] ?? `${p.foot} foot`),
    p.current_club,
    p.caps != null && p.caps > 0 && `${p.caps} caps`,
  ].filter((x): x is string => !!x);
  const sources = (p.sources ?? ["transfermarkt"]).filter((x) => x !== "statsbomb").map((x) => SOURCE_NAME[x] ?? x).join(" and ") || "public records";

  return (
    <div className="pb-12">
      <header className="px-6 pt-8 md:px-8">
        <div className="flex items-end gap-5 pr-10">
          <span className="relative size-[112px] shrink-0 overflow-hidden rounded-2xl">
            <RevealImage key={p.photo_url ?? "none"} src={p.photo_url} alt={display} className="size-full"
              fallback={<span className="grid size-full place-items-center bg-surface-3 text-[34px] font-semibold text-ink-3">{initials(p.short_name || p.name)}</span>} />
            <span className="pointer-events-none absolute inset-0 rounded-2xl outline outline-1 -outline-offset-1 outline-white/10" />
          </span>
          <div className="min-w-0 pb-1">
            <h2 id="player-drawer-title" className="text-balance text-[30px] font-semibold leading-[1.08] tracking-[-0.03em] text-ink">{display}</h2>
            {display !== p.name && <p className="mt-1 truncate text-[13.5px] text-ink-3">{p.name}</p>}
            {(p.position || p.nationality) && <p className="mt-2 text-[14.5px] text-ink-2">{[p.position, p.nationality].filter(Boolean).join(", ")}</p>}
          </div>
        </div>
        {facts.length > 0 && (
          <ul className="mt-6 flex flex-wrap gap-x-5 gap-y-1.5 text-[14px] text-ink-2" aria-label="Facts">
            {facts.map((f) => <li key={f} className="tabular">{f}</li>)}
          </ul>
        )}
      </header>

      <div className="mt-8 space-y-9 px-6 md:px-8">
        {p.in_match && (
          <Block title="In this match">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-5 rounded-2xl bg-surface-2 p-5 ring-1 ring-line sm:grid-cols-4">
              <Big label="Minutes" value={`${Math.round(p.in_match.minutes)}'`} />
              <Big label="Value added" value={`${p.in_match.vaep >= 0 ? "+" : ""}${p.in_match.vaep.toFixed(2)}`} />
              <Big label="Rank in match" value={`#${p.in_match.rank_in_match}`} />
              <Big label="Market value then" value={eur(p.in_match.market_value_eur)} />
            </dl>
            {p.in_match.age != null && <p className="mt-2.5 text-[13px] text-ink-3">Aged {p.in_match.age} on match day.</p>}
          </Block>
        )}

        {!p.career && (
          <p className="rounded-2xl bg-surface-2 p-5 text-[14px] leading-[1.6] text-ink-2 ring-1 ring-line">
            <span className="font-medium text-ink">Not in our match data.</span> This profile comes from {sources}. Our models only have event data for the 2,924 matches in StatsBomb's open data.
          </p>
        )}

        {p.career && (
          <Block title="Career in our data" meta={`${p.career.matches} matches`}>
            <dl className="grid grid-cols-3 gap-x-4 gap-y-5 rounded-2xl bg-surface-2 p-5 ring-1 ring-line sm:grid-cols-5">
              <Big small label="Minutes" value={Math.round(p.career.minutes).toLocaleString("en-GB")} />
              <Big small label="Value added per 90" value={p.career.vaep_per90.toFixed(2)} />
              <Big small label="Expected goals" value={p.career.xg.toFixed(1)} />
              <Big small label="Goals" value={String(p.career.goals)} />
              <Big small label="Progression per 90" value={p.career.prog_per90.toFixed(1)} />
            </dl>
          </Block>
        )}

        {p.valuations.length > 1 && <ValueChart p={p} />}

        {p.career && p.heatmap && (
          <div className="grid grid-cols-1 gap-8 sm:grid-cols-2 sm:gap-5">
            <Block title="Where they act">
              <Heatmap h={p.heatmap} />
              <p className="mt-2 text-[12.5px] text-ink-3">Attacking left to right, all matches</p>
            </Block>
            <Block title="Value split">
              <Split off={p.career.vaep_off} def={p.career.vaep_def} />
            </Block>
          </div>
        )}

        {p.top_moments.length > 0 && <Moments p={p} />}

        {p.career && p.career.by_competition.length > 0 && (
          <Block title="By competition">
            <div className="overflow-hidden rounded-2xl bg-surface-2 ring-1 ring-line">
              <table className="w-full border-collapse text-[13px]">
                <thead className="border-b border-line">
                  <tr className="text-[12px] text-ink-3">
                    <th scope="col" className="px-4 py-2.5 text-left font-medium">Competition</th>
                    <th scope="col" className="px-2 py-2.5 text-right font-medium">Matches</th>
                    <th scope="col" className="hidden px-2 py-2.5 text-right font-medium sm:table-cell">Minutes</th>
                    <th scope="col" className="px-2 py-2.5 text-right font-medium">Per 90</th>
                    <th scope="col" className="px-4 py-2.5 text-right font-medium">Goals</th>
                  </tr>
                </thead>
                <tbody>
                  {p.career.by_competition.map((c) => (
                    <tr key={c.competition + c.season + c.team} className="border-t border-line first:border-t-0">
                      <th scope="row" className="min-w-0 px-4 py-2.5 text-left font-normal">
                        <span className="block font-medium text-ink">{c.competition} {c.season}</span>
                        <span className="block text-[12px] text-ink-3">{c.team}</span>
                      </th>
                      <td className="tabular px-2 py-2.5 text-right text-ink-3">{c.matches}</td>
                      <td className="tabular hidden px-2 py-2.5 text-right text-ink-3 sm:table-cell">{Math.round(c.minutes).toLocaleString("en-GB")}</td>
                      <td className="tabular px-2 py-2.5 text-right font-medium text-ink">{c.vaep_per90.toFixed(2)}</td>
                      <td className="tabular px-4 py-2.5 text-right text-ink-2">{c.goals}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-[12.5px] text-ink-3">Per 90 is value added per 90 minutes.</p>
          </Block>
        )}

        <p className="text-pretty text-[12.5px] leading-[1.6] text-ink-3">
          Profile from Transfermarkt via transfermarkt-datasets (CC0){p.wikidata_id ? " and Wikidata (CC0)" : ""}.
          {p.match_confidence != null && <> Matched to our data with {Math.round(p.match_confidence * 100)}% confidence.</>}
          {p.photo_credit && <> Photo by {p.photo_credit}{p.photo_license ? ` (${p.photo_license})` : ""}, Wikimedia Commons.</>}
          {p.career ? " Career numbers come from MatchPulse's own models." : ""}
        </p>
      </div>
    </div>
  );
}

function Big({ label, value, small }: { label: string; value: string; small?: boolean }) {
  return (
    <div className="flex min-w-0 flex-col-reverse justify-end gap-1.5">
      <dt className="text-[12.5px] leading-[1.35] text-ink-3">{label}</dt>
      <dd className={`numeral leading-none text-ink ${small ? "text-[24px]" : "text-[30px]"}`}>{value}</dd>
    </div>
  );
}

/** Transfermarkt valuation history: a step line that draws on, with a hover readout. */
function ValueChart({ p }: { p: PlayerProfile }) {
  const [ref, { width }] = useSize<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const [last, setLast] = useState<number | null>(null);
  const reduce = useReducedMotion();
  const H = 132, P = { l: 48, r: 8, t: 14, b: 24 };
  const pts = useMemo(() => p.valuations.map((v) => ({ d: new Date(v.date), v: v.value_eur, club: v.club })), [p]);
  if (hover != null && hover !== last) setLast(hover);
  const shownIdx = hover ?? last;
  const shown = shownIdx != null ? pts[shownIdx] : null;

  const x = scaleTime().domain([pts[0].d, pts[pts.length - 1].d]).range([P.l, Math.max(P.l + 1, width - P.r)]);
  const y = scaleLinear().domain([0, Math.max(...pts.map((q) => q.v))]).nice(3).range([H - P.b, P.t]);
  const path = line<(typeof pts)[number]>().x((q) => x(q.d)).y((q) => y(q.v)).curve(curveStepAfter)(pts) ?? "";
  const fill = area<(typeof pts)[number]>().x((q) => x(q.d)).y0(H - P.b).y1((q) => y(q.v)).curve(curveStepAfter)(pts) ?? "";
  const match = p.matches[0]?.date && p.in_match ? new Date(p.matches[0].date) : null;
  const showMatch = match && match >= pts[0].d && match <= pts[pts.length - 1].d;

  return (
    <Block title="Market value" meta={<>Now <span className="text-ink">{eur(p.market_value_eur)}</span>, peak <span className="text-ink">{eur(p.peak_market_value_eur)}</span></>}>
      <div ref={ref} className="relative" style={{ height: H }}>
        {width > 0 && (
          <svg width={width} height={H} className="block overflow-visible" role="img"
            aria-label={`Market value from ${pts[0].d.getFullYear()} to ${pts[pts.length - 1].d.getFullYear()}, peaking at ${eur(p.peak_market_value_eur)}`}>
            {y.ticks(3).map((t) => (
              <g key={t}>
                <line x1={P.l} x2={width - P.r} y1={y(t)} y2={y(t)} stroke="var(--grid)" />
                <text x={P.l - 8} y={y(t) + 4} fontSize={11} fill="var(--ink-3)" textAnchor="end" className="tabular">{eur(t)}</text>
              </g>
            ))}
            <motion.path d={fill} fill="var(--ink)" initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 0.06 }} transition={{ duration: 0.6, delay: 0.5 }} />
            <motion.path d={path} fill="none" stroke="var(--ink-2)" strokeWidth={1.5} strokeLinejoin="round"
              initial={reduce ? false : { pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.1, delay: 0.2, ease: EASE }} />
            {showMatch && (
              <g>
                <line x1={x(match)} x2={x(match)} y1={P.t} y2={H - P.b} stroke="var(--ink-3)" strokeDasharray="3 3" />
                <text x={x(match) + 5} y={P.t + 9} fontSize={11} fill="var(--ink-2)">This match</text>
              </g>
            )}
            <text x={P.l} y={H - 5} fontSize={11} fill="var(--ink-3)" className="tabular">{pts[0].d.getFullYear()}</text>
            <text x={width - P.r} y={H - 5} fontSize={11} fill="var(--ink-3)" textAnchor="end" className="tabular">{pts[pts.length - 1].d.getFullYear()}</text>
            {shown && (
              <circle cx={x(shown.d)} cy={y(shown.v)} r={4} fill="var(--ink)" stroke="var(--surface-1)" strokeWidth={2} pointerEvents="none"
                opacity={hover != null ? 1 : 0} style={{ transition: `opacity ${hover != null ? "var(--tt-in-dur)" : "var(--tt-out-dur)"} ease-out` }} />
            )}
            <rect x={P.l} y={0} width={Math.max(0, width - P.l - P.r)} height={H} fill="transparent"
              onPointerMove={(e) => {
                const t = x.invert(e.clientX - e.currentTarget.getBoundingClientRect().left + P.l).getTime();
                // the valuation in force at the pointer (step-after)
                let i = 0;
                for (let k = 0; k < pts.length; k++) if (pts[k].d.getTime() <= t) i = k;
                setHover(i);
              }}
              onPointerLeave={() => setHover(null)} />
          </svg>
        )}
        {shown && width > 0 && (
          <div data-open={hover != null} style={{ left: Math.min(Math.max(x(shown.d), 100), width - 100), top: Math.max(-34, y(shown.v) - 42) }}
            className="t-tt absolute z-10 whitespace-nowrap rounded-lg bg-surface-3 px-2.5 py-1.5 text-[12px] text-ink shadow-[0_8px_24px_-8px_rgba(0,0,0,0.6)] ring-1 ring-line-strong">
            <span className="mr-2 text-ink-2">{monthFmt.format(shown.d)}</span>
            <span className="tabular font-medium">{eur(shown.v)}</span>
            {shown.club && <span className="text-ink-2">, {shown.club}</span>}
          </div>
        )}
      </div>
    </Block>
  );
}

function Heatmap({ h }: { h: NonNullable<PlayerProfile["heatmap"]> }) {
  const { L, W } = PITCH;
  const cw = L / h.nx, ch = W / h.ny;
  return (
    <svg viewBox={`-1.5 -1.5 ${L + 3} ${W + 3}`} className="w-full overflow-hidden rounded-xl" role="img" aria-label="Where this player's actions happen, attacking left to right">
      <PitchMarkings pad={1.5} texture={false} lineWidth={0.45} />
      {h.values.map((v, i) => {
        const cx = i % h.nx, cy = Math.floor(i / h.nx);
        return v > 0.02 ? <rect key={i} x={cx * cw} y={(h.ny - 1 - cy) * ch} width={cw} height={ch} fill="var(--ink)" opacity={Math.min(0.75, v * 0.75)} /> : null;
      })}
    </svg>
  );
}

function Split({ off, def }: { off: number; def: number }) {
  const total = Math.max(Math.abs(off) + Math.abs(def), 0.001);
  return (
    <div className="rounded-2xl bg-surface-2 p-4 ring-1 ring-line">
      {([["Attacking", off], ["Defending", def]] as const).map(([l, v]) => (
        <div key={l} className="mb-3 last:mb-0">
          <div className="mb-1.5 flex justify-between text-[13px]"><span className="text-ink-3">{l}</span><span className="tabular font-medium text-ink">{v.toFixed(1)}</span></div>
          <div className="h-1.5 rounded-full bg-surface-4"><div className="h-1.5 rounded-full bg-ink-2" style={{ width: `${(Math.abs(v) / total) * 100}%` }} /></div>
        </div>
      ))}
      <p className="mt-3 text-[12.5px] leading-[1.5] text-ink-3">Total value added from attacking and defending actions.</p>
    </div>
  );
}

function Moments({ p }: { p: PlayerProfile }) {
  const navigate = useNavigate();
  const matchId = useMatch((s) => s.matchId);
  const focusEvent = useMatch((s) => s.focusEvent);
  const focusSequence = useMatch((s) => s.focusSequence);
  const setPendingFocus = useMatch((s) => s.setPendingFocus);
  const openPlayer = usePlayerUi((s) => s.openPlayer);
  const go = (m: PlayerProfile["top_moments"][number]) => {
    openPlayer(null);
    if (m.match_id === matchId) {
      if (m.sequence_id) focusSequence(m.sequence_id); else if (m.event_id) focusEvent(m.event_id);
      return;
    }
    setPendingFocus(m.sequence_id ? { seq: m.sequence_id } : m.event_id ? { ev: m.event_id } : null);
    navigate(`/match/${encodeURIComponent(m.match_id)}`);
  };
  const rows = useMemo(() => p.top_moments.slice(0, 6), [p]);
  const inDb = useMemo(() => new Set(p.matches.filter((m) => m.in_db).map((m) => m.match_id)), [p]);
  return (
    <Block title="Best moments by value added">
      <ul className="space-y-0.5 rounded-[18px] bg-surface-2 p-1.5 ring-1 ring-line">
        {rows.map((m, i) => {
          const can = inDb.has(m.match_id);
          return (
            <li key={i}>
              <button type="button" onClick={() => can && go(m)} disabled={!can}
                className="flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left transition-[background-color,transform] duration-150 ease-out enabled:hover:bg-surface-3 enabled:active:scale-[0.98] disabled:cursor-default">
                <span className="numeral w-11 shrink-0 text-[18px] leading-[1.2] text-ink">{m.minute_label}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[12.5px] text-ink-3">{m.match_label}</span>
                  <span className="mt-0.5 block text-[14px] leading-[1.45] text-ink-2">{m.text?.replace(/(\d)[–—](\d)/g, "$1-$2") ?? (can ? "Open the moment" : "Training match, not in the demo set")}</span>
                </span>
                <span className="tabular shrink-0 pt-px text-[13px] font-medium text-ink-2">+{m.vaep.toFixed(2)}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </Block>
  );
}
