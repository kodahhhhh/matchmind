import { useEffect, useState } from "react";
import { scaleLinear } from "d3-scale";
import { area, line } from "d3-shape";
import { motion } from "motion/react";
import { api } from "../../api/client";
import type { Counterfactual, Marker, Side } from "../../api/types";
import { useMatch } from "../../store/match";
import { clock, pct, xg } from "../../lib/format";

const CHANGE: Record<string, { change: Counterfactual["change"]; verb: string }> = {
  goal: { change: "remove_goal", verb: "doesn't happen" },
  sub: { change: "no_sub", verb: "isn't made" },
  card: { change: "remove_red_card", verb: "isn't shown" },
};

export function WhatIf() {
  const data = useMatch((s) => s.data);
  const focusEvent = useMatch((s) => s.focusEvent);
  const [picked, setPicked] = useState<Marker | null>(null);
  const [result, setResult] = useState<Counterfactual | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!picked || !data) return;
    let live = true;
    setLoading(true);
    api.counterfactual(data.match.match_id, picked.event_id, CHANGE[picked.type].change)
      .then((r) => live && setResult(r))
      .finally(() => live && setLoading(false));
    return () => { live = false; };
  }, [picked, data]);

  if (!data) return null;
  const nameOf = (id: number | null | undefined) =>
    [...data.match.lineups.home, ...data.match.lineups.away].find((p) => p.player_id === id)?.short_name ?? "Unknown";
  const options = data.match.markers.filter((m) => m.type === "goal" || m.type === "sub" || (m.type === "card" && m.detail !== "yellow"));
  const title = (m: Marker) =>
    m.type === "goal" ? `${nameOf(m.player_id)} goal` : m.type === "sub" ? `${nameOf(m.player_off_id)} off, ${nameOf(m.player_id)} on` : `${nameOf(m.player_id)} red card`;

  return (
    <div className="scroll-thin h-full overflow-y-auto px-5 py-5">
      <div className="mb-1 flex items-center gap-2">
        <span className="text-sm font-medium text-ink">What if…</span>
        <span className="rounded-full border border-[var(--ai-line)] bg-ai-soft px-2 py-[1px] text-[10px] font-semibold uppercase tracking-wider text-ai">Modelled hypothetical</span>
      </div>
      <p className="mb-4 text-xs leading-relaxed text-ink-3">Pick a moment and remove it. A model trained on 2,924 matches estimates a range for the next 15 minutes, next to real situations that looked the same.</p>

      {([["Goals", options.filter((m) => m.type !== "sub")], ["Substitutions", options.filter((m) => m.type === "sub")]] as const).map(([group, ms]) =>
        ms.length > 0 && (
          <div key={group} className="mb-4">
            <div className="mb-1.5 text-[10px] uppercase tracking-[0.14em] text-ink-3">{group}</div>
            <div className="flex flex-wrap gap-1.5">
              {ms.map((m) => (
                <button key={m.event_id + m.type} onClick={() => { setPicked(m); focusEvent(m.event_id); }}
                  className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition ${picked?.event_id === m.event_id ? "border-line-strong bg-surface-3 text-ink" : "border-line text-ink-2 hover:border-line-strong"}`}>
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: `var(--${m.team})` }} />
                  <span className="tabular text-ink-3">{clock(m.period, m.minute)}</span> {title(m)}
                </button>
              ))}
            </div>
          </div>
        ))}

      {picked && (
        <div className={loading ? "opacity-50 transition" : "transition"}>
          <div className="mb-4 font-display text-xl font-semibold leading-snug tracking-wide">
            What if the {title(picked)} {CHANGE[picked.type].verb}?
          </div>
          {result && <Result r={result} />}
        </div>
      )}
    </div>
  );
}

function Result({ r }: { r: Counterfactual }) {
  const teams = useMatch((s) => s.data!.match.teams);
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-5">
      <div className="grid grid-cols-2 gap-3">
        {(["home", "away"] as Side[]).map((s) => (
          <div key={s} className="rounded-xl border border-line bg-surface-2/60 p-3">
            <div className="mb-2 flex items-center gap-2 text-xs text-ink-2">
              <span className="h-2 w-2 rounded-full" style={{ background: `var(--${s})` }} />{teams[s].name} · next {r.horizon_minutes}'
            </div>
            <BandChart r={r} side={s} />
            <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
              <div><div className="text-ink-3">Actual xG</div><div className="text-base font-semibold tabular text-ink">{xg(r.actual[s].xg)}</div></div>
              <div><div className="text-ink-3">Modelled</div><div className="text-base font-semibold tabular text-ink">{xg(r.modelled[s].xg.p10)}–{xg(r.modelled[s].xg.p90)}</div></div>
            </div>
            <div className="mt-1 text-[11px] text-ink-3">Possession {pct(r.actual[s].possession)} actual · {pct(r.modelled[s].possession.p10)}–{pct(r.modelled[s].possession.p90)} modelled</div>
          </div>
        ))}
      </div>

      <div>
        <div className="mb-2 flex items-baseline justify-between">
          <span className="text-xs font-medium text-ink">Comparable real situations</span>
          <span className="text-[11px] text-ink-3">{r.analogs.length} of {r.n_analogs} closest</span>
        </div>
        <ul className="divide-y divide-line rounded-xl border border-line">
          {r.analogs.map((a) => (
            <li key={a.match_id + a.minute} className="flex items-center gap-3 px-3 py-2 text-xs">
              <span className="w-9 tabular text-ink-3">{Math.round(a.similarity * 100)}%</span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-ink">{a.home} v {a.away}</div>
                <div className="text-[11px] text-ink-3">{a.competition} {a.season} · {a.minute}' · {a.score_state}</div>
              </div>
              <span className="tabular text-ink-2">{xg(a.next15.xg_for)}<span className="text-ink-4"> – </span>{xg(a.next15.xg_against)}</span>
            </li>
          ))}
        </ul>
      </div>
      <p className="rounded-xl border border-line bg-surface-2/40 p-3 text-[11px] leading-relaxed text-ink-3">{r.caveat}</p>
    </motion.div>
  );
}

function BandChart({ r, side }: { r: Counterfactual; side: Side }) {
  const W = 220, H = 92, P = { l: 4, r: 4, t: 6, b: 16 };
  const max = Math.max(...r.series.map((d) => Math.max(d.modelled[side].p90, d.actual[side])), 0.2);
  const x = scaleLinear().domain([0, r.horizon_minutes]).range([P.l, W - P.r]);
  const y = scaleLinear().domain([0, max]).nice().range([H - P.b, P.t]);
  const band = area<(typeof r.series)[number]>().x((d) => x(d.offset_min)).y0((d) => y(d.modelled[side].p10)).y1((d) => y(d.modelled[side].p90));
  const mid = line<(typeof r.series)[number]>().x((d) => x(d.offset_min)).y((d) => y(d.modelled[side].p50));
  const act = line<(typeof r.series)[number]>().x((d) => x(d.offset_min)).y((d) => y(d.actual[side]));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Cumulative xG: actual vs modelled range">
      <line x1={P.l} x2={W - P.r} y1={y(0)} y2={y(0)} stroke="var(--axis)" />
      <path d={band(r.series) ?? ""} fill="var(--ai)" opacity={0.14} />
      <path d={mid(r.series) ?? ""} fill="none" stroke="var(--ai)" strokeWidth={1.5} strokeDasharray="4 3" />
      <path d={act(r.series) ?? ""} fill="none" stroke={`var(--${side})`} strokeWidth={2} strokeLinecap="round" />
      <text x={P.l} y={H - 3} fontSize={9} fill="var(--ink-4)">{r.anchor.label}</text>
      <text x={W - P.r} y={H - 3} fontSize={9} fill="var(--ink-4)" textAnchor="end">+{r.horizon_minutes}'</text>
    </svg>
  );
}
