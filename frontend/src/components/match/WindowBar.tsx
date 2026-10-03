import { useMemo } from "react";
import type { Side } from "../../api/types";
import { useMatch } from "../../store/match";
import { pct, xg } from "../../lib/format";

/** Stats for the selected window, home vs away, as split bars. */
export function WindowBar() {
  const data = useMatch((s) => s.data);
  const win = useMatch((s) => s.window);
  const setWindow = useMatch((s) => s.setWindow);
  const setFocus = useMatch((s) => s.setFocus);
  const turning = useMatch((s) => s.focus?.kind === "turning");

  const stats = useMemo(() => {
    if (!data) return null;
    const rows = win ? data.timeline.slice(win.from, win.to + 1) : data.timeline;
    const sum = (s: Side, k: "passes" | "shots" | "xg") => rows.reduce((a, m) => a + m[s][k], 0);
    const avg = (s: Side, k: "possession" | "field_tilt") => rows.reduce((a, m) => a + m[s][k], 0) / Math.max(rows.length, 1);
    return {
      label: win ? `${rows[0]?.label} – ${rows[rows.length - 1]?.label}` : "Full match",
      possession: [avg("home", "possession"), avg("away", "possession")] as const,
      tilt: [avg("home", "field_tilt"), avg("away", "field_tilt")] as const,
      xg: [sum("home", "xg"), sum("away", "xg")] as const,
      shots: [sum("home", "shots"), sum("away", "shots")] as const,
    };
  }, [data, win]);
  if (!stats) return null;

  return (
    <div className="flex items-center gap-5 px-1">
      <div className="min-w-[118px]">
        {turning
          ? <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ai">Turning point</div>
          : <div className="text-[10px] uppercase tracking-[0.16em] text-ink-3">Window</div>}
        <div className="font-display text-lg font-semibold tracking-wide">{stats.label}</div>
      </div>
      <Split label="Possession" a={stats.possession[0]} b={stats.possession[1]} fmt={(v) => pct(v)} share />
      <Split label="Field tilt" a={stats.tilt[0]} b={stats.tilt[1]} fmt={(v) => pct(v)} share />
      <Split label="xG" a={stats.xg[0]} b={stats.xg[1]} fmt={xg} />
      <Split label="Shots" a={stats.shots[0]} b={stats.shots[1]} fmt={(v) => String(v)} />
      {win && (
        <button onClick={() => { setWindow(null); setFocus(null); }}
          className="ml-auto rounded-lg border border-line px-3 py-1.5 text-xs text-ink-2 transition hover:border-line-strong hover:text-ink">
          Full match
        </button>
      )}
    </div>
  );
}

function Split({ label, a, b, fmt, share }: { label: string; a: number; b: number; fmt: (v: number) => string; share?: boolean }) {
  const total = share ? 1 : a + b || 1;
  const wa = (a / total) * 100;
  return (
    <div className="min-w-0 flex-1">
      <div className="mb-1 text-center text-[10px] uppercase tracking-[0.14em] text-ink-3">{label}</div>
      <div className="flex items-center gap-2 text-xs">
        <span className="w-9 text-right tabular font-semibold text-ink">{fmt(a)}</span>
        <div className="flex h-1.5 min-w-0 flex-1 gap-[2px] overflow-hidden rounded-full">
          <div className="rounded-l-full transition-all duration-500" style={{ width: `${wa}%`, background: "var(--home)" }} />
          <div className="flex-1 rounded-r-full transition-all duration-500" style={{ background: "var(--away)" }} />
        </div>
        <span className="w-9 tabular font-semibold text-ink">{fmt(b)}</span>
      </div>
    </div>
  );
}
