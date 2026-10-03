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
      {(["home", "away"] as Side[]).map((s) => (
        <div key={s} className="rounded-2xl bg-surface-2 p-4 ring-1 ring-line">
          <div className="mb-3 flex items-center justify-between">
            <span className="flex items-center gap-2 text-[13px] font-semibold text-ink"><span className="h-2.5 w-2.5 rounded-full" style={{ background: `var(--${s})` }} />{teams[s].name}</span>
            <span className="text-[11.5px] text-ink-3">next {r.horizon_minutes} minutes</span>
          </div>
          <div className="flex items-end gap-5">
            <div><div className="text-[11.5px] text-ink-3">Actual xG</div><div className="display text-[30px] leading-none text-ink">{xg(r.actual[s].xg)}</div></div>
            <div><div className="text-[11.5px] text-ai">Modelled range</div><div className="display text-[30px] leading-none text-ink">{xg(r.modelled[s].xg.p10)}<span className="text-ink-4">–</span>{xg(r.modelled[s].xg.p90)}</div></div>
            <div className="ml-auto text-right text-[11.5px] leading-snug text-ink-3">Possession<br /><span className="text-ink-2">{pct(r.actual[s].possession)}</span> vs <span className="text-ink-2">{pct(r.modelled[s].possession.p10)}–{pct(r.modelled[s].possession.p90)}</span></div>
          </div>
          <BandChart r={r} side={s} />
        </div>
      ))}

      <div>
        <div className="mb-2 flex items-baseline justify-between">
          <span className="eyebrow">Comparable real situations</span>
          <span className="text-[11.5px] text-ink-4">{r.analogs.length} of {r.n_analogs}</span>
        </div>
        <ul className="overflow-hidden rounded-2xl bg-surface-2 ring-1 ring-line">
          {r.analogs.map((a, i) => (
            <li key={a.match_id + a.minute} className={`flex items-center gap-3 px-3.5 py-2.5 ${i ? "border-t border-line" : ""}`}>
              <span className="w-10 text-[12px] font-semibold tabular text-ai">{Math.round(a.similarity * 100)}%</span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] font-medium text-ink">{a.home} v {a.away}</div>
                <div className="text-[11.5px] text-ink-3">{a.competition} {a.season} · {a.minute}' · {a.score_state}</div>
              </div>
              <span className="text-[12px] tabular text-ink-2">{xg(a.next15.xg_for)}<span className="text-ink-4"> / </span>{xg(a.next15.xg_against)}</span>
            </li>
          ))}
        </ul>
      </div>
      <p className="text-[11.5px] leading-relaxed text-ink-4">{r.caveat}</p>
    </motion.div>
  );
}

function BandChart({ r, side }: { r: Counterfactual; side: Side }) {
  const W = 380, H = 96, P = { l: 2, r: 2, t: 8, b: 16 };
  const max = Math.max(...r.series.map((d) => Math.max(d.modelled[side].p90, d.actual[side])), 0.2);
  const x = scaleLinear().domain([0, r.horizon_minutes]).range([P.l, W - P.r]);
  const y = scaleLinear().domain([0, max]).nice().range([H - P.b, P.t]);
  type D = (typeof r.series)[number];
  const band = area<D>().x((d) => x(d.offset_min)).y0((d) => y(d.modelled[side].p10)).y1((d) => y(d.modelled[side].p90));
  const mid = line<D>().x((d) => x(d.offset_min)).y((d) => y(d.modelled[side].p50));
  const act = line<D>().x((d) => x(d.offset_min)).y((d) => y(d.actual[side]));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-3 w-full" role="img" aria-label="Cumulative xG: actual vs modelled range">
      <line x1={P.l} x2={W - P.r} y1={y(0)} y2={y(0)} stroke="var(--axis)" />
      <path d={band(r.series) ?? ""} fill="var(--ai)" opacity={0.16} />
      <path d={mid(r.series) ?? ""} fill="none" stroke="var(--ai)" strokeWidth={1.5} strokeDasharray="4 3" />
      <path d={act(r.series) ?? ""} fill="none" stroke={`var(--${side})`} strokeWidth={2.2} strokeLinecap="round" />
      <text x={P.l} y={H - 2} fontSize={10} fill="var(--ink-4)">{r.anchor.label}</text>
      <text x={W - P.r} y={H - 2} fontSize={10} fill="var(--ink-4)" textAnchor="end">+{r.horizon_minutes}'</text>
      <g fontSize={10} fill="var(--ink-3)">
        <line x1={W - 150} x2={W - 136} y1={P.t} y2={P.t} stroke={`var(--${side})`} strokeWidth={2} /><text x={W - 132} y={P.t + 3.5}>actual</text>
        <rect x={W - 90} y={P.t - 4} width={14} height={8} fill="var(--ai)" opacity={0.3} /><text x={W - 72} y={P.t + 3.5}>modelled</text>
      </g>
    </svg>
  );
}
