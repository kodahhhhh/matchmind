import { useEffect, useRef, useState } from "react";
import { scaleLinear } from "d3-scale";
import { area, line } from "d3-shape";
import { motion } from "motion/react";
import { api } from "../../api/client";
import type { Counterfactual, Marker, MatchEvent, ShotAlternatives, Side } from "../../api/types";
import { useMatch } from "../../store/match";
import { clock, pct, signed, xg } from "../../lib/format";
import { PitchMarkings } from "../pitch/PitchMarkings";
import { PITCH, sy } from "../pitch/geometry";

const CHANGE: Record<string, { change: Counterfactual["change"]; verb: string }> = {
  goal: { change: "remove_goal", verb: "never happened" },
  sub: { change: "no_sub", verb: "wasn't made" },
  card: { change: "remove_red_card", verb: "wasn't shown" },
};

type Pick = { kind: "marker"; marker: Marker } | { kind: "shot"; shot: MatchEvent };

export function WhatIf() {
  const data = useMatch((s) => s.data);
  const focusEvent = useMatch((s) => s.focusEvent);
  const [picked, setPicked] = useState<Pick | null>(null);
  const [result, setResult] = useState<Counterfactual | null>(null);
  const [shotResult, setShotResult] = useState<ShotAlternatives | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const resultRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (result || shotResult) resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [result, shotResult]);

  if (!data) return null;
  const nameOf = (id: number | null | undefined) =>
    [...data.match.lineups.home, ...data.match.lineups.away].find((p) => p.player_id === id)?.short_name ?? "Unknown";
  const options = data.match.markers.filter((m) => m.type === "goal" || m.type === "sub" || (m.type === "card" && m.detail !== "yellow"));
  const shots = data.events.filter((e) => e.type === "shot" && e.period < 5);
  const title = (m: Marker) =>
    m.type === "goal" ? `${nameOf(m.player_id)}'s goal` : m.type === "sub" ? `${nameOf(m.player_off_id)} → ${nameOf(m.player_id)} sub` : `${nameOf(m.player_id)}'s red card`;

  const pickMarker = (m: Marker) => {
    setPicked({ kind: "marker", marker: m });
    setShotResult(null);
    setError(null);
    focusEvent(m.event_id);
    setLoading(true);
    api.counterfactual(data.match.match_id, m.event_id, CHANGE[m.type].change)
      .then(setResult)
      .catch(() => setError("This moment can't be modelled."))
      .finally(() => setLoading(false));
  };
  const pickShot = (e: MatchEvent) => {
    setPicked({ kind: "shot", shot: e });
    setResult(null);
    setError(null);
    focusEvent(e.id);
    setLoading(true);
    api.shotAlternatives(data.match.match_id, e.id)
      .then(setShotResult)
      .catch(() => setError("No player positions were recorded for this shot."))
      .finally(() => setLoading(false));
  };

  const groups: [string, Marker[]][] = [["Goals", options.filter((m) => m.type !== "sub")], ["Substitutions", options.filter((m) => m.type === "sub")]];
  const chip = (on: boolean) =>
    `flex items-center gap-2 rounded-xl px-2.5 py-1.5 text-[12.5px] font-medium ring-1 transition ${on ? "bg-surface-4 text-ink ring-white/20" : "bg-surface-2 text-ink-2 ring-line hover:bg-surface-3"}`;

  return (
    <div className="scroll-thin h-full overflow-y-auto px-5 pb-5">
      <div className="pt-1">
        <div className="flex items-center gap-2">
          <span className="text-[15px] font-semibold text-ink">What if…</span>
          <span className="rounded-md bg-ai-soft px-1.5 py-[2px] text-[10px] font-bold uppercase tracking-wider text-ai ring-1 ring-[var(--ai-line)]">Modelled</span>
        </div>
        <p className="mt-0.5 text-[13px] leading-relaxed text-ink-3">Remove a moment and the model compares the next 15 minutes with and without it, next to real games in the same spot. Or pick a shot to see the passes that were on.</p>
      </div>

      {groups.map(([group, ms]) => ms.length > 0 && (
        <div key={group} className="mt-4">
          <div className="eyebrow mb-2">{group}</div>
          <div className="flex flex-wrap gap-1.5">
            {ms.map((m) => (
              <button key={m.event_id + m.type} onClick={() => pickMarker(m)} className={chip(picked?.kind === "marker" && picked.marker.event_id === m.event_id)}>
                <span className="h-2 w-2 rounded-full" style={{ background: `var(--${m.team})` }} />
                <span className="tabular text-ink-3">{clock(m.period, m.minute)}</span>
                {m.type === "goal" ? nameOf(m.player_id) : m.type === "sub" ? `${nameOf(m.player_off_id)} → ${nameOf(m.player_id)}` : nameOf(m.player_id)}
              </button>
            ))}
          </div>
        </div>
      ))}

      {shots.length > 0 && (
        <div className="mt-4">
          <div className="eyebrow mb-2">Shots · pass instead?</div>
          <div className="flex flex-wrap gap-1.5">
            {shots.map((e) => (
              <button key={e.id} onClick={() => pickShot(e)} className={chip(picked?.kind === "shot" && picked.shot.id === e.id)}>
                <span className="h-2 w-2 rounded-full" style={{ background: `var(--${e.team})` }} />
                <span className="tabular text-ink-3">{clock(e.period, e.minute)}</span>
                {e.player ?? "Unknown"}
                <span className="tabular text-ink-4">{xg(e.xg)}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {picked && (
        <div ref={resultRef} className={`mt-6 scroll-mt-4 transition ${loading ? "opacity-50" : ""}`}>
          <div className="display text-[26px] leading-[1.05] text-ink">
            {picked.kind === "marker"
              ? `What if ${title(picked.marker)} ${CHANGE[picked.marker.type].verb}?`
              : `What if ${picked.shot.player ?? "the shooter"} passed instead of shooting?`}
          </div>
          {error && !loading && <p className="mt-3 text-[13px] text-ink-3">{error}</p>}
          {picked.kind === "marker" && result && <Result r={result} />}
          {picked.kind === "shot" && shotResult && <ShotBranch r={shotResult} />}
        </div>
      )}
    </div>
  );
}

function Result({ r }: { r: Counterfactual }) {
  const teams = useMatch((s) => s.data!.match.teams);
  const base = r.factual ?? r.modelled;
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-4 space-y-4">
      {r.model && (
        <div className="flex items-center gap-2.5 rounded-xl bg-ai-soft px-3 py-2 text-[12px] text-ink-2 ring-1 ring-[var(--ai-line)]">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="shrink-0"><circle cx="7" cy="7" r="6" stroke="var(--ai)" strokeWidth="1.3" /><path d="M4 7.5 6 9.5l4-5" stroke="var(--ai)" strokeWidth="1.4" strokeLinecap="round" /></svg>
          <span>
            {r.method === "trained_model" ? "Trained model" : "Similar-match estimate"} · {r.model.trained_matches.toLocaleString()} matches · real outcome inside the range {Math.round(r.model.coverage_p10_p90.xg * 100)}% of the time
            {r.model.skill_vs_constant && <> · {Math.round(r.model.skill_vs_constant.xg * 100)}% sharper than a fixed range for xG, {Math.round(r.model.skill_vs_constant.possession * 100)}% for possession</>}
          </span>
        </div>
      )}

      {r.lineup_change && (
        <div className="rounded-xl bg-surface-2 px-3.5 py-2.5 text-[12.5px] text-ink-2 ring-1 ring-line">
          Puts <span className="font-semibold text-ink">{r.lineup_change.restored.name}</span> back on
          <span className="tabular text-ink-3"> ({r.lineup_change.restored.vaep_per90.toFixed(2)} VAEP/90)</span>
          {r.lineup_change.removed && <> instead of <span className="font-semibold text-ink">{r.lineup_change.removed.name}</span><span className="tabular text-ink-3"> ({r.lineup_change.removed.vaep_per90.toFixed(2)})</span></>}.
          <span className="text-ink-3"> Ratings come from every other match in the corpus.</span>
        </div>
      )}

      {r.negligible && (
        <div className="rounded-xl bg-surface-2 px-3.5 py-2.5 text-[12.5px] leading-relaxed text-ink-2 ring-1 ring-line">
          <span className="font-semibold text-ink">The model sees almost no difference.</span> With or without this moment, its estimate for the next 15 minutes barely moves.
        </div>
      )}

      {(["home", "away"] as Side[]).map((s) => (
        <div key={s} className="rounded-2xl bg-surface-2 p-4 ring-1 ring-line">
          <div className="mb-3 flex items-center justify-between">
            <span className="flex items-center gap-2 text-[13px] font-semibold text-ink"><span className="h-2.5 w-2.5 rounded-full" style={{ background: `var(--${s})` }} />{teams[s].name}</span>
            <span className="text-[11.5px] text-ink-3">xG over the next {r.horizon_minutes} minutes</span>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <Stat label="What happened" value={xg(r.actual[s].xg)} />
            <Stat label="Model, as it was" value={xg(base[s].xg.p50)} sub={`${xg(base[s].xg.p10)}–${xg(base[s].xg.p90)}`} />
            <Stat label="Model, changed" accent value={xg(r.modelled[s].xg.p50)} sub={`${xg(r.modelled[s].xg.p10)}–${xg(r.modelled[s].xg.p90)}`} />
          </div>
          {r.effect && (
            <div className="mt-2.5 text-[11.5px] text-ink-3">
              Change in the model's median: <span className="tabular text-ink-2">{delta(r.effect[s].xg, 2, " xG")}</span>, possession <span className="tabular text-ink-2">{delta(r.effect[s].possession * 100, 1, " pts")}</span>
              <span className="text-ink-4"> (as it was {pct(base[s].possession.p50)})</span>
            </div>
          )}
          <RangeChart r={r} side={s} />
        </div>
      ))}

      <div>
        <div className="mb-2 flex items-baseline justify-between">
          <span className="eyebrow">Most similar real situations</span>
          <span className="text-[11.5px] text-ink-4">top {r.analogs.length} of {r.n_analogs}</span>
        </div>
        <ul className="overflow-hidden rounded-2xl bg-surface-2 ring-1 ring-line">
          {r.analogs.map((a, i) => (
            <li key={a.match_id + a.minute + i} className={`flex items-center gap-3 px-3.5 py-2.5 ${i ? "border-t border-line" : ""}`}>
              <span className="w-10 text-[12px] font-semibold tabular text-ai">{Math.round(a.similarity * 100)}%</span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] font-medium text-ink">{a.home} v {a.away}</div>
                <div className="text-[11.5px] text-ink-3">{a.competition} {a.season} · {a.minute}' · score {a.score_state}</div>
              </div>
              <span className="text-right text-[11px] leading-tight text-ink-3">next 15'<br /><span className="text-[12px] tabular text-ink-2">{xg(a.next15.xg_for)} / {xg(a.next15.xg_against)} xG</span></span>
            </li>
          ))}
        </ul>
      </div>
      <p className="text-[11.5px] leading-relaxed text-ink-4">{r.caveat}</p>
    </motion.div>
  );
}

/** Signed change, or "no change" when it rounds to zero. */
function delta(v: number, digits: number, unit: string) {
  return Math.abs(v) < 0.5 * 10 ** -digits ? "no change" : `${signed(v, digits)}${unit}`;
}

function Stat({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: boolean }) {
  return (
    <div>
      <div className={`text-[11.5px] ${accent ? "text-ai" : "text-ink-3"}`}>{label}</div>
      <div className="display text-[28px] leading-none text-ink">{value}</div>
      {sub && <div className="mt-0.5 text-[11px] tabular text-ink-4">range {sub}</div>}
    </div>
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
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-3 w-full" role="img" aria-label="Actual cumulative xG with modelled ranges as it was, changed, and in similar matches">
      <line x1={P.l} x2={W - 4} y1={y(0)} y2={y(0)} stroke="var(--axis)" />
      {legacy && <path d={legacy} fill="var(--ai)" opacity={0.14} />}
      <path d={act(r.series) ?? ""} fill="none" stroke={`var(--${side})`} strokeWidth={2.2} strokeLinecap="round" />
      {last && <circle cx={x(last.offset_min)} cy={y(last.actual[side])} r={3.5} fill={`var(--${side})`} stroke="var(--surface-2)" strokeWidth={2} />}
      <line x1={W - P.r + 12} x2={W - P.r + 12} y1={P.t} y2={H - P.b} stroke="var(--border-strong)" strokeDasharray="2 3" />
      {f && bar(W - P.r + 38, f, "var(--ink-3)", "as was")}
      {bar(W - P.r + 82, m, "var(--ai)", "changed")}
      {a && bar(W - P.r + 126, a, "var(--ink-2)", "similar")}
      <text x={P.l} y={H - 3} fontSize={9.5} fill="var(--ink-4)">{r.anchor.label}</text>
      <text x={W - P.r} y={H - 3} fontSize={9.5} fill="var(--ink-4)" textAnchor="end">+{r.horizon_minutes}'</text>
      <text x={P.l} y={P.t + 2} fontSize={9.5} fill="var(--ink-3)">what happened</text>
    </svg>
  );
}

const VERDICT: Record<ShotAlternatives["comparison"], string> = {
  pass_higher: "The best pass is modelled as more dangerous than the shot.",
  shot_higher: "The shot is modelled as the better option.",
  similar: "The shot and the best pass are modelled as roughly equal.",
  no_teammates: "No teammates were in the frame to pass to.",
};

function ShotBranch({ r }: { r: ShotAlternatives }) {
  const best = r.options[0];
  const shown = r.options.slice(0, 5);
  const top = Math.max(...r.options.map((o) => o.value), r.shot.xg, 0.01);
  // Home attacks right, away attacks left in the API frame. Crop to the players
  // and the goal, padded, at least 4:3 so the panel stays short.
  const goalX = r.shot.team === "home" ? PITCH.L : 0;
  const xs = [r.shot.x, goalX, ...r.options.map((o) => o.x)];
  const ys = [r.shot.y, PITCH.W / 2 - 9, PITCH.W / 2 + 9, ...r.options.map((o) => o.y)];
  let x0 = Math.min(...xs) - 6, x1 = Math.max(...xs) + 6;
  let y0 = Math.min(...ys) - 5, y1 = Math.max(...ys) + 5;
  const minW = (y1 - y0) * 4 / 3;
  if (x1 - x0 < minW) {
    const grow = minW - (x1 - x0);
    if (goalX === 0) x1 += grow; else x0 -= grow;
  }
  const minH = (x1 - x0) * 0.55;
  if (y1 - y0 < minH) { const c = (y0 + y1) / 2; y0 = c - minH / 2; y1 = c + minH / 2; }
  const vb = { x: x0, y: PITCH.W - y1, w: x1 - x0, h: y1 - y0 };
  const font = vb.w / 30;
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-4 space-y-4">
      <div className="overflow-hidden rounded-2xl ring-1 ring-line">
        <svg viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`} className="block w-full" role="img" aria-label="Shot location and modelled passing options">
          <PitchMarkings pad={40} padX={40} texture={false} lineWidth={0.3} />
          <line x1={r.shot.x} y1={sy(r.shot.y)} x2={goalX} y2={PITCH.W / 2} stroke={`var(--${r.shot.team})`} strokeWidth={0.45} strokeDasharray="1.2 1" opacity={0.9} />
          {shown.map((o, i) => (
            <line key={i} x1={r.shot.x} y1={sy(r.shot.y)} x2={o.x} y2={sy(o.y)}
              stroke={i === 0 ? "var(--ai)" : "var(--ink-2)"} strokeWidth={0.25 + 0.9 * (o.value / top)} opacity={i === 0 ? 1 : 0.45} strokeLinecap="round" />
          ))}
          {r.options.map((o, i) => (
            <g key={`p${i}`}>
              <circle cx={o.x} cy={sy(o.y)} r={1.25} fill={i === 0 ? "var(--ai)" : "var(--surface-4)"} stroke="var(--ink)" strokeWidth={0.2} />
              {i < 3 && <text x={o.x + 1.8} y={sy(o.y) + font * 0.35} fontSize={font} fill="var(--ink)" stroke="var(--on-grass)" strokeWidth={font * 0.18} paintOrder="stroke">{o.player.split(" ").slice(-1)[0]} · {pct(o.p_complete)}</text>}
            </g>
          ))}
          <circle cx={r.shot.x} cy={sy(r.shot.y)} r={1.5} fill={`var(--${r.shot.team})`} stroke="var(--ink)" strokeWidth={0.25} />
        </svg>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-2xl bg-surface-2 p-3.5 ring-1 ring-line">
          <div className="eyebrow mb-1.5">What happened</div>
          <div className="text-[13px] font-semibold text-ink">{r.shot.player} shot · {r.shot.label}</div>
          <div className="display mt-1 text-[28px] leading-none text-ink">{xg(r.shot.xg)} <span className="text-[13px] text-ink-3">xG</span></div>
          <div className="mt-1 text-[12px] text-ink-3">{r.shot.outcome}</div>
        </div>
        <div className="rounded-2xl bg-ai-soft p-3.5 ring-1 ring-[var(--ai-line)]">
          <div className="eyebrow mb-1.5 text-ai">Best modelled pass</div>
          {best ? (
            <>
              <div className="text-[13px] font-semibold text-ink">to {best.player}</div>
              <div className="display mt-1 text-[28px] leading-none text-ink">{xg(best.value)} <span className="text-[13px] text-ink-3">modelled</span></div>
              <div className="mt-1 text-[12px] text-ink-3">{pct(best.p_complete)} to complete × {xg(Math.max(best.xg_if_shot, best.xt))} if received</div>
            </>
          ) : <div className="text-[13px] text-ink-3">No teammates in the frame.</div>}
        </div>
      </div>
      <p className="text-[13px] font-medium text-ink-2">{VERDICT[r.comparison]}</p>

      {shown.length > 0 && (
        <ul className="overflow-hidden rounded-2xl bg-surface-2 ring-1 ring-line">
          <li className="flex items-center gap-3 px-3.5 py-2 text-[11px] text-ink-4">
            <span className="flex-1">Teammate</span><span className="w-14 text-right">completes</span><span className="w-14 text-right">if shot</span><span className="w-14 text-right">zone xT</span><span className="w-14 text-right">value</span>
          </li>
          {shown.map((o, i) => (
            <li key={i} className="flex items-center gap-3 border-t border-line px-3.5 py-2 text-[12.5px] tabular">
              <span className={`flex-1 truncate font-medium ${i === 0 ? "text-ai" : "text-ink"}`}>{o.player}</span>
              <span className="w-14 text-right text-ink-2">{pct(o.p_complete)}</span>
              <span className="w-14 text-right text-ink-2">{xg(o.xg_if_shot)}</span>
              <span className="w-14 text-right text-ink-2">{xg(o.xt)}</span>
              <span className="w-14 text-right font-semibold text-ink">{xg(o.value)}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="rounded-xl bg-surface-2 px-3.5 py-2.5 text-[11.5px] leading-relaxed text-ink-3 ring-1 ring-line">
        {r.model.name}: {r.model.trained_passes.toLocaleString()} passes from {r.model.trained_matches} matches · AUC {r.model.auc.toFixed(2)} ({r.model.baseline_auc.toFixed(2)} without defender positions)
        <ul className="mt-1.5 list-disc space-y-0.5 pl-4">
          {r.assumptions.map((a) => <li key={a}>{a}</li>)}
        </ul>
      </div>
      <p className="text-[11.5px] leading-relaxed text-ink-4">{r.caveat}</p>
    </motion.div>
  );
}
