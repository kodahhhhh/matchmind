import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import { motion } from "motion/react";
import { ArrowElbowDownLeft, MagnifyingGlass, Trophy, X } from "@phosphor-icons/react";
import { api } from "../../api/client";
import type { MatchCard, PlayerHit, SearchResult } from "../../api/types";
import { usePlayerUi, useUi } from "../../store/ui";
import { useMatch } from "../../store/match";
import { useCatalogue } from "../../store/catalogue";
import { FAMOUS, LITE_LABEL, compLabel, matchDate, matchPath, searchCompetitions, searchMatches } from "../../lib/matchSearch";
import { initials, trapTab } from "../ui/focusTrap";
import { undash } from "../../lib/format";

const EXAMPLES = ["Spain v England", "Champions League", "Messi", "header from a corner", "counter-attack goal"];

/** True on devices without a hover-capable pointer (phones, tablets): hide keyboard hints there. */
const touch = typeof window !== "undefined" && window.matchMedia?.("(hover: none)").matches;

/** One search for everything: matches (by team, competition or year), players, and moments described in plain words.
 *  Opened many times a day, so it appears instantly: no scale, only a very short backdrop fade. */
export function SearchPalette() {
  const open = useUi((s) => s.searchOpen);
  const setOpen = useUi((s) => s.setSearchOpen);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const typing = el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
      if (((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") || (e.key === "/" && !typing && !useUi.getState().searchOpen)) {
        e.preventDefault();
        setOpen(!useUi.getState().searchOpen);
      }
      if (e.key === "Escape" && useUi.getState().searchOpen) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);

  // hand focus back to whatever opened the palette
  useEffect(() => {
    if (!open) return;
    void useCatalogue.getState().load();
    const trigger = document.activeElement as HTMLElement | null;
    return () => { if (trigger?.isConnected) trigger.focus({ preventScroll: true }); };
  }, [open]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-bg/70 px-2 pt-2 opacity-100 backdrop-blur-sm transition-opacity duration-100 ease-out starting:opacity-0 motion-reduce:transition-none sm:px-4 sm:pt-[12vh]"
      onMouseDown={() => setOpen(false)}>
      <div ref={panel} role="dialog" aria-modal="true" aria-label="Search" onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => trapTab(e, panel.current)}
        className="w-full max-w-[720px] overflow-hidden rounded-[20px] bg-surface-1 shadow-[0_40px_120px_-20px_rgba(0,0,0,0.9)] ring-1 ring-line-strong">
        <Palette onClose={() => setOpen(false)} />
      </div>
    </div>
  );
}

interface Item { key: string; run: () => void }

function Palette({ onClose }: { onClose: () => void }) {
  const [q, setQ] = useState(() => useUi.getState().searchSeed);
  const [scope, setScope] = useState<"all" | "match">("all");
  // remote results remember which query they answer, so stale results never show as "nothing found"
  const [moments, setMoments] = useState<{ key: string; hits: SearchResult[] } | null>(null);
  const [people, setPeople] = useState<{ key: string; hits: PlayerHit[] } | null>(null);
  const [sel, setSel] = useState(0);
  const navigate = useNavigate();
  const location = useLocation();
  const matchId = useMatch((s) => s.matchId);
  const focusSequence = useMatch((s) => s.focusSequence);
  const setPendingFocus = useMatch((s) => s.setPendingFocus);
  const catalogue = useCatalogue();
  const onMatch = location.pathname.startsWith("/match/") && matchId;
  const listRef = useRef<HTMLDivElement>(null);
  const query = q.trim();
  const searching = query.length >= 2;
  const key = `${scope}|${query}`;
  const loading = searching && moments?.key !== key;
  // when the query clearly names matches, moments are a secondary guess: show fewer
  const allMoments = moments?.key === key ? moments.hits : [];
  const players = people?.key === key ? people.hits : [];

  const matches = useMemo(() => (searching && scope === "all" ? searchMatches(catalogue.matches, query, 5).map((h) => h.m) : []), [catalogue.matches, query, searching, scope]);
  const results = matches.length ? allMoments.slice(0, 3) : allMoments;
  const comps = useMemo(() => (searching && scope === "all" ? searchCompetitions(catalogue.competitions, query, 3) : []), [catalogue.competitions, query, searching, scope]);
  const famous = useMemo(() => FAMOUS.slice(0, 4).map((f) => ({ ...f, m: catalogue.byId.get(f.id) })).filter((f): f is typeof f & { m: MatchCard } => !!f.m), [catalogue.byId]);

  useEffect(() => {
    if (query.length < 2) return;
    let live = true;
    const k = `${scope}|${query}`;
    const t = setTimeout(() => {
      if (scope === "all") api.searchPlayers(query).then((p) => live && setPeople({ key: k, hits: p.slice(0, 4) })).catch(() => live && setPeople({ key: k, hits: [] }));
      api.search(query, scope === "match" && onMatch ? matchId! : undefined)
        .then((r) => live && setMoments({ key: k, hits: r.slice(0, 8) }))
        .catch(() => live && setMoments({ key: k, hits: [] }));
    }, 200);
    return () => { live = false; clearTimeout(t); };
  }, [query, scope, onMatch, matchId]);

  const openMatch = (id: string) => { onClose(); navigate(matchPath(id)); };
  const openMoment = (r: SearchResult) => {
    onClose();
    if (onMatch && r.match_id === matchId) { focusSequence(r.sequence_id); return; }
    setPendingFocus({ seq: r.sequence_id });
    navigate(matchPath(r.match_id));
  };
  const openComp = (name: string) => { onClose(); navigate(`/?comp=${encodeURIComponent(name)}#matches`); };
  const openPlayer = (id: number) => { onClose(); usePlayerUi.getState().openPlayer(id); };

  // one flat list for arrow keys, in the order the sections render
  const items: Item[] = searching
    ? [
        ...matches.map((m) => ({ key: m.match_id, run: () => openMatch(m.match_id) })),
        ...comps.map((c) => ({ key: `c:${c.name}`, run: () => openComp(c.name) })),
        ...players.map((p) => ({ key: `p:${p.player_id}`, run: () => openPlayer(p.player_id) })),
        ...results.map((r) => ({ key: r.sequence_id, run: () => openMoment(r) })),
      ]
    : [
        ...famous.map((f) => ({ key: f.id, run: () => openMatch(f.id) })),
        ...EXAMPLES.map((x) => ({ key: `x:${x}`, run: () => { setQ(x); setSel(0); } })),
      ];
  const idx = new Map(items.map((it, i) => [it.key, i]));
  const at = (key: string) => idx.get(key) ?? -1;

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, items.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    if (e.key === "Enter" && items[sel]) { e.preventDefault(); items[sel].run(); }
  };

  useEffect(() => {
    listRef.current?.querySelector(`[data-i="${sel}"]`)?.scrollIntoView({ block: "nearest" });
  }, [sel]);

  const row = (key: string, extra = "") => {
    const i = at(key);
    return {
      "data-i": i,
      "data-search-hit": "",
      onMouseEnter: () => setSel(i),
      className: `flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors duration-100 ${i === sel ? "bg-surface-3" : ""} ${extra}`,
    };
  };
  const nothing = searching && !loading && !matches.length && !comps.length && !players.length && !results.length;
  const momentsLoading = searching && loading && results.length === 0;

  return (
    <div onKeyDown={onKey}>
      <div className="flex items-center gap-3 border-b border-line pl-4 pr-2 transition-colors duration-150 focus-within:border-line-strong sm:pl-5 sm:pr-3">
        <MagnifyingGlass size={18} className="shrink-0 text-ink-3" aria-hidden />
        <input autoFocus value={q} onChange={(e) => { setQ(e.target.value); setSel(0); }} aria-label="Search matches, players and moments"
          placeholder="A team, a player or a moment" enterKeyHint="search" autoComplete="off" autoCorrect="off" spellCheck={false}
          className="h-[60px] min-w-0 flex-1 bg-transparent text-[16px] text-ink outline-none placeholder:text-ink-4" />
        {onMatch && (
          <div role="group" aria-label="Search scope" className="flex shrink-0 gap-0.5 rounded-full bg-surface-2 p-0.5 text-[12.5px] ring-1 ring-line">
            {(["all", "match"] as const).map((s) => {
              const on = scope === s;
              return (
                <button key={s} type="button" aria-pressed={on} onClick={() => { setScope(s); setSel(0); }}
                  className={`relative whitespace-nowrap rounded-full px-3 py-1 font-medium transition-colors duration-150 ${on ? "text-bg" : "text-ink-3 hover:text-ink"}`}>
                  {on && <motion.span layoutId="search-scope-pill" className="absolute inset-0 rounded-full bg-ink" transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }} />}
                  <span className="relative">{s === "all" ? "Everything" : "This match"}</span>
                </button>
              );
            })}
          </div>
        )}
        <button type="button" onClick={onClose} aria-label="Close search"
          className="grid size-9 shrink-0 place-items-center rounded-full text-ink-3 transition-colors duration-150 hover:bg-surface-3 hover:text-ink sm:hidden">
          <X size={16} weight="bold" aria-hidden />
        </button>
      </div>

      <p role="status" className="sr-only">
        {searching && !loading ? `${matches.length} matches, ${players.length} players and ${results.length} moments found` : loading ? "Searching" : ""}
      </p>

      <div ref={listRef} className="scroll-thin max-h-[calc(100dvh-80px)] overflow-y-auto overscroll-contain p-2 sm:max-h-[60vh]">
        {!searching ? (
          <>
            {famous.length > 0 && (
              <Section title="Famous matches">
                {famous.map(({ id, hook, m }) => (
                  <button key={id} type="button" onClick={() => openMatch(id)} {...row(id)}>
                    <MatchMini m={m} sub={hook} />
                  </button>
                ))}
              </Section>
            )}
            <Section title="Try searching for">
              <div className="flex flex-wrap gap-2 px-3 pb-2">
                {EXAMPLES.map((x) => {
                  const i = at(`x:${x}`);
                  return (
                    <button key={x} type="button" data-i={i} onClick={() => setQ(x)} onMouseEnter={() => setSel(i)}
                      className={`rounded-full px-3.5 py-1.5 text-[13px] ring-1 transition-[background-color,color,transform] duration-150 ease-out active:scale-[0.97] ${i === sel ? "bg-surface-3 text-ink ring-line-strong" : "bg-surface-2 text-ink-2 ring-line hover:bg-surface-3 hover:text-ink"}`}>{x}</button>
                  );
                })}
              </div>
              <p className="px-3 pb-2 pt-2 text-pretty text-[13px] leading-[1.6] text-ink-3">
                Moments are found by meaning, so describe them the way you would to a friend.
              </p>
            </Section>
          </>
        ) : nothing ? (
          <div className="px-4 py-12 text-center">
            <p className="text-[15px] font-medium text-ink">Nothing found for “{query}”</p>
            <p className="mt-1.5 text-pretty text-[14px] text-ink-3">Try a team or player name, or describe a moment, like “header from a corner”.</p>
          </div>
        ) : (
          <>
            {matches.length > 0 && (
              <Section title="Matches">
                {matches.map((m) => (
                  <button key={m.match_id} type="button" onClick={() => openMatch(m.match_id)} {...row(m.match_id)}>
                    <MatchMini m={m} sub={`${compLabel(m.competition, m.season)}${m.stage && m.stage !== "Regular Season" ? `, ${m.stage.toLowerCase()}` : ""} · ${matchDate(m)}${m.data_tier === "lite" ? ` · ${LITE_LABEL}` : ""}`} />
                    <Enter on={at(m.match_id) === sel} />
                  </button>
                ))}
              </Section>
            )}
            {comps.length > 0 && (
              <Section title="Competitions">
                {comps.map((c) => (
                  <button key={c.name} type="button" onClick={() => openComp(c.name)} {...row(`c:${c.name}`)}>
                    <span className="grid size-9 shrink-0 place-items-center rounded-full bg-surface-3 text-ink-2"><Trophy size={16} aria-hidden /></span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14.5px] font-medium text-ink">{c.name}</span>
                      <span className="tabular block text-[12.5px] text-ink-3">{c.total} matches{c.seasons > 1 ? ` across ${c.seasons} seasons` : ""}</span>
                    </span>
                    <Enter on={at(`c:${c.name}`) === sel} />
                  </button>
                ))}
              </Section>
            )}
            {players.length > 0 && (
              <Section title="Players">
                {players.map((p) => (
                  <button key={p.player_id} type="button" onClick={() => openPlayer(p.player_id)} {...row(`p:${p.player_id}`)}>
                    {p.photo_url ? <img src={p.photo_url} alt="" className="size-9 shrink-0 rounded-full object-cover object-top outline outline-1 -outline-offset-1 outline-white/10" />
                      : <span className="grid size-9 shrink-0 place-items-center rounded-full bg-surface-3 text-[13px] font-semibold text-ink-2">{initials(p.short_name || p.name)}</span>}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14.5px] font-medium text-ink">{p.short_name || p.name}</span>
                      <span className="block truncate text-[12.5px] text-ink-3">{[[p.position, p.nationality].filter(Boolean).join(", "), p.teams.slice(0, 3).join(", ")].filter(Boolean).join(" · ")}</span>
                    </span>
                    {p.in_dataset === false && <span className="shrink-0 rounded-full bg-surface-3 px-2.5 py-0.5 text-[12px] text-ink-3">Profile only</span>}
                    <Enter on={at(`p:${p.player_id}`) === sel} />
                  </button>
                ))}
              </Section>
            )}
            {(results.length > 0 || momentsLoading) && (
              <Section title={scope === "match" ? "Moments in this match" : "Moments"}>
                {momentsLoading ? (
                  <div aria-hidden className="space-y-1">
                    {Array.from({ length: 3 }, (_, i) => (
                      <div key={i} className="flex gap-3.5 rounded-xl px-3 py-3">
                        <span className="h-4 w-10 shrink-0 rounded-full bg-surface-2 motion-safe:animate-pulse" />
                        <span className="flex-1 space-y-2"><span className="block h-3 w-40 rounded-full bg-surface-2 motion-safe:animate-pulse" /><span className="block h-3.5 w-full rounded-full bg-surface-2 motion-safe:animate-pulse" /></span>
                      </div>
                    ))}
                  </div>
                ) : results.map((r) => (
                  <button key={r.sequence_id} type="button" onClick={() => openMoment(r)} {...row(r.sequence_id, "items-start")}>
                    <span className="numeral w-12 shrink-0 pt-[1px] text-right text-[17px] text-ink">{r.label}</span>
                    <span className="min-w-0 flex-1">
                      {r.match && (
                        <span className="mb-0.5 flex min-w-0 items-center gap-1.5 text-[12.5px] text-ink-3">
                          <span className="size-2 shrink-0 rounded-[2px]" style={{ background: r.match.home_color }} />
                          <span className="truncate">{r.match.home}</span>
                          <span className="text-ink-4">v</span>
                          <span className="size-2 shrink-0 rounded-[2px]" style={{ background: r.match.away_color }} />
                          <span className="truncate">{r.match.away}</span>
                          <span className="hidden shrink-0 text-ink-4 sm:inline">· {compLabel(r.match.competition, r.match.season)}</span>
                        </span>
                      )}
                      <span className="block text-[14px] leading-[1.45] text-ink-2"><Highlight text={undash(r.text)} q={q} /></span>
                    </span>
                    <Enter on={at(r.sequence_id) === sel} />
                  </button>
                ))}
              </Section>
            )}
          </>
        )}
      </div>
      {!touch && (
        <div className="hidden items-center gap-4 border-t border-line px-5 py-2.5 text-[12px] text-ink-3 sm:flex">
          <span><Kbd>↑</Kbd><Kbd>↓</Kbd> Move</span><span><Kbd>↵</Kbd> Open</span><span><Kbd>esc</Kbd> Close</span>
          <span className="ml-auto">Moments open on the pitch, ready to replay</span>
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div role="group" aria-label={title} className="mb-1 border-b border-line pb-2 last:mb-0 last:border-b-0 last:pb-0">
      <h2 className="px-3 pb-1.5 pt-2 text-[13px] font-semibold text-ink-3">{title}</h2>
      {children}
    </div>
  );
}

/** A match in one line: both teams with their colours and the score, with a sub line. */
function MatchMini({ m, sub }: { m: MatchCard; sub: string }) {
  return (
    <span className="min-w-0 flex-1">
      <span className="flex min-w-0 items-center gap-2 text-[14.5px] font-medium text-ink">
        <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: m.home.color }} aria-hidden />
        <span className="truncate">{m.home.name}</span>
        <span className="numeral shrink-0 text-[17px] leading-none text-ink">{m.home_score}<span className="px-1 text-ink-4">-</span>{m.away_score}</span>
        <span className="truncate">{m.away.name}</span>
        <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: m.away.color }} aria-hidden />
      </span>
      <span className="mt-0.5 block truncate text-[12.5px] text-ink-3">{sub}</span>
    </span>
  );
}

function Enter({ on }: { on: boolean }) {
  if (!on || touch) return null;
  return <span className="hidden shrink-0 self-center rounded-full bg-surface-4 p-1 text-ink-3 sm:block" aria-hidden><ArrowElbowDownLeft size={12} weight="bold" /></span>;
}

function Highlight({ text, q }: { text: string; q: string }) {
  const words = q.trim().split(/\s+/).filter((w) => w.length > 2).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!words.length) return <>{text}</>;
  const parts = text.split(new RegExp(`(${words.join("|")})`, "gi"));
  return <>{parts.map((p, i) => (i % 2 ? <mark key={i} className="bg-transparent font-medium text-ink">{p}</mark> : p))}</>;
}

function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="mr-1 rounded-md bg-surface-3 px-1.5 py-0.5 font-mono text-[11px] text-ink-2">{children}</kbd>;
}

/** Opens search. Compact shows only the icon (headers on phones). */
export function SearchButton({ compact, className = "rounded-full", label = "Search" }: { compact?: boolean; className?: string; label?: string }) {
  const setOpen = useUi((s) => s.setSearchOpen);
  return (
    <button type="button" onClick={() => setOpen(true)} aria-label={compact ? label : undefined}
      className={`flex items-center gap-2.5 bg-surface-2 py-2 pl-3 pr-2 text-[13px] text-ink-3 ring-1 ring-line transition-[background-color,color,box-shadow,transform] duration-150 ease-out hover:bg-surface-3 hover:text-ink-2 hover:ring-line-strong active:scale-[0.97] ${compact ? "pr-3" : ""} ${className}`}>
      <MagnifyingGlass size={15} aria-hidden />
      {!compact && <span className="pr-1">{label}</span>}
      {!touch && <kbd className="hidden rounded-md bg-surface-4 px-1.5 py-0.5 font-mono text-[11px] text-ink-3 sm:inline">⌘K</kbd>}
    </button>
  );
}
