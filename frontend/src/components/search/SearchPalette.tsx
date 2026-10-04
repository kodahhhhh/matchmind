import { useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import { motion } from "motion/react";
import { ArrowElbowDownLeft, MagnifyingGlass } from "@phosphor-icons/react";
import { api } from "../../api/client";
import type { PlayerHit, SearchResult } from "../../api/types";
import { usePlayerUi } from "../../store/ui";
import { useMatch } from "../../store/match";
import { useUi } from "../../store/ui";
import { initials, trapTab } from "../ui/focusTrap";

const EXAMPLES = ["Mbappé penalty", "header from a corner", "long ball over the top", "counter-attack goal", "shot from outside the box"];

/** ⌘K palette: hybrid search over Luna's commentary across every match.
 *  Opened many times a day, so it appears instantly: no scale, only a very short backdrop fade. */
export function SearchPalette() {
  const open = useUi((s) => s.searchOpen);
  const setOpen = useUi((s) => s.setSearchOpen);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!useUi.getState().searchOpen);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);

  // hand focus back to whatever opened the palette
  useEffect(() => {
    if (!open) return;
    const trigger = document.activeElement as HTMLElement | null;
    return () => { if (trigger?.isConnected) trigger.focus({ preventScroll: true }); };
  }, [open]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-bg/70 px-3 pt-[10vh] opacity-100 backdrop-blur-sm transition-opacity duration-100 ease-out starting:opacity-0 motion-reduce:transition-none sm:px-4 sm:pt-[12vh]"
      onMouseDown={() => setOpen(false)}>
      <div ref={panel} role="dialog" aria-modal="true" aria-label="Search moments" onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => trapTab(e, panel.current)}
        className="w-full max-w-[720px] overflow-hidden rounded-[20px] bg-surface-1 shadow-[0_40px_120px_-20px_rgba(0,0,0,0.9)] ring-1 ring-line-strong">
        <Palette onClose={() => setOpen(false)} />
      </div>
    </div>
  );
}

function Palette({ onClose }: { onClose: () => void }) {
  const [q, setQ] = useState(() => useUi.getState().searchSeed);
  const [scope, setScope] = useState<"all" | "match">("all");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [players, setPlayers] = useState<PlayerHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [sel, setSel] = useState(0);
  const navigate = useNavigate();
  const location = useLocation();
  const matchId = useMatch((s) => s.matchId);
  const focusSequence = useMatch((s) => s.focusSequence);
  const setPendingFocus = useMatch((s) => s.setPendingFocus);
  const onMatch = location.pathname.startsWith("/match/") && matchId;
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const query = q.trim();
    if (query.length < 2) { setResults([]); setPlayers([]); return; }
    let live = true;
    const t = setTimeout(() => {
      setLoading(true);
      api.searchPlayers(query).then((p) => live && setPlayers(p.slice(0, 4))).catch(() => live && setPlayers([]));
      api.search(query, scope === "match" && onMatch ? matchId! : undefined)
        .then((r) => { if (live) { setResults(r); setSel(0); } })
        .catch(() => live && setResults([]))
        .finally(() => live && setLoading(false));
    }, 220);
    return () => { live = false; clearTimeout(t); };
  }, [q, scope, onMatch, matchId]);

  const go = (r: SearchResult) => {
    onClose();
    if (onMatch && r.match_id === matchId) {
      focusSequence(r.sequence_id);
      return;
    }
    setPendingFocus({ seq: r.sequence_id });
    navigate(`/match/${encodeURIComponent(r.match_id)}`);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, results.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    if (e.key === "Enter" && results[sel]) go(results[sel]);
  };

  useEffect(() => {
    listRef.current?.querySelector(`[data-i="${sel}"]`)?.scrollIntoView({ block: "nearest" });
  }, [sel]);

  const searching = q.trim().length >= 2;
  const firstLoad = loading && results.length === 0 && players.length === 0;

  return (
    <div onKeyDown={onKey}>
      <div className="flex items-center gap-3 border-b border-line px-4 transition-colors duration-150 focus-within:border-line-strong sm:px-5">
        <MagnifyingGlass size={18} className="shrink-0 text-ink-3" aria-hidden />
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search moments"
          placeholder="Describe a moment, like “Messi free kick”"
          className="h-[60px] min-w-0 flex-1 bg-transparent text-[16px] text-ink outline-none placeholder:text-ink-4" />
        {onMatch && (
          <div role="group" aria-label="Search scope" className="flex shrink-0 gap-0.5 rounded-full bg-surface-2 p-0.5 text-[12.5px] ring-1 ring-line">
            {(["all", "match"] as const).map((s) => {
              const on = scope === s;
              return (
                <button key={s} type="button" aria-pressed={on} onClick={() => setScope(s)}
                  className={`relative whitespace-nowrap rounded-full px-3 py-1 font-medium transition-colors duration-150 ${on ? "text-bg" : "text-ink-3 hover:text-ink"}`}>
                  {on && <motion.span layoutId="search-scope-pill" className="absolute inset-0 rounded-full bg-ink" transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }} />}
                  <span className="relative">{s === "all" ? "All matches" : "This match"}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      <p role="status" className="sr-only">
        {searching && !loading ? `${results.length} moments${players.length ? ` and ${players.length} players` : ""} found` : loading ? "Searching" : ""}
      </p>

      <div ref={listRef} className="scroll-thin max-h-[56vh] overflow-y-auto overscroll-contain p-2">
        {!searching ? (
          <div className="p-3">
            <h2 className="mb-3 text-[13px] font-semibold text-ink-3">Try</h2>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((x) => (
                <button key={x} type="button" onClick={() => setQ(x)}
                  className="rounded-full bg-surface-2 px-3.5 py-1.5 text-[13px] text-ink-2 ring-1 ring-line transition-[background-color,color,transform] duration-150 ease-out hover:bg-surface-3 hover:text-ink active:scale-[0.97]">{x}</button>
              ))}
            </div>
            <p className="mt-5 max-w-[60ch] text-pretty text-[13px] leading-[1.6] text-ink-3">
              Searches GPT-6 Luna's commentary for every move in 493 matches, by meaning (Qwen3 embeddings on Cloudflare Workers AI and pgvector) and by keyword.
            </p>
          </div>
        ) : firstLoad ? (
          <div aria-hidden className="space-y-1 p-1">
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className="flex gap-3.5 rounded-xl px-3 py-3">
                <span className="h-4 w-10 shrink-0 rounded-full bg-surface-2 motion-safe:animate-pulse" />
                <span className="flex-1 space-y-2"><span className="block h-3 w-40 rounded-full bg-surface-2 motion-safe:animate-pulse" /><span className="block h-3.5 w-full rounded-full bg-surface-2 motion-safe:animate-pulse" /></span>
              </div>
            ))}
          </div>
        ) : results.length === 0 && players.length === 0 && !loading ? (
          <div className="px-4 py-12 text-center">
            <p className="text-[15px] font-medium text-ink">No moments match “{q.trim()}”</p>
            <p className="mt-1.5 text-[14px] text-ink-3">Try fewer words, or describe the action, like “header from a corner”.</p>
          </div>
        ) : (
          <div className={`transition-opacity duration-150 ${loading ? "opacity-60" : "opacity-100"}`}>
          {players.length > 0 && (
            <div role="group" aria-labelledby="search-players" className="mb-1 border-b border-line pb-2">
              <h2 id="search-players" className="px-3 pb-1.5 pt-2 text-[13px] font-semibold text-ink-3">Players</h2>
              {players.map((p) => (
                <button key={p.player_id} type="button" onClick={() => { onClose(); usePlayerUi.getState().openPlayer(p.player_id); }}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition-colors duration-150 hover:bg-surface-3">
                  {p.photo_url ? <img src={p.photo_url} alt="" className="size-9 shrink-0 rounded-full object-cover object-top outline outline-1 -outline-offset-1 outline-white/10" />
                    : <span className="grid size-9 shrink-0 place-items-center rounded-full bg-surface-3 text-[13px] font-semibold text-ink-2">{initials(p.short_name || p.name)}</span>}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[14.5px] font-medium text-ink">{p.short_name || p.name}</span>
                    <span className="block truncate text-[12.5px] text-ink-3">{[[p.position, p.nationality].filter(Boolean).join(", "), p.teams.slice(0, 3).join(", ")].filter(Boolean).join(" · ")}</span>
                  </span>
                  {p.vaep_per90 != null
                    ? <span className="tabular shrink-0 text-[12.5px] text-ink-3"><span className="font-medium text-ink">{p.vaep_per90.toFixed(2)}</span> value added per 90</span>
                    : p.in_dataset === false && <span className="shrink-0 rounded-full bg-surface-3 px-2.5 py-0.5 text-[12px] text-ink-3">Profile only</span>}
                </button>
              ))}
            </div>
          )}
          {results.length > 0 && <h2 id="search-moments" className="px-3 pb-1.5 pt-2 text-[13px] font-semibold text-ink-3">Moments</h2>}
          <div role="group" aria-labelledby={results.length ? "search-moments" : undefined}>
          {results.map((r, i) => (
            <button key={r.sequence_id} type="button" data-i={i} onClick={() => go(r)} onMouseEnter={() => setSel(i)}
              className={`flex w-full gap-3.5 rounded-xl px-3 py-2.5 text-left ${i === sel ? "bg-surface-3" : ""}`}>
              <span className="numeral w-12 shrink-0 pt-[1px] text-right text-[17px] text-ink">{r.label}</span>
              <span className="min-w-0 flex-1">
                {r.match && (
                  <span className="mb-0.5 flex min-w-0 items-center gap-1.5 text-[12.5px] text-ink-3">
                    <span className="size-2 shrink-0 rounded-[2px]" style={{ background: r.match.home_color }} />
                    <span className="truncate">{r.match.home}</span>
                    <span className="text-ink-4">v</span>
                    <span className="size-2 shrink-0 rounded-[2px]" style={{ background: r.match.away_color }} />
                    <span className="truncate">{r.match.away}</span>
                    <span className="hidden shrink-0 text-ink-4 sm:inline">· {r.match.competition} {r.match.season}</span>
                  </span>
                )}
                <span className="block text-[14px] leading-[1.45] text-ink-2"><Highlight text={r.text} q={q} /></span>
              </span>
              {i === sel && <span className="hidden self-center rounded-full bg-surface-4 p-1 text-ink-3 sm:block" aria-hidden><ArrowElbowDownLeft size={12} weight="bold" /></span>}
            </button>
          ))}
          </div>
          </div>
        )}
      </div>
      <div className="hidden items-center gap-4 border-t border-line px-5 py-2.5 text-[12px] text-ink-3 sm:flex">
        <span><Kbd>↑</Kbd><Kbd>↓</Kbd> Move</span><span><Kbd>↵</Kbd> Open moment</span><span><Kbd>esc</Kbd> Close</span>
        <span className="ml-auto">Hybrid search: Qwen3 embeddings and full text</span>
      </div>
    </div>
  );
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

export function SearchButton({ compact, className = "rounded-full" }: { compact?: boolean; className?: string }) {
  const setOpen = useUi((s) => s.setSearchOpen);
  return (
    <button type="button" onClick={() => setOpen(true)} aria-label={compact ? "Search moments" : undefined}
      className={`flex items-center gap-2.5 bg-surface-2 py-2 pl-3 pr-2 text-[13px] text-ink-3 ring-1 ring-line transition-[background-color,color,box-shadow,transform] duration-150 ease-out hover:bg-surface-3 hover:text-ink-2 hover:ring-line-strong active:scale-[0.97] ${className}`}>
      <MagnifyingGlass size={15} aria-hidden />
      {!compact && <span>Search moments</span>}
      <kbd className="rounded-md bg-surface-4 px-1.5 py-0.5 font-mono text-[11px] text-ink-3">⌘K</kbd>
    </button>
  );
}
