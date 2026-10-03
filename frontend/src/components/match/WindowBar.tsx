import { useMemo } from "react";
import type { Side } from "../../api/types";
import { useMatch } from "../../store/match";
import { pct, xg } from "../../lib/format";
import { usePitchEvents } from "../pitch/Pitch";

/** Glass overlays on the pitch: what's shown (top-left) and window stats (top-right). */
export function PitchOverlays() {
  const data = useMatch((s) => s.data);
  const win = useMatch((s) => s.window);
  const focus = useMatch((s) => s.focus);
  const setWindow = useMatch((s) => s.setWindow);
  const setFocus = useMatch((s) => s.setFocus);
  const stopReplay = useMatch((s) => s.stopReplay);
  const focusTurningPoint = useMatch((s) => s.focusTurningPoint);
  const { mode, events, seq } = usePitchEvents();
  const caption = useMatch((st) => (seq ? st.commentaryBySeq.get(seq.id) : undefined));

  const stats = useMemo(() => {
    if (!data) return null;
    const rows = win ? data.timeline.slice(win.from, win.to + 1) : data.timeline;
    const sum = (s: Side, k: "shots" | "xg") => rows.reduce((a, m) => a + m[s][k], 0);
    const avg = (s: Side, k: "possession" | "field_tilt") => rows.reduce((a, m) => a + m[s][k], 0) / Math.max(rows.length, 1);
    return {
      label: win ? `${rows[0]?.label} – ${rows[rows.length - 1]?.label}` : "Full match",
      rows: [
        { label: "Possession", a: avg("home", "possession"), b: avg("away", "possession"), fmt: (v: number) => pct(v), share: true },
        { label: "Field tilt", a: avg("home", "field_tilt"), b: avg("away", "field_tilt"), fmt: (v: number) => pct(v), share: true },
        { label: "xG", a: sum("home", "xg"), b: sum("away", "xg"), fmt: xg, share: false },
        { label: "Shots", a: sum("home", "shots"), b: sum("away", "shots"), fmt: (v: number) => String(v), share: false },
      ],
    };
  }, [data, win]);
  if (!data || !stats) return null;
  const turning = focus?.kind === "turning";
  const { home, away } = data.match.teams;
  const what = mode === "sequence"
    ? `Sequence · ${seq?.start.label} ${data.match.teams[seq!.team].name}`
    : mode === "detail" ? `${events.length} actions` : "Shot map";
  const reset = () => { setWindow(null); setFocus(null); stopReplay(); };

  return (
    <>
      <div className="pointer-events-none absolute left-4 top-4 flex items-center gap-2">
        <div className="glass pointer-events-auto flex items-center gap-3 rounded-2xl py-2 pl-3.5 pr-2">
          <div>
            <div className={`text-[10px] font-semibold uppercase tracking-[0.16em] ${turning ? "text-ai" : "text-ink-3"}`}>{turning ? "Turning point" : "Showing"}</div>
            <div className="display text-[19px] leading-tight text-ink">{stats.label}</div>
          </div>
          <span className="h-7 w-px bg-white/10" />
          <span className="text-xs text-ink-2">{what}</span>
          {(win || focus) && (
            <button onClick={reset} className="ml-1 rounded-lg bg-white/8 px-2.5 py-1 text-xs font-medium text-ink-2 transition hover:bg-white/15 hover:text-ink">
              Full match
            </button>
          )}
        </div>
        {turning && data.turningPoints.length > 1 && (
          <div className="glass pointer-events-auto flex items-center gap-1 rounded-2xl p-1.5">
            <span className="px-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-3">Shifts</span>
            {data.turningPoints.map((tp) => {
              const on = focus?.kind === "turning" && focus.id === tp.id;
              return (
                <button key={tp.id} onClick={() => focusTurningPoint(tp.id)}
                  className={`flex items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-[12px] font-semibold transition ${on ? "bg-ai text-bg" : "text-ink-2 hover:bg-white/10"}`}>
                  <span className="h-2 w-2 rounded-full" style={{ background: `var(--${tp.team_gaining})` }} />
                  {tp.start.label}
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className={`glass pointer-events-none absolute bottom-4 right-4 flex items-center gap-4 rounded-2xl px-4 py-2.5 transition-opacity ${mode === "sequence" ? "opacity-0" : ""}`}>
        <div className="flex flex-col gap-1 text-[10.5px] font-bold tracking-wider">
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-home" />{home.short}</span>
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-away" />{away.short}</span>
        </div>
        {stats.rows.map((r) => {
          const total = r.share ? 1 : r.a + r.b || 1;
          return (
            <div key={r.label} className="w-[78px]">
              <div className="mb-1 text-[10px] text-ink-3">{r.label}</div>
              <div className="flex items-baseline justify-between text-[12.5px] font-bold tabular text-ink">
                <span>{r.fmt(r.a)}</span><span className="text-ink-2">{r.fmt(r.b)}</span>
              </div>
              <div className="mt-1 flex h-[4px] gap-[2px]">
                <div className="rounded-full transition-all duration-500" style={{ width: `${(r.a / total) * 100}%`, background: "var(--home)" }} />
                <div className="flex-1 rounded-full transition-all duration-500" style={{ background: "var(--away)", opacity: r.b === 0 && !r.share ? 0.15 : 1 }} />
              </div>
            </div>
          );
        })}
      </div>

      {mode === "sequence" && caption && (
        <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center px-4">
          <div className="glass flex max-w-[720px] items-stretch overflow-hidden rounded-2xl">
            <span className="w-1.5 shrink-0" style={{ background: `var(--${caption.team})` }} />
            <div className="px-4 py-2.5">
              <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-3">
                <span className="display text-[14px] tracking-normal text-ink">{caption.start.label}</span>
                {data.match.teams[caption.team].name}
                <span className="ml-1 flex items-center gap-1 normal-case tracking-normal text-ink-4"><span className="h-1 w-1 rounded-full bg-ai" />Luna</span>
              </div>
              <div className="mt-0.5 text-[14.5px] font-medium leading-snug text-ink">{caption.text}</div>
            </div>
          </div>
        </div>
      )}

      <div className={`glass pointer-events-none absolute bottom-4 left-4 flex items-center gap-3 rounded-xl px-3 py-2 text-[11px] text-white/75 ${mode === "sequence" && caption ? "hidden" : ""}`}>
        <span className="flex items-center gap-1.5"><svg width="12" height="12"><circle cx="6" cy="6" r="4.5" fill="rgba(255,255,255,0.25)" stroke="#fff" strokeWidth="1" /></svg>shot · size = xG</span>
        <span className="flex items-center gap-1.5"><svg width="12" height="12"><circle cx="6" cy="6" r="5" fill="#fff" /><circle cx="6" cy="6" r="1.8" fill="#1a4a30" /></svg>goal</span>
        {mode !== "overview" && <span className="flex items-center gap-1.5"><svg width="18" height="8"><line x1="1" y1="4" x2="17" y2="4" stroke="#fff" strokeWidth="1.5" /></svg>pass</span>}
        {mode !== "overview" && <span className="flex items-center gap-1.5"><svg width="18" height="8"><line x1="1" y1="4" x2="17" y2="4" stroke="#fff" strokeWidth="1.5" strokeDasharray="1 3" strokeLinecap="round" /></svg>carry</span>}
      </div>
    </>
  );
}
