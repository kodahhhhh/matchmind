import { useMemo, type ComponentProps, type ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import type { Components } from "streamdown";
import { ArrowRight, ArrowsDownUp, CaretRight, Lightning, Play, Question as QuestionIcon, TrendUp } from "@phosphor-icons/react";
import { Conversation, ConversationContent, ConversationScrollButton } from "@/components/ai-elements/conversation";
import { Message, MessageContent, MessageResponse } from "@/components/ai-elements/message";
import {
  PromptInput, PromptInputBody, PromptInputFooter, PromptInputSubmit, PromptInputTextarea, PromptInputTools,
} from "@/components/ai-elements/prompt-input";
import { Reasoning, ReasoningContent, ReasoningTrigger } from "@/components/ai-elements/reasoning";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { Suggestion, Suggestions } from "@/components/ai-elements/suggestion";
import { Tool, ToolContent, ToolHeader } from "@/components/ai-elements/tool";
import { resolveSequence, useMatch, type AgentStep, type ChatMessage } from "../../store/match";
import { clock, describe, isShot, undash } from "../../lib/format";

const EASE = [0.22, 1, 0.36, 1] as const;

const STARTERS: { q: string; sub: string; icon: ReactNode }[] = [
  { q: "Find the turning point", sub: "When did the match swing?", icon: <TrendUp size={16} weight="bold" /> },
  { q: "Who was actually progressing the ball?", sub: "Who moved the team forward", icon: <ArrowRight size={16} weight="bold" /> },
  { q: "Show me the three most dangerous sequences", sub: "The attacks closest to a goal", icon: <Lightning size={16} weight="bold" /> },
  { q: "What changed after the substitutions?", sub: "Did the changes work?", icon: <ArrowsDownUp size={16} weight="bold" /> },
];
const FOLLOW_UPS = [
  ...STARTERS.map((s) => s.q),
  "What if the first goal never happened?",
  "Should the last big chance have been a pass instead of a shot?",
];

/** What each tool does, in words a fan would use. */
const STEP_TITLE: Record<string, string> = {
  find_turning_points: "Finding where the match swung",
  get_window_stats: "Comparing both teams over a stretch of play",
  get_events: "Looking up what happened",
  get_top_sequences: "Ranking the most dangerous attacks",
  get_player_rankings: "Ranking the players",
  get_player_profile: "Reading up on a player",
  run_counterfactual: "Running the what-if model",
  shot_alternatives: "Checking the passes that were on",
  search_moments: "Searching the commentary",
  get_commentary: "Reading the match commentary",
};

export function AnalystPanel() {
  const chat = useMatch((s) => s.chat);
  const ask = useMatch((s) => s.ask);
  const stop = useMatch((s) => s.stopAsking);
  const busy = chat.some((m) => m.streaming);
  const status = useAnnouncement(chat);

  const submit = (q: string) => {
    if (!q.trim() || busy) return;
    void ask(q.trim());
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <Conversation className="min-h-0 flex-1">
        <ConversationContent className="gap-7 px-5 pb-4 pt-2">
          {chat.length === 0
            ? <EmptyState onPick={submit} />
            : chat.map((m) => (m.role === "user" ? <UserTurn key={m.id} text={m.content} /> : <AgentTurn key={m.id} m={m} />))}
        </ConversationContent>
        <ConversationScrollButton className="bg-surface-3 text-ink ring-1 ring-line hover:bg-surface-4" />
      </Conversation>
      <p role="status" aria-live="polite" className="sr-only">{status}</p>
      <div className="p-3 pt-0">
        <PromptInput onSubmit={({ text }) => submit(text)}
          className="rounded-2xl bg-surface-2 ring-1 ring-line transition-[box-shadow] focus-within:ring-2 focus-within:ring-[var(--ai-line)] [&_[data-slot=input-group]]:border-0 [&_[data-slot=input-group]]:bg-transparent [&_[data-slot=input-group]]:shadow-none">
          <PromptInputBody>
            <PromptInputTextarea placeholder="Ask anything about this match" aria-label="Ask the analyst about this match"
              className="min-h-11 text-base text-ink placeholder:text-ink-3 sm:text-[14px]" />
          </PromptInputBody>
          <PromptInputFooter>
            <PromptInputTools>
              <span className="px-1 text-[12px] text-ink-3">{busy ? "The analyst is working. Press stop to cancel." : "Answers use only this match's data."}</span>
            </PromptInputTools>
            <PromptInputSubmit status={busy ? "streaming" : undefined} aria-label={busy ? "Stop the answer" : "Send question"}
              onClick={busy ? (e) => { e.preventDefault(); stop(); } : undefined}
              className="ai-button rounded-full text-ink" />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </div>
  );
}

/** Polite screen-reader status: says when the analyst starts working and reads the finished answer once. */
function useAnnouncement(chat: ChatMessage[]): string {
  const data = useMatch((s) => s.data);
  const last = [...chat].reverse().find((m) => m.role === "assistant");
  if (!last) return "";
  if (last.streaming) return "The analyst is working on an answer.";
  const plain = last.content
    .replace(/\[\[(ev|seq):([^\]]+)\]\]/g, (_, kind: string, id: string) => {
      const label = last.labels[`${kind}:${id}`];
      if (label) return label;
      const e = kind === "ev" ? data?.eventById.get(id) : undefined;
      return e ? describe(e) : "a moment";
    })
    .replace(/[*_]/g, "");
  return `Answer ready. ${undash(plain)}`;
}

function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  const reduce = useReducedMotion();
  return (
    <div className="pt-3">
      <div className="mb-5 flex items-start gap-3">
        <Orb />
        <div className="min-w-0">
          <h2 className="text-[16px] font-semibold leading-snug tracking-[-0.015em] text-ink">Ask the analyst</h2>
          <p className="mt-1 text-pretty text-[13.5px] leading-[1.55] text-ink-3">
            Ask in your own words. The analyst looks things up in the match data, shows you each step, and links every claim to the moment on the pitch.
          </p>
        </div>
      </div>
      <ul className="grid grid-cols-2 gap-2.5">
        {STARTERS.map((s, i) => (
          <motion.li key={s.q} initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6, filter: "blur(2px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            transition={{ duration: 0.3, delay: 0.04 * i, ease: EASE }}>
            <button type="button" onClick={() => onPick(s.q)}
              className="group flex h-full w-full flex-col items-start gap-3 rounded-2xl bg-surface-2 p-3.5 text-left ring-1 ring-line transition-[background-color,box-shadow,transform] duration-150 ease-out hover:bg-surface-3 hover:ring-[var(--ai-line)] active:scale-[0.97]">
              <span className="flex size-8 items-center justify-center rounded-[10px] bg-ai-soft text-ai" aria-hidden>{s.icon}</span>
              <span>
                <span className="block text-pretty text-[13.5px] font-semibold leading-snug text-ink">{s.q}</span>
                <span className="mt-1 block text-[12.5px] leading-snug text-ink-3">{s.sub}</span>
              </span>
            </button>
          </motion.li>
        ))}
      </ul>
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
  if (!items.length) return null;
  let h = 0, a = 0;
  return (
    <section aria-labelledby="match-story" className="mt-7">
      <h3 id="match-story" className="mb-2.5 text-[14px] font-semibold tracking-[-0.01em] text-ink">Match story</h3>
      <ol className="overflow-hidden rounded-2xl bg-surface-2 ring-1 ring-line">
        {items.map((m, i) => {
          if (m.type === "goal") { if (m.team === "home") h++; else a++; }
          const who = m.detail === "own_goal" ? "Own goal" : names.get(m.player_id ?? -1) ?? "Unknown";
          const what = m.type === "card" ? "Red card" : m.detail === "penalty" ? "Penalty" : m.detail === "own_goal" ? "" : "Goal";
          return (
            <li key={m.event_id} className={i ? "border-t border-line" : ""}>
              <button type="button" onClick={() => focusEvent(m.event_id)}
                className="flex w-full items-center gap-3 px-3.5 py-2.5 text-left transition-colors duration-150 hover:bg-surface-3">
                <span className="numeral w-11 text-[18px] leading-none text-ink">{clock(m.period, m.minute)}</span>
                <span className="h-5 w-1 shrink-0 rounded-full" style={{ background: `var(--${m.team})` }} aria-hidden />
                <span className="min-w-0 flex-1 truncate text-[13.5px] font-semibold text-ink">
                  {who}
                  {what && <span className="ml-2 text-[12.5px] font-normal text-ink-3">{what}</span>}
                </span>
                {m.type === "goal" && <span className="numeral text-[18px] leading-none text-ink-2" aria-label={`Score ${h}-${a}`}>{h}-{a}</span>}
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function UserTurn({ text }: { text: string }) {
  return (
    <Message from="user">
      <MessageContent className="rounded-[20px] rounded-br-md bg-surface-3 px-4 py-2.5 text-[14px] font-medium leading-snug text-ink">
        {text}
      </MessageContent>
    </Message>
  );
}

/** One agent turn: its thinking, every tool call with what it found, then the grounded answer. */
function AgentTurn({ m }: { m: ChatMessage }) {
  const writing = m.streaming && !m.content;
  return (
    <Message from="assistant" className="max-w-full">
      <div className="flex gap-3">
        <Orb small active={m.streaming} />
        <MessageContent className="w-full min-w-0 gap-3">
          {m.reasoning.trim() && (
            <Reasoning isStreaming={m.streaming && !m.content} defaultOpen className="mb-0">
              <ReasoningTrigger className="text-[12.5px] text-ink-3 hover:text-ink-2" />
              <ReasoningContent className="mt-2 border-l border-[var(--ai-line)] pl-3 text-[12.5px] leading-[1.55] text-ink-3">
                {m.reasoning}
              </ReasoningContent>
            </Reasoning>
          )}
          {m.steps.length > 0 && (
            <ol aria-label="What the analyst did" className="space-y-1.5">
              {m.steps.map((s, i) => <Step key={i} step={s} />)}
            </ol>
          )}
          {writing && (
            <Shimmer className="text-[13px] font-medium">{m.steps.length ? "Writing the answer" : "Reading the match"}</Shimmer>
          )}
          {m.content && <Answer m={m} />}
          {!m.streaming && <Moments m={m} />}
          {!m.streaming && m.content && <FollowUps />}
        </MessageContent>
      </div>
    </Message>
  );
}

const STEP_ARG_LABEL: Record<string, string> = {
  from_minute: "from minute", to_minute: "to minute", period: "half", team: "team", types: "looking for",
  limit: "how many", sort: "ranked by", change: "change", query: "search", player_id: "player", event_id: "moment",
};

function Step({ step }: { step: AgentStep }) {
  const teams = useMatch((s) => s.data?.match.teams);
  const state = step.state === "running" ? "input-available" : step.state === "error" ? "output-error" : "output-available";
  const args = Object.entries(step.args).filter(([k, v]) => v != null && v !== "" && k in STEP_ARG_LABEL);
  const show = (k: string, v: unknown) =>
    k === "team" && (v === "home" || v === "away") && teams ? teams[v].name : Array.isArray(v) ? v.join(", ") : String(v);
  return (
    <li>
      <Tool className="mb-0 rounded-xl border-0 bg-surface-2 ring-1 ring-line">
        <ToolHeader type={`tool-${step.name}`} state={state} title={STEP_TITLE[step.name] ?? step.name}
          className="gap-2 px-3 py-2 text-left text-ink [&_.font-medium]:text-[13px] [&_.font-medium]:text-ink-2 [&>div]:min-w-0 [&>div]:flex-1 [&>div>span:first-of-type]:flex-1" />
        <ToolContent className="px-3 pb-3 text-[12.5px] leading-[1.5]">
          <p className="text-ink-2">{step.summary ?? "Working on it."}</p>
          {args.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="What it looked up">
              {args.map(([k, v]) => (
                <li key={k} className="rounded-full bg-surface-3 px-2 py-0.5 text-[11.5px] text-ink-3">
                  {STEP_ARG_LABEL[k]} <span className="text-ink-2">{show(k, v)}</span>
                </li>
              ))}
            </ul>
          )}
        </ToolContent>
      </Tool>
    </li>
  );
}

/** The grounded answer as streaming markdown; [[ev:...]] / [[seq:...]] citations become chips that drive the pitch. */
function Answer({ m }: { m: ChatMessage }) {
  const data = useMatch((s) => s.data);
  const markdown = useMemo(() => {
    const clean = undash(m.content.replace(/\[\[[^\]]*$/, ""));
    return clean.replace(/\[\[(ev|seq):([^\]]+)\]\]/g, (_, kind: string, id: string) => {
      let label = m.labels[`${kind}:${id}`];
      if (!label && kind === "ev") { const e = data?.eventById.get(id); label = e ? describe(e) : ""; }
      if (!label && kind === "seq") { const s = resolveSequence(data, id); label = s ? `${s.start.label} ${s.players[0] ?? ""} move` : ""; }
      return ` [${(label || "this moment").replace(/[[\]]/g, "")}](#cite:${kind}:${id})`;
    });
  }, [m.content, m.labels, data]);
  return (
    <MessageResponse className="answer text-[15px] leading-[1.7] text-ink [&_p]:text-pretty [&_strong]:font-semibold [&_strong]:text-ink"
      components={MARKDOWN}>
      {markdown}
    </MessageResponse>
  );
}

const MARKDOWN: Components = { a: ({ href, children }) => <CitationLink href={href}>{children}</CitationLink> };

function CitationLink({ href, children }: Pick<ComponentProps<"a">, "href" | "children">) {
  const data = useMatch((s) => s.data);
  const focusEvent = useMatch((s) => s.focusEvent);
  const focusSequence = useMatch((s) => s.focusSequence);
  const cite = href?.startsWith("#cite:") ? href.slice(6) : null;
  if (!cite) return <a href={href} className="text-ai underline underline-offset-2">{children}</a>;
  const kind = cite.startsWith("ev:") ? "ev" : "seq";
  const id = cite.slice(kind.length + 1);
  const side = kind === "ev" ? data?.eventById.get(id)?.team : resolveSequence(data, id)?.team;
  return (
    <button type="button" onClick={() => (kind === "ev" ? focusEvent(id) : focusSequence(id))}
      className="mx-0.5 inline-flex min-h-6 translate-y-[-1px] items-center gap-1.5 whitespace-nowrap rounded-full bg-surface-3 py-[1px] pl-2 pr-2.5 align-middle text-[13px] font-semibold leading-5 text-ink ring-1 ring-line-strong transition-[background-color,box-shadow,transform] duration-150 ease-out hover:bg-ai-soft hover:ring-[var(--ai-line)] active:scale-[0.97]">
      <span className="size-2 shrink-0 rounded-[3px]" style={{ background: side ? `var(--${side})` : "var(--ink-3)" }} aria-hidden />
      {children}
    </button>
  );
}

/** Next questions, plus one-tap actions that drive the UI. */
function FollowUps() {
  const chat = useMatch((s) => s.chat);
  const ask = useMatch((s) => s.ask);
  const playHighlights = useMatch((s) => s.playHighlights);
  const setRightTab = useMatch((s) => s.setRightTab);
  const asked = new Set(chat.filter((c) => c.role === "user").map((c) => c.content));
  const questions = FOLLOW_UPS.filter((q) => !asked.has(q)).slice(0, 3);
  const pill = "h-8 rounded-full border-0 bg-surface-2 px-3 text-[12.5px] font-medium text-ink-2 ring-1 ring-line hover:bg-surface-3 hover:text-ink";
  return (
    <div role="group" aria-label="Next steps" className="space-y-1.5 pt-1">
      <Suggestions className="gap-1.5">
        <Suggestion suggestion="Play the highlights" onClick={playHighlights} className={pill}>
          <Play size={12} weight="fill" aria-hidden />Play the highlights
        </Suggestion>
        <Suggestion suggestion="Try a what-if" onClick={() => setRightTab("whatif")} className={pill}>
          Try a what-if<ArrowRight size={12} weight="bold" aria-hidden />
        </Suggestion>
      </Suggestions>
      <Suggestions className="gap-1.5">
        {questions.map((q) => (
          <Suggestion key={q} suggestion={q} onClick={(s) => void ask(s)} className={`${pill} hover:bg-ai-soft hover:ring-[var(--ai-line)]`}>
            <QuestionIcon size={12} weight="bold" aria-hidden />{q}
          </Suggestion>
        ))}
      </Suggestions>
    </div>
  );
}

function Moments({ m }: { m: ChatMessage }) {
  const data = useMatch((s) => s.data);
  const focusEvent = useMatch((s) => s.focusEvent);
  const focus = useMatch((s) => s.focus);
  if (!data) return null;
  const ids = [...new Set([...m.content.matchAll(/\[\[ev:([^\]]+)\]\]/g)].map((x) => x[1]))].filter((id) => data.eventById.has(id));
  if (!ids.length) return null;
  return (
    <section aria-label="Moments in this answer" className="pt-1">
      <h3 className="mb-2.5 text-[14px] font-semibold tracking-[-0.01em] text-ink">Moments in this answer</h3>
      <ol className="overflow-hidden rounded-2xl bg-surface-2 ring-1 ring-line">
        {ids.map((id, i) => {
          const e = data.eventById.get(id)!;
          const active = focus?.kind === "event" && focus.id === id;
          const what = describe(e).replace(/^\S+\s/, "").replace(e.player ?? "", "").trim() || e.type;
          return (
            <li key={id} className={i ? "border-t border-line" : ""}>
              <button type="button" onClick={() => focusEvent(id)} aria-current={active || undefined}
                className={`flex w-full items-center gap-3 px-3.5 py-2.5 text-left transition-colors duration-150 ${active ? "bg-surface-4" : "hover:bg-surface-3"}`}>
                <span className="numeral w-11 text-[18px] leading-none text-ink">{clock(e.period, e.minute)}</span>
                <span className="h-6 w-1 shrink-0 rounded-full" style={{ background: `var(--${e.team})` }} aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13.5px] font-semibold text-ink">{e.player}</span>
                  <span className="block text-[12.5px] text-ink-3">{what.charAt(0).toUpperCase() + what.slice(1)}</span>
                </span>
                {isShot(e.type) && e.xg != null && (
                  <span className="tabular text-right text-[12px] leading-tight text-ink-3">
                    <span className="font-semibold text-ink">{Math.round(e.xg * 100)}%</span><br />chance
                  </span>
                )}
                <CaretRight size={14} weight="bold" className="shrink-0 text-ink-4" aria-hidden />
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/** The AI identity: a violet sphere. While the analyst works, a soft ring breathes around it. */
function Orb({ small, active }: { small?: boolean; active?: boolean }) {
  const s = small ? 26 : 36;
  return (
    <span className="relative shrink-0" style={{ width: s, height: s }} aria-hidden>
      {active && <span className="absolute -inset-1 rounded-full ring-2 ring-[var(--ai-line)] motion-safe:animate-pulse" />}
      <span className="absolute inset-0 rounded-full"
        style={{
          background: "radial-gradient(circle at 30% 30%, color-mix(in oklab, var(--ai) 45%, var(--ink)), var(--ai) 45%, color-mix(in oklab, var(--ai-2) 70%, var(--bg)) 100%)",
          boxShadow: "0 0 18px color-mix(in oklab, var(--ai-2) 45%, transparent)",
        }} />
    </span>
  );
}
