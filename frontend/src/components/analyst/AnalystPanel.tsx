import { useEffect, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { resolveSequence, useMatch, type ChatMessage } from "../../store/match";
import { clock, describe, isShot, xg } from "../../lib/format";

const SUGGESTIONS: { q: string; sub: string; icon: ReactNode }[] = [
  { q: "Find the turning point", sub: "Where control of the match shifted", icon: <IconTrend /> },
  { q: "Who was actually progressing the ball?", sub: "Value added, not pass counts", icon: <IconArrow /> },
  { q: "Show me the three most dangerous sequences", sub: "Ranked by threat created", icon: <IconBolt /> },
  { q: "What changed after the substitutions?", sub: "Before vs after, both teams", icon: <IconSwap /> },
];

const TOOL_LABEL: Record<string, string> = {
  find_turning_points: "Searched for shifts in control",
  get_window_stats: "Computed window stats",
  get_events: "Pulled match events",
  get_top_sequences: "Ranked sequences",
  get_player_rankings: "Ranked players by value added",
  run_counterfactual: "Ran the game-state model",
  search_moments: "Searched commentary",
};

export function AnalystPanel() {
  const chat = useMatch((s) => s.chat);
  const ask = useMatch((s) => s.ask);
  const nEvents = useMatch((s) => s.data?.events.length ?? 0);
  const [draft, setDraft] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const busy = chat.some((m) => m.streaming);

  useEffect(() => {
    if (chat.length) scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [chat]);

  const submit = (q: string) => {
    if (!q.trim() || busy) return;
    void ask(q.trim());
    setDraft("");
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={scroller} className="scroll-thin min-h-0 flex-1 overflow-y-auto px-5 pb-4">
        {chat.length === 0 ? (
          <EmptyState onPick={submit} nEvents={nEvents} />
        ) : (
          <div className="space-y-6 pt-2">
            {chat.map((m) => (m.role === "user" ? <Question key={m.id} text={m.content} /> : <Answer key={m.id} m={m} />))}
          </div>
        )}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); submit(draft); }} className="p-3 pt-0">
        <div className="flex items-center gap-2 rounded-2xl bg-surface-2 py-1.5 pl-4 pr-1.5 ring-1 ring-line transition focus-within:ring-[var(--ai-line)]">
          <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Ask anything about this match"
            className="min-w-0 flex-1 bg-transparent py-1.5 text-[14px] text-ink placeholder:text-ink-4 focus:outline-none" />
          <button type="submit" disabled={busy || !draft.trim()} aria-label="Ask"
            className="ai-button flex h-9 w-9 items-center justify-center rounded-xl transition disabled:opacity-30 disabled:shadow-none">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 13V3M8 3 3.5 7.5M8 3l4.5 4.5" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </button>
        </div>
      </form>
    </div>
  );
}

function EmptyState({ onPick, nEvents }: { onPick: (q: string) => void; nEvents: number }) {
  return (
    <div className="pt-3">
      <div className="mb-5 flex items-start gap-3">
        <Orb />
        <div>
          <div className="text-[15px] font-semibold text-ink">Ask the analyst</div>
          <p className="mt-0.5 text-[13px] leading-relaxed text-ink-3">
            Answers are computed from all <span className="tabular text-ink-2">{nEvents.toLocaleString()}</span> match events, and every claim links to the moment it's based on.
          </p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2.5">
        {SUGGESTIONS.map((s, i) => (
          <motion.button key={s.q} onClick={() => onPick(s.q)} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 * i }}
            className="group flex flex-col items-start gap-3 rounded-2xl bg-surface-2 p-3.5 text-left ring-1 ring-line transition hover:bg-surface-3 hover:ring-[var(--ai-line)]">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-ai-soft text-ai">{s.icon}</span>
            <span>
              <span className="block text-[13.5px] font-semibold leading-snug text-ink">{s.q}</span>
              <span className="mt-1 block text-[12px] leading-snug text-ink-3">{s.sub}</span>
            </span>
          </motion.button>
        ))}
      </div>
      <MatchStory />
    </div>
  );
}

function MatchStory() {
  const data = useMatch((s) => s.data);
  const focusEvent = useMatch((s) => s.focusEvent);
  if (!data) return null;
  const names = new Map([...data.match.lineups.home, ...data.match.lineups.away].map((p) => [p.player_id, p.short_name]));
  const items = data.match.markers.filter((m) => m.type === "goal" || (m.type === "card" && m.detail !== "yellow"));
  let h = 0, a = 0;
  return (
    <div className="mt-6">
      <div className="eyebrow mb-2">Match story</div>
      <div className="overflow-hidden rounded-2xl bg-surface-2 ring-1 ring-line">
        {items.map((m, i) => {
          if (m.type === "goal") m.team === "home" ? h++ : a++;
          return (
            <button key={m.event_id} onClick={() => focusEvent(m.event_id)}
              className={`flex w-full items-center gap-3 px-3.5 py-2.5 text-left transition hover:bg-surface-3 ${i ? "border-t border-line" : ""}`}>
              <span className="display w-12 text-lg text-ink">{clock(m.period, m.minute)}</span>
              <span className="h-5 w-1 rounded-full" style={{ background: `var(--${m.team})` }} />
              <span className="flex-1 text-[13.5px] font-semibold text-ink">
                {m.detail === "own_goal" ? "Own goal" : names.get(m.player_id ?? -1)}
                <span className="ml-2 text-[12px] font-normal text-ink-3">{m.type === "card" ? "red card" : m.detail === "penalty" ? "penalty" : "goal"}</span>
              </span>
              {m.type === "goal" && <span className="display text-lg tabular text-ink-2">{h}–{a}</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Question({ text }: { text: string }) {
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex justify-end">
      <div className="max-w-[85%] rounded-2xl rounded-br-md bg-surface-3 px-4 py-2.5 text-[14px] font-medium text-ink">{text}</div>
    </motion.div>
  );
}

function Answer({ m }: { m: ChatMessage }) {
  const data = useMatch((s) => s.data);
  const refs = [...m.content.matchAll(/\[\[ev:([^\]]+)\]\]/g)].map((x) => x[1]);
  const moments = [...new Set(refs)].map((id) => data?.eventById.get(id)).filter((e): e is NonNullable<typeof e> => !!e);
  const thinking = m.streaming && !m.content;
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
      <Orb small pulse={m.streaming} />
      <div className="min-w-0 flex-1 space-y-3">
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          {m.tools.map((t, i) => (
            <span key={i} className="flex items-center gap-1.5 text-[12px] text-ink-3">
              <svg width="12" height="12" viewBox="0 0 12 12"><circle cx="6" cy="6" r="5.5" fill="var(--ai-soft)" /><path d="M3.6 6.2 5.2 7.8 8.4 4.4" stroke="var(--ai)" strokeWidth="1.4" fill="none" strokeLinecap="round" /></svg>
              {TOOL_LABEL[t] ?? t}
            </span>
          ))}
          {thinking && <span className="shimmer text-[12px] font-medium">{m.tools.length ? "Writing" : "Analysing the match"}</span>}
        </div>
        {m.content && (
          <div className="text-[15px] leading-[1.7] text-ink">
            <RichText text={m.content} />
            {m.streaming && <span className="ml-0.5 inline-block h-4 w-[2px] translate-y-[3px] animate-pulse bg-ai" />}
          </div>
        )}
        <AnimatePresence>
          {!m.streaming && moments.length > 0 && <Moments ids={moments.map((e) => e.id)} />}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

function Moments({ ids }: { ids: string[] }) {
  const data = useMatch((s) => s.data);
  const focusEvent = useMatch((s) => s.focusEvent);
  const focus = useMatch((s) => s.focus);
  if (!data) return null;
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
      <div className="eyebrow mb-2">Moments referenced</div>
      <div className="overflow-hidden rounded-2xl bg-surface-2 ring-1 ring-line">
        {ids.map((id, i) => {
          const e = data.eventById.get(id)!;
          const active = focus?.kind === "event" && focus.id === id;
          return (
            <button key={id} onClick={() => focusEvent(id)}
              className={`flex w-full items-center gap-3 px-3.5 py-2.5 text-left transition ${i ? "border-t border-line" : ""} ${active ? "bg-surface-4" : "hover:bg-surface-3"}`}>
              <span className="display w-12 text-lg text-ink">{clock(e.period, e.minute)}</span>
              <span className="h-6 w-1 rounded-full" style={{ background: `var(--${e.team})` }} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13.5px] font-semibold text-ink">{e.player}</span>
                <span className="block text-[12px] text-ink-3">{describe(e).replace(/^\S+\s/, "").replace(e.player ?? "", "").trim() || e.type}</span>
              </span>
              {isShot(e.type) && <span className="tabular text-[12px] text-ink-2"><span className="font-semibold text-ink">{xg(e.xg)}</span> xG</span>}
              <svg width="14" height="14" viewBox="0 0 14 14" className="text-ink-4"><path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" /></svg>
            </button>
          );
        })}
      </div>
    </motion.div>
  );
}

/** Minimal markdown (paragraphs, bullet/numbered lists, **bold**, *italic*) with [[ev:id]] / [[seq:id]] citation chips.
 *  A half-streamed trailing token is hidden until it completes. */
function RichText({ text }: { text: string }) {
  const clean = text.replace(/\[\[[^\]]*$/, "").replace(/\*\*?$/, "");
  const blocks: { kind: "p" | "ul" | "ol"; lines: string[] }[] = [];
  for (const raw of clean.split("\n")) {
    const line = raw.trimEnd();
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
    const num = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    const last = blocks[blocks.length - 1];
    if (bullet || num) {
      const kind = bullet ? "ul" : "ol";
      const content = (bullet ?? num)![1];
      if (last?.kind === kind) last.lines.push(content);
      else blocks.push({ kind, lines: [content] });
    } else if (!line.trim()) {
      blocks.push({ kind: "p", lines: [] });
    } else if (last?.kind === "p" && last.lines.length) {
      last.lines.push(line);
    } else {
      blocks.push({ kind: "p", lines: [line] });
    }
  }
  const visible = blocks.filter((b) => b.lines.length);
  return (
    <div className="space-y-3">
      {visible.map((b, i) =>
        b.kind === "p" ? <p key={i}><Inline text={b.lines.join(" ")} /></p>
        : b.kind === "ul" ? <ul key={i} className="space-y-1.5">{b.lines.map((l, j) => (
            <li key={j} className="flex gap-2.5"><span className="mt-[10px] h-1 w-1 shrink-0 rounded-full bg-ink-3" /><span><Inline text={l} /></span></li>
          ))}</ul>
        : <ol key={i} className="space-y-1.5">{b.lines.map((l, j) => (
            <li key={j} className="flex gap-2.5"><span className="display mt-[1px] w-4 shrink-0 text-ink-3">{j + 1}</span><span><Inline text={l} /></span></li>
          ))}</ol>,
      )}
    </div>
  );
}

function Inline({ text }: { text: string }) {
  const data = useMatch((s) => s.data);
  const focusEvent = useMatch((s) => s.focusEvent);
  const focusSequence = useMatch((s) => s.focusSequence);
  const parts: ReactNode[] = [];
  const re = /\[\[(ev|seq):([^\]]+)\]\]|\*\*([^*]+)\*\*|\*([^*\s][^*]*)\*/g;
  let last = 0;
  let mm: RegExpExecArray | null;
  while ((mm = re.exec(text))) {
    parts.push(text.slice(last, mm.index));
    const [, kind, id, bold, italic] = mm;
    if (bold) parts.push(<strong key={mm.index} className="font-semibold text-ink">{bold}</strong>);
    else if (italic) parts.push(<em key={mm.index} className="text-ink-2">{italic}</em>);
    else if (kind === "ev") {
      const e = data?.eventById.get(id);
      parts.push(<Chip key={mm.index} side={e?.team} onClick={() => focusEvent(id)}>{e ? describe(e) : "event"}</Chip>);
    } else {
      const s = resolveSequence(data, id);
      parts.push(<Chip key={mm.index} side={s?.team} onClick={() => s && focusSequence(id)}>{s ? `${s.start.label} ${s.players[0] ?? ""} move`.replace(/\s+/g, " ") : "move"}</Chip>);
    }
    last = mm.index + mm[0].length;
  }
  parts.push(text.slice(last));
  return <>{parts}</>;
}

function Chip({ children, side, onClick }: { children: ReactNode; side?: "home" | "away"; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className="mx-0.5 inline-flex translate-y-[-1px] items-center gap-1.5 rounded-lg bg-surface-3 px-2 py-[2px] align-middle text-[13px] font-semibold text-ink ring-1 ring-white/10 transition hover:bg-ai-soft hover:ring-[var(--ai-line)]">
      <span className="h-2 w-2 rounded-full" style={{ background: side ? `var(--${side})` : "var(--ink-3)" }} />
      {children}
    </button>
  );
}

function Orb({ small, pulse }: { small?: boolean; pulse?: boolean }) {
  const s = small ? 26 : 36;
  return (
    <span className="relative shrink-0" style={{ width: s, height: s }}>
      {pulse && <span className="absolute inset-0 animate-ping rounded-full bg-ai opacity-25" />}
      <span className="absolute inset-0 rounded-full" style={{ background: "radial-gradient(circle at 30% 30%, #d9cfff, #8f7dff 45%, #4b3cc4 100%)", boxShadow: "0 0 18px rgba(143,125,255,0.45)" }} />
    </span>
  );
}

function IconTrend() {
  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M1.5 11.5 5.5 7.5l3 3 6-6.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}
function IconArrow() {
  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M2 8h11M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}
function IconBolt() {
  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M9 1.5 3.5 9H8l-1 5.5L12.5 7H8l1-5.5Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /></svg>;
}
function IconSwap() {
  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M4 2v11M4 13l-2.5-2.5M4 13l2.5-2.5M12 14V3M12 3 9.5 5.5M12 3l2.5 2.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}
