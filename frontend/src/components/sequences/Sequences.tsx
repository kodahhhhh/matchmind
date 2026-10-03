import { useMatch } from "../../store/match";
import { xg } from "../../lib/format";

export function Sequences() {
  const data = useMatch((s) => s.data);
  const focus = useMatch((s) => s.focus);
  const replay = useMatch((s) => s.replay);
  const focusSequence = useMatch((s) => s.focusSequence);
  const startReplay = useMatch((s) => s.startReplay);
  if (!data) return null;
  const max = Math.max(...data.sequences.map((s) => s.danger), 0.01);

  return (
    <div className="scroll-thin h-full overflow-y-auto px-5 py-5">
      <div className="mb-1 text-sm font-medium text-ink">Most dangerous sequences</div>
      <p className="mb-4 text-xs leading-relaxed text-ink-3">Ranked by the total value each move added to the attacking team's chance of scoring.</p>
      <ol className="space-y-2">
        {data.sequences.map((s, i) => {
          const active = focus?.kind === "sequence" && focus.id === s.id;
          const playing = replay?.sequenceId === s.id && replay.playing;
          return (
            <li key={s.id}>
              <div onClick={() => focusSequence(s.id)} role="button" tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && focusSequence(s.id)}
                className={`group cursor-pointer rounded-xl border px-3.5 py-3 transition ${active ? "border-line-strong bg-surface-3" : "border-line bg-surface-2/50 hover:border-line-strong"}`}>
                <div className="flex items-center gap-3">
                  <span className="font-display text-2xl font-semibold text-ink-4">{i + 1}</span>
                  <span className="h-8 w-1 rounded-full" style={{ background: `var(--${s.team})` }} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <span className="font-display text-base font-semibold tracking-wide">{s.start.label}</span>
                      <span className="text-xs text-ink-3">{data.match.teams[s.team].name}</span>
                      <Outcome o={s.outcome} />
                    </div>
                    <div className="truncate text-xs text-ink-2">{s.players.join(" → ")}</div>
                  </div>
                  <button onClick={(e) => { e.stopPropagation(); startReplay(s.id); }} aria-label="Replay sequence"
                    className="flex h-8 w-8 items-center justify-center rounded-full border border-line-strong text-ink-2 transition hover:bg-surface-3 hover:text-ink">
                    {playing ? <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-ink" /> :
                      <svg width="10" height="12" viewBox="0 0 10 12"><path d="M1 1 9 6 1 11z" fill="currentColor" /></svg>}
                  </button>
                </div>
                <div className="mt-2.5 flex items-center gap-3 text-[11px] text-ink-3">
                  <div className="h-1 flex-1 rounded-full bg-surface-3">
                    <div className="h-1 rounded-full" style={{ width: `${(s.danger / max) * 100}%`, background: `var(--${s.team})` }} />
                  </div>
                  <span className="tabular">{s.n_events} actions · {Math.round(s.duration)}s{s.xg > 0 ? ` · ${xg(s.xg)} xG` : ""}</span>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function Outcome({ o }: { o: "goal" | "shot" | "lost" }) {
  const cls = o === "goal" ? "border-ink/40 text-ink" : "border-line text-ink-3";
  return <span className={`rounded-full border px-1.5 py-[1px] text-[10px] uppercase tracking-wider ${cls}`}>{o === "lost" ? "lost ball" : o}</span>;
}
