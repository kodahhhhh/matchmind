import { useEffect, useRef, useState, type ReactNode } from "react";
import { motion } from "motion/react";
import { useMatch, type ChatMessage } from "../../store/match";
import { describe } from "../../lib/format";

const SUGGESTIONS = [
  "Find the turning point",
  "Who was actually progressing the ball?",
  "Show me the three most dangerous sequences",
  "What changed after the substitutions?",
];

const TOOL_LABEL: Record<string, string> = {
  find_turning_points: "Searched for regime changes",
  get_window_stats: "Computed window stats",
  get_events: "Pulled match events",
  get_top_sequences: "Ranked sequences by danger",
  get_player_rankings: "Ranked players by value added",
  run_counterfactual: "Ran the game-state model",
  search_moments: "Searched match commentary",
};

export function AnalystPanel() {
  const chat = useMatch((s) => s.chat);
  const ask = useMatch((s) => s.ask);
  const [draft, setDraft] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const busy = chat.some((m) => m.streaming);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [chat]);

  const submit = (q: string) => {
    if (!q.trim() || busy) return;
    void ask(q.trim());
    setDraft("");
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={scroller} className="scroll-thin min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-5">
        {chat.length === 0 ? (
          <EmptyState onPick={submit} />
        ) : (
          chat.map((m) => (m.role === "user" ? <UserBubble key={m.id} text={m.content} /> : <Answer key={m.id} m={m} />))
        )}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); submit(draft); }} className="border-t border-line p-3">
        <div className="flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-3 py-2 focus-within:border-[var(--ai-line)]">
          <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Ask about this match…"
            className="min-w-0 flex-1 bg-transparent text-sm text-ink placeholder:text-ink-4 focus:outline-none" />
          <button type="submit" disabled={busy || !draft.trim()}
            className="rounded-lg bg-ai px-3 py-1 text-xs font-semibold text-bg transition disabled:opacity-30">
            Ask
          </button>
        </div>
      </form>
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="pt-4">
      <div className="mb-1 flex items-center gap-2 text-sm font-medium text-ink">
        <span className="h-1.5 w-1.5 rounded-full bg-ai shadow-[0_0_10px_var(--ai)]" />
        Ask the analyst
      </div>
      <p className="mb-5 text-sm leading-relaxed text-ink-3">
        Every answer is computed from the match events and cites the moments it's based on. Click a citation to jump the pitch there.
      </p>
      <div className="flex flex-col gap-2">
        {SUGGESTIONS.map((s) => (
          <button key={s} onClick={() => onPick(s)}
            className="rounded-xl border border-line bg-surface-2/60 px-3.5 py-2.5 text-left text-sm text-ink-2 transition hover:border-[var(--ai-line)] hover:bg-ai-soft hover:text-ink">
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-2xl rounded-br-md bg-surface-3 px-3.5 py-2 text-sm text-ink">{text}</div>
    </div>
  );
}

function Answer({ m }: { m: ChatMessage }) {
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
      {m.tools.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {m.tools.map((t, i) => (
            <span key={i} className="flex items-center gap-1.5 rounded-full border border-line px-2.5 py-0.5 text-[11px] text-ink-3">
              <svg width="10" height="10" viewBox="0 0 10 10"><path d="M2 5.2 4.2 7.4 8 3" stroke="var(--ai)" strokeWidth="1.5" fill="none" strokeLinecap="round" /></svg>
              {TOOL_LABEL[t] ?? t}
            </span>
          ))}
        </div>
      )}
      <div className="text-[14.5px] leading-[1.65] text-ink">
        <RichText text={m.content} />
        {m.streaming && <span className="ml-0.5 inline-block h-4 w-[2px] translate-y-[3px] animate-pulse bg-ai" />}
      </div>
    </motion.div>
  );
}

/** Renders [[ev:id]] / [[seq:id]] as clickable chips; hides a half-streamed trailing token. */
function RichText({ text }: { text: string }) {
  const data = useMatch((s) => s.data);
  const focusEvent = useMatch((s) => s.focusEvent);
  const focusSequence = useMatch((s) => s.focusSequence);
  const clean = text.replace(/\[\[[^\]]*$/, "");
  const parts: ReactNode[] = [];
  const re = /\[\[(ev|seq):([^\]]+)\]\]/g;
  let last = 0;
  let mm: RegExpExecArray | null;
  while ((mm = re.exec(clean))) {
    parts.push(clean.slice(last, mm.index));
    const [, kind, id] = mm;
    if (kind === "ev") {
      const e = data?.eventById.get(id);
      parts.push(
        <Chip key={mm.index} side={e?.team} onClick={() => focusEvent(id)}>{e ? describe(e) : "event"}</Chip>,
      );
    } else {
      const s = data?.sequences.find((x) => x.id === id);
      parts.push(<Chip key={mm.index} side={s?.team} onClick={() => focusSequence(id)}>{s ? `${s.start.label} sequence` : "sequence"}</Chip>);
    }
    last = mm.index + mm[0].length;
  }
  parts.push(clean.slice(last));
  return <>{parts}</>;
}

function Chip({ children, side, onClick }: { children: ReactNode; side?: "home" | "away"; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className="mx-0.5 inline-flex translate-y-[-1px] items-center gap-1.5 rounded-md border border-line-strong bg-surface-3 px-1.5 py-[1px] align-middle text-[12.5px] font-medium text-ink transition hover:border-[var(--ai-line)] hover:bg-ai-soft">
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: side ? `var(--${side})` : "var(--ink-3)" }} />
      {children}
    </button>
  );
}
