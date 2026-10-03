import { useEffect, useRef, useState } from "react";
import { scaleLinear } from "d3-scale";
import { area, line } from "d3-shape";
import { motion } from "motion/react";
import { api } from "../../api/client";
import type { Counterfactual, Marker, Side } from "../../api/types";
import { useMatch } from "../../store/match";
import { clock, pct, xg } from "../../lib/format";

const CHANGE: Record<string, { change: Counterfactual["change"]; verb: string }> = {
  goal: { change: "remove_goal", verb: "never happened" },
  sub: { change: "no_sub", verb: "wasn't made" },
  card: { change: "remove_red_card", verb: "wasn't shown" },
};

export function WhatIf() {
  const data = useMatch((s) => s.data);
  const focusEvent = useMatch((s) => s.focusEvent);
  const [picked, setPicked] = useState<Marker | null>(null);
  const [result, setResult] = useState<Counterfactual | null>(null);
  const [loading, setLoading] = useState(false);
  const resultRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (result) resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [result]);

  if (!data) return null;
  const nameOf = (id: number | null | undefined) =>
    [...data.match.lineups.home, ...data.match.lineups.away].find((p) => p.player_id === id)?.short_name ?? "Unknown";
  const options = data.match.markers.filter((m) => m.type === "goal" || m.type === "sub" || (m.type === "card" && m.detail !== "yellow"));
  const title = (m: Marker) =>
    m.type === "goal" ? `${nameOf(m.player_id)}'s goal` : m.type === "sub" ? `${nameOf(m.player_off_id)} → ${nameOf(m.player_id)} sub` : `${nameOf(m.player_id)}'s red card`;

  const pick = (m: Marker) => {
    setPicked(m);
    focusEvent(m.event_id);
    setLoading(true);
    api.counterfactual(data.match.match_id, m.event_id, CHANGE[m.type].change)
      .then(setResult)
      .finally(() => setLoading(false));
  };

  const groups: [string, Marker[]][] = [["Goals", options.filter((m) => m.type !== "sub")], ["Substitutions", options.filter((m) => m.type === "sub")]];

  return (
    <div className="scroll-thin h-full overflow-y-auto px-5 pb-5">
      <div className="pt-1">
        <div className="flex items-center gap-2">
          <span className="text-[15px] font-semibold text-ink">What if…</span>
          <span className="rounded-md bg-ai-soft px-1.5 py-[2px] text-[10px] font-bold uppercase tracking-wider text-ai ring-1 ring-[var(--ai-line)]">Modelled</span>
        </div>
        <p className="mt-0.5 text-[13px] leading-relaxed text-ink-3">Remove a moment. A model trained on 2,924 matches estimates the next 15 minutes, next to real games that were in the same spot.</p>
      </div>

      {groups.map(([group, ms]) => ms.length > 0 && (
        <div key={group} className="mt-4">
          <div className="eyebrow mb-2">{group}</div>
          <div className="flex flex-wrap gap-1.5">
            {ms.map((m) => {
              const on = picked?.event_id === m.event_id;
              return (
                <button key={m.event_id + m.type} onClick={() => pick(m)}
                  className={`flex items-center gap-2 rounded-xl px-2.5 py-1.5 text-[12.5px] font-medium ring-1 transition ${on ? "bg-surface-4 text-ink ring-white/20" : "bg-surface-2 text-ink-2 ring-line hover:bg-surface-3"}`}>
                  <span className="h-2 w-2 rounded-full" style={{ background: `var(--${m.team})` }} />
                  <span className="tabular text-ink-3">{clock(m.period, m.minute)}</span>
                  {m.type === "goal" ? nameOf(m.player_id) : `${nameOf(m.player_off_id)} → ${nameOf(m.player_id)}`}
                </button>
              );
            })}
          </div>
        </div>
      ))}

      {picked && (
        <div ref={resultRef} className={`mt-6 scroll-mt-4 transition ${loading ? "opacity-50" : ""}`}>
          <div className="display text-[26px] leading-[1.05] text-ink">What if {title(picked)} {CHANGE[picked.type].verb}?</div>
          {result && <Result r={result} />}
        </div>
      )}
    </div>
  );
}

function Result({ r }: { r: Counterfactual }) {
  const teams = useMatch((s) => s.data!.match.teams);
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-4 space-y-4">
      {r.model && (
        <div className="flex items-center gap-2.5 rounded-xl bg-ai-soft px-3 py-2 text-[12px] text-ink-2 ring-1 ring-[var(--ai-line)]">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="6" stroke="var(--ai)" strokeWidth="1.3" /><path d="M4 7.5 6 9.5l4-5" stroke="var(--ai)" strokeWidth="1.4" strokeLinecap="round" /></svg>
          <span>{r.method === "trained_model" ? "Trained model" : "Similar-match estimate"} · {r.model.trained_matches.toLocaleString()} matches · real outcome inside the range {Math.round(r.model.coverage_p10_p90.xg * 100)}% of the time</span>
        </div>
      )}
      {(["home", "away"] as Side[]).map((s) => (
        <div key={s} className="rounded-2xl bg-surface-2 p-4 ring-1 ring-line">
          <div className="mb-3 flex items-center justify-between">
            <span className="flex items-center gap-2 text-[13px] font-semibold text-ink"><span className="h-2.5 w-2.5 rounded-full" style={{ background: `var(--${s})` }} />{teams[s].name}</span>
            <span className="text-[11.5px] text-ink-3">xG over the next {r.horizon_minutes} minutes</span>
          </div>
          <div className="flex items-end gap-5">
            <div><div className="text-[11.5px] text-ink-3">What happened</div><div className="display text-[30px] leading-none text-ink">{xg(r.actual[s].xg)}</div></div>
            <div><div className="text-[11.5px] text-ai">Modelled range</div><div className="display text-[30px] leading-none text-ink">{xg(r.modelled[s].xg.p10)}<span className="text-ink-4">–</span>{xg(r.modelled[s].xg.p90)}</div></div>
            <div className="ml-auto text-right text-[11.5px] leading-snug text-ink-3">Possession<br /><span className="text-ink-2">{pct(r.actual[s].possession)}</span> vs <span className="text-ink-2">{pct(r.modelled[s].possession.p10)}–{pct(r.modelled[s].possession.p90)}</span></div>
          </div>
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

/** Actual cumulative xG over the horizon, ending in two range bars: trained model and similar matches. */
function RangeChart({ r, side }: { r: Counterfactual; side: Side }) {
  const W = 380, H = 112, P = { l: 4, r: 96, t: 10, b: 18 };
  const m = r.modelled[side].xg;
  const a = r.analog_summary?.[side].xg;
  const max = Math.max(m.p90, a?.p90 ?? 0, ...r.series.map((d) => d.actual[side]), 0.2);
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
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-3 w-full" role="img" aria-label="Actual cumulative xG with modelled and similar-match ranges">
      <line x1={P.l} x2={W - 4} y1={y(0)} y2={y(0)} stroke="var(--axis)" />
      {legacy && <path d={legacy} fill="var(--ai)" opacity={0.14} />}
      <path d={act(r.series) ?? ""} fill="none" stroke={`var(--${side})`} strokeWidth={2.2} strokeLinecap="round" />
      {last && <circle cx={x(last.offset_min)} cy={y(last.actual[side])} r={3.5} fill={`var(--${side})`} stroke="var(--surface-2)" strokeWidth={2} />}
      <line x1={W - P.r + 14} x2={W - P.r + 14} y1={P.t} y2={H - P.b} stroke="var(--border-strong)" strokeDasharray="2 3" />
      {bar(W - P.r + 42, m, "var(--ai)", "model")}
      {a && bar(W - P.r + 76, a, "var(--ink-2)", "similar")}
      <text x={P.l} y={H - 3} fontSize={9.5} fill="var(--ink-4)">{r.anchor.label}</text>
      <text x={W - P.r} y={H - 3} fontSize={9.5} fill="var(--ink-4)" textAnchor="end">+{r.horizon_minutes}'</text>
      <text x={P.l} y={P.t + 2} fontSize={9.5} fill="var(--ink-3)">what happened</text>
    </svg>
  );
}
