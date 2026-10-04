import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { AnimatePresence, motion } from "motion/react";
import { scaleLinear, scaleTime } from "d3-scale";
import { line, curveStepAfter } from "d3-shape";
import { api } from "../../api/client";
import type { PlayerProfile } from "../../api/types";
import { useMatch } from "../../store/match";
import { usePlayerUi } from "../../store/ui";
import { PitchMarkings } from "../pitch/PitchMarkings";
import { PITCH } from "../pitch/geometry";

export const eur = (v: number | null | undefined) =>
  v == null ? "—" : v >= 1e6 ? `€${(v / 1e6).toFixed(v >= 1e8 ? 0 : 1)}m` : v >= 1e3 ? `€${Math.round(v / 1e3)}k` : `€${v}`;

/** Slide-over player profile; open it from anywhere with usePlayerUi().openPlayer(id). */
export function PlayerDrawer() {
  const playerId = usePlayerUi((s) => s.playerId);
  const openPlayer = usePlayerUi((s) => s.openPlayer);
  const matchId = useMatch((s) => s.matchId);
  const [p, setP] = useState<PlayerProfile | null>(null);
  const [err, setErr] = useState(false);

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

  return (
    <AnimatePresence>
      {playerId != null && (
        <motion.div className="fixed inset-0 z-40 flex justify-end bg-black/40 backdrop-blur-[2px]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          onMouseDown={() => openPlayer(null)}>
          <motion.aside initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 40, opacity: 0 }} transition={{ type: "spring", bounce: 0.1, duration: 0.4 }}
            onMouseDown={(e) => e.stopPropagation()}
            className="scroll-thin h-full w-full max-w-[560px] overflow-y-auto bg-surface-1 shadow-[-30px_0_80px_-20px_rgba(0,0,0,0.8)] ring-1 ring-white/10">
            <button onClick={() => openPlayer(null)} aria-label="Close" className="absolute right-4 top-4 z-10 flex h-9 w-9 items-center justify-center rounded-full bg-surface-3 text-ink-2 transition hover:text-ink">
              <svg width="12" height="12" viewBox="0 0 12 12"><path d="M1 1l10 10M11 1 1 11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
            </button>
            {err ? <div className="p-8 text-sm text-ink-3">No profile for this player yet.</div>
              : !p ? <div className="p-8"><span className="shimmer text-sm font-medium">Loading player</span></div>
              : <Profile p={p} />}
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function Profile({ p }: { p: PlayerProfile }) {
  const age = p.date_of_birth ? Math.floor((Date.now() - new Date(p.date_of_birth).getTime()) / 3.15576e10) : null;
  return (
    <div className="pb-10">
      <div className="relative overflow-hidden px-6 pb-6 pt-8">
        <div className="absolute inset-0 bg-gradient-to-b from-[#173d2a]/70 to-transparent" />
        <div className="relative flex items-end gap-5">
          <Avatar p={p} />
          <div className="min-w-0 pb-1">
            <div className="eyebrow mb-1">{[p.position, p.nationality].filter(Boolean).join(" · ")}</div>
            <h2 className="display text-[38px] leading-[0.95] text-ink">{p.nickname || p.short_name || p.name}</h2>
            {(p.nickname || p.short_name) && p.name !== (p.nickname || p.short_name) && <div className="mt-1 text-[12px] text-ink-3">{p.name}</div>}
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[12.5px] text-ink-2">
              {age != null && <span>{age} yrs</span>}
              {p.height_cm && <span>{p.height_cm} cm</span>}
              {p.foot && <span className="capitalize">{p.foot} foot</span>}
              {p.current_club && <span>{p.current_club}</span>}
              {p.caps != null && p.caps > 0 && <span>{p.caps} caps</span>}
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-5 px-6">
        {p.in_match && (
          <div className="rounded-2xl bg-surface-2 p-4 ring-1 ring-line">
            <div className="eyebrow mb-3">In this match</div>
            <div className="grid grid-cols-4 gap-3">
              <Big label="Minutes" value={`${Math.round(p.in_match.minutes)}'`} />
              <Big label="Value added" value={`${p.in_match.vaep >= 0 ? "+" : ""}${p.in_match.vaep.toFixed(2)}`} />
              <Big label="Rank in match" value={`#${p.in_match.rank_in_match}`} />
              <Big label="Market value then" value={eur(p.in_match.market_value_eur)} />
            </div>
            {p.in_match.age != null && <div className="mt-2 text-[11.5px] text-ink-3">Aged {p.in_match.age} on match day.</div>}
          </div>
        )}

        {!p.career && (
          <div className="rounded-2xl bg-surface-2 p-4 text-[13px] leading-relaxed text-ink-2 ring-1 ring-line">
            <span className="font-semibold text-ink">Not in our match data.</span> This profile comes from {(p.sources ?? ["transfermarkt"]).filter((x) => x !== "statsbomb").join(" and ") || "public records"};
            our models only have event data for the 2,924 matches in StatsBomb's open data.
          </div>
        )}

        {p.career && <div>
          <div className="eyebrow mb-2">Career in our data · {p.career.matches} matches</div>
          <div className="grid grid-cols-5 gap-2">
            <Stat label="Minutes" value={Math.round(p.career.minutes).toLocaleString()} />
            <Stat label="VAEP / 90" value={p.career.vaep_per90.toFixed(2)} accent />
            <Stat label="xG" value={p.career.xg.toFixed(1)} />
            <Stat label="Goals" value={String(p.career.goals)} />
            <Stat label="Prog / 90" value={p.career.prog_per90.toFixed(1)} />
          </div>
        </div>}

        {p.valuations.length > 1 && <ValueChart p={p} />}

        {p.career && p.heatmap && <div className="grid grid-cols-[1fr_1fr] gap-4">
          <div>
            <div className="eyebrow mb-2">Where they act</div>
            <Heatmap h={p.heatmap} />
            <div className="mt-1 text-[11px] text-ink-4">Attacking left → right, all matches</div>
          </div>
          <div>
            <div className="eyebrow mb-2">Value split</div>
            <Split off={p.career.vaep_off} def={p.career.vaep_def} />
          </div>
        </div>}

        {p.top_moments.length > 0 && <Moments p={p} />}

        {p.career && p.career.by_competition.length > 0 && <div>
          <div className="eyebrow mb-2">By competition</div>
          <div className="overflow-hidden rounded-2xl bg-surface-2 ring-1 ring-line">
            {p.career.by_competition.map((c, i) => (
              <div key={c.competition + c.season + c.team} className={`grid grid-cols-[1.6fr_0.6fr_0.7fr_0.6fr_0.5fr] items-center gap-2 px-3.5 py-2 text-[12.5px] ${i ? "border-t border-line" : ""}`}>
                <span className="min-w-0"><span className="block truncate font-medium text-ink">{c.competition} {c.season}</span><span className="block truncate text-[11px] text-ink-3">{c.team}</span></span>
                <span className="tabular text-ink-3">{c.matches} gp</span>
                <span className="tabular text-ink-3">{Math.round(c.minutes).toLocaleString()}'</span>
                <span className="text-right font-semibold tabular text-ink">{c.vaep_per90.toFixed(2)}</span>
                <span className="text-right tabular text-ink-2">{c.goals}g</span>
              </div>
            ))}
          </div>
        </div>}

        <div className="text-[11px] leading-relaxed text-ink-4">
          Profile: Transfermarkt via transfermarkt-datasets (CC0){p.wikidata_id ? " and Wikidata (CC0)" : ""}
          {p.match_confidence != null && <> · matched with {Math.round(p.match_confidence * 100)}% confidence</>}
          {p.photo_credit && <> · Photo: {p.photo_credit}{p.photo_license ? ` (${p.photo_license})` : ""}, Wikimedia Commons</>}
          .{p.career ? " Career numbers are MatchMind's own models." : ""}
        </div>
      </div>
    </div>
  );
}

function Avatar({ p }: { p: PlayerProfile }) {
  const [broken, setBroken] = useState(false);
  const initials = p.short_name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  return p.photo_url && !broken ? (
    <img src={p.photo_url} alt={p.nickname || p.name} onError={() => setBroken(true)}
      className="h-[104px] w-[104px] shrink-0 rounded-[28px] object-cover object-top ring-2 ring-white/15" />
  ) : (
    <div className="display flex h-[104px] w-[104px] shrink-0 items-center justify-center rounded-[28px] bg-surface-3 text-[40px] text-ink-2 ring-2 ring-white/10">{initials}</div>
  );
}

function Big({ label, value }: { label: string; value: string }) {
  return <div><div className="text-[11px] text-ink-3">{label}</div><div className="display text-[26px] leading-tight text-ink">{value}</div></div>;
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-xl bg-surface-2 px-2.5 py-2 ring-1 ring-line">
      <div className="text-[10.5px] text-ink-3">{label}</div>
      <div className={`text-[15px] font-semibold tabular ${accent ? "text-ai" : "text-ink"}`}>{value}</div>
    </div>
  );
}

function ValueChart({ p }: { p: PlayerProfile }) {
  const W = 512, H = 120, P = { l: 44, r: 8, t: 10, b: 20 };
  const pts = p.valuations.map((v) => ({ d: new Date(v.date), v: v.value_eur, club: v.club }));
  const x = scaleTime().domain([pts[0].d, pts[pts.length - 1].d]).range([P.l, W - P.r]);
  const y = scaleLinear().domain([0, Math.max(...pts.map((q) => q.v))]).nice(3).range([H - P.b, P.t]);
  const path = line<(typeof pts)[number]>().x((q) => x(q.d)).y((q) => y(q.v)).curve(curveStepAfter)(pts);
  const match = p.matches[0]?.date && p.in_match ? new Date(p.matches[0].date) : null;
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <span className="eyebrow">Market value</span>
        <span className="text-[12px] text-ink-3">now <span className="font-semibold text-ink">{eur(p.market_value_eur)}</span> · peak <span className="font-semibold text-ink">{eur(p.peak_market_value_eur)}</span></span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded-2xl bg-surface-2 ring-1 ring-line" role="img" aria-label="Market value over time">
        {y.ticks(3).map((t) => (
          <g key={t}>
            <line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} stroke="var(--grid)" />
            <text x={P.l - 6} y={y(t) + 3.5} fontSize={9.5} fill="var(--ink-4)" textAnchor="end">{eur(t)}</text>
          </g>
        ))}
        <path d={path ?? ""} fill="none" stroke="var(--ink)" strokeWidth={2} strokeLinejoin="round" />
        {match && match >= pts[0].d && match <= pts[pts.length - 1].d && (
          <g>
            <line x1={x(match)} x2={x(match)} y1={P.t} y2={H - P.b} stroke="var(--ai)" strokeDasharray="3 3" />
            <text x={x(match) + 4} y={P.t + 8} fontSize={9.5} fill="var(--ai)">this match</text>
          </g>
        )}
        <text x={P.l} y={H - 5} fontSize={9.5} fill="var(--ink-4)">{pts[0].d.getFullYear()}</text>
        <text x={W - P.r} y={H - 5} fontSize={9.5} fill="var(--ink-4)" textAnchor="end">{pts[pts.length - 1].d.getFullYear()}</text>
      </svg>
    </div>
  );
}

function Heatmap({ h }: { h: NonNullable<PlayerProfile["heatmap"]> }) {
  const { L, W } = PITCH;
  const cw = L / h.nx, ch = W / h.ny;
  return (
    <svg viewBox={`-1.5 -1.5 ${L + 3} ${W + 3}`} className="w-full overflow-hidden rounded-xl" role="img" aria-label="Action heatmap">
      <PitchMarkings pad={1.5} texture={false} lineWidth={0.45} />
      {h.values.map((v, i) => {
        const cx = i % h.nx, cy = Math.floor(i / h.nx);
        return v > 0.02 ? <rect key={i} x={cx * cw} y={(h.ny - 1 - cy) * ch} width={cw} height={ch} fill="#b6a4ff" opacity={Math.min(0.85, v * 0.85)} /> : null;
      })}
    </svg>
  );
}

function Split({ off, def }: { off: number; def: number }) {
  const total = Math.max(Math.abs(off) + Math.abs(def), 0.001);
  return (
    <div className="rounded-xl bg-surface-2 p-3 ring-1 ring-line">
      {[["Attacking", off], ["Defending", def]].map(([l, v]) => (
        <div key={l as string} className="mb-2 last:mb-0">
          <div className="mb-1 flex justify-between text-[12px]"><span className="text-ink-3">{l}</span><span className="font-semibold tabular text-ink">{(v as number).toFixed(1)}</span></div>
          <div className="h-[5px] rounded-full bg-surface-4"><div className="h-[5px] rounded-full bg-ai" style={{ width: `${(Math.abs(v as number) / total) * 100}%` }} /></div>
        </div>
      ))}
      <p className="mt-2 text-[11px] leading-snug text-ink-4">Total VAEP from attacking vs defending actions.</p>
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
    <div>
      <div className="eyebrow mb-2">Best moments by value added</div>
      <div className="overflow-hidden rounded-2xl bg-surface-2 ring-1 ring-line">
        {rows.map((m, i) => (
          <button key={i} onClick={() => inDb.has(m.match_id) && go(m)} disabled={!inDb.has(m.match_id)}
            className={`flex w-full items-start gap-3 px-3.5 py-2.5 text-left transition enabled:hover:bg-surface-3 ${i ? "border-t border-line" : ""}`}>
            <span className="display w-12 shrink-0 text-[16px] text-ink">{m.minute_label}</span>
            <span className="min-w-0 flex-1">
              <span className="block text-[11.5px] text-ink-3">{m.match_label}</span>
              <span className="block text-[13px] leading-snug text-ink-2">{m.text ?? (inDb.has(m.match_id) ? "Open the moment" : "Training match (not in the demo set)")}</span>
            </span>
            <span className="shrink-0 text-[12px] font-semibold tabular text-ai">+{m.vaep.toFixed(2)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
