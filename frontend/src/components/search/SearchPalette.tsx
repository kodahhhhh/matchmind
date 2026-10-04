import { useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import { AnimatePresence, motion } from "motion/react";
import { api } from "../../api/client";
import type { PlayerHit, SearchResult } from "../../api/types";
import { usePlayerUi } from "../../store/ui";
import { useMatch } from "../../store/match";
import { useUi } from "../../store/ui";

const EXAMPLES = ["Mbappé penalty", "header from a corner", "long ball over the top", "counter-attack goal", "shot from outside the box"];

/** ⌘K palette: hybrid search over Luna's commentary across every match. */
export function SearchPalette() {
  const open = useUi((s) => s.searchOpen);
  const setOpen = useUi((s) => s.setSearchOpen);

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

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 flex items-start justify-center bg-black/55 px-4 pt-[12vh] backdrop-blur-sm"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={() => setOpen(false)}>
          <motion.div initial={{ opacity: 0, y: -8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.16 }} onMouseDown={(e) => e.stopPropagation()}
            className="w-full max-w-[720px] overflow-hidden rounded-[22px] bg-surface-1 shadow-[0_40px_120px_-20px_rgba(0,0,0,0.9)] ring-1 ring-white/12">
            <Palette onClose={() => setOpen(false)} />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function Palette({ onClose }: { onClose: () => void }) {
  const [q, setQ] = useState("");
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

  return (
    <div onKeyDown={onKey}>
      <div className="flex items-center gap-3 border-b border-line px-5">
        <svg width="18" height="18" viewBox="0 0 16 16" fill="none" className="text-ink-3"><circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.6" /><path d="m11 11 3.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search every moment: “Messi free kick”, “header from a corner”…"
          className="h-[60px] min-w-0 flex-1 bg-transparent text-[16px] text-ink placeholder:text-ink-4 focus:outline-none" />
        {loading && <span className="h-4 w-4 animate-spin rounded-full border-2 border-ink-4 border-t-ai" />}
        {onMatch && (
          <div className="flex rounded-lg bg-surface-2 p-0.5 text-[11.5px]">
            {(["all", "match"] as const).map((s) => (
              <button key={s} onClick={() => setScope(s)}
                className={`rounded-md px-2.5 py-1 font-medium transition ${scope === s ? "bg-surface-4 text-ink" : "text-ink-3"}`}>{s === "all" ? "All matches" : "This match"}</button>
            ))}
          </div>
        )}
      </div>

      <div ref={listRef} className="scroll-thin max-h-[56vh] overflow-y-auto p-2">
        {q.trim().length < 2 ? (
          <div className="p-3">
            <div className="eyebrow mb-2.5">Try</div>
            <div className="flex flex-wrap gap-1.5">
              {EXAMPLES.map((x) => (
                <button key={x} onClick={() => setQ(x)} className="rounded-lg bg-surface-2 px-3 py-1.5 text-[13px] text-ink-2 ring-1 ring-line transition hover:bg-surface-3 hover:text-ink">{x}</button>
              ))}
            </div>
            <p className="mt-4 text-[12px] leading-relaxed text-ink-4">Searches GPT-6 Luna's commentary for every move in 493 matches, by meaning (Qwen3 embeddings on Cloudflare Workers AI + pgvector) and by keyword.</p>
          </div>
        ) : results.length === 0 && players.length === 0 && !loading ? (
          <div className="px-4 py-10 text-center text-[13px] text-ink-3">No moments found for “{q}”.</div>
        ) : (
          <>
          {players.length > 0 && (
            <div className="mb-1 border-b border-line pb-2">
              <div className="eyebrow px-3 pb-1 pt-1">Players</div>
              {players.map((p) => (
                <button key={p.player_id} onClick={() => { onClose(); usePlayerUi.getState().openPlayer(p.player_id); }}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition hover:bg-surface-3">
                  {p.photo_url ? <img src={p.photo_url} alt="" className="h-8 w-8 rounded-full object-cover object-top" />
                    : <span className="display flex h-8 w-8 items-center justify-center rounded-full bg-surface-3 text-[13px] text-ink-2">{p.short_name.slice(0, 2).toUpperCase()}</span>}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[14px] font-semibold text-ink">{p.short_name || p.name}</span>
                    <span className="block truncate text-[11.5px] text-ink-3">{[p.position, p.nationality, p.teams.slice(0, 3).join(", ")].filter(Boolean).join(" · ")}</span>
                  </span>
                  {p.vaep_per90 != null
                    ? <span className="text-[12px] tabular text-ink-3"><span className="font-semibold text-ai">{p.vaep_per90.toFixed(2)}</span> VAEP/90</span>
                    : p.in_dataset === false && <span className="rounded-md bg-surface-4 px-1.5 py-0.5 text-[10.5px] text-ink-3">profile only</span>}
                </button>
              ))}
            </div>
          )}
          {results.length > 0 && <div className="eyebrow px-3 pb-1 pt-1">Moments</div>}
          {results.map((r, i) => (
            <button key={r.sequence_id} data-i={i} onClick={() => go(r)} onMouseEnter={() => setSel(i)}
              className={`flex w-full gap-3.5 rounded-xl px-3 py-2.5 text-left transition ${i === sel ? "bg-surface-3" : ""}`}>
              <span className="display w-12 shrink-0 pt-[1px] text-right text-[17px] text-ink">{r.label}</span>
              <span className="min-w-0 flex-1">
                {r.match && (
                  <span className="mb-0.5 flex items-center gap-1.5 text-[11.5px] text-ink-3">
                    <span className="h-2 w-2 rounded-full" style={{ background: r.match.home_color }} />{r.match.home}
                    <span className="text-ink-4">v</span>
                    <span className="h-2 w-2 rounded-full" style={{ background: r.match.away_color }} />{r.match.away}
                    <span className="text-ink-4">· {r.match.competition} {r.match.season}</span>
                  </span>
                )}
                <span className="block text-[14px] leading-snug text-ink-2"><Highlight text={r.text} q={q} /></span>
              </span>
              {i === sel && <span className="self-center rounded-md bg-surface-4 px-1.5 py-0.5 text-[10.5px] text-ink-3">↵</span>}
            </button>
          ))}
          </>
        )}
      </div>
      <div className="flex items-center gap-4 border-t border-line px-5 py-2.5 text-[11px] text-ink-4">
        <span><Kbd>↑</Kbd><Kbd>↓</Kbd> navigate</span><span><Kbd>↵</Kbd> open moment</span><span><Kbd>esc</Kbd> close</span>
        <span className="ml-auto flex items-center gap-1.5"><span className="h-1.5 w-1.5 rounded-full bg-ai" />hybrid search · Qwen3 embeddings + full text</span>
      </div>
    </div>
  );
}

function Highlight({ text, q }: { text: string; q: string }) {
  const words = q.trim().split(/\s+/).filter((w) => w.length > 2).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!words.length) return <>{text}</>;
  const parts = text.split(new RegExp(`(${words.join("|")})`, "gi"));
  return <>{parts.map((p, i) => (i % 2 ? <mark key={i} className="rounded bg-ai-soft px-0.5 text-ink">{p}</mark> : p))}</>;
}

function Kbd({ children }: { children: ReactNode }) {
  return <span className="mr-1 rounded bg-surface-3 px-1.5 py-0.5 font-mono text-[10px] text-ink-3">{children}</span>;
}

export function SearchButton({ compact }: { compact?: boolean }) {
  const setOpen = useUi((s) => s.setSearchOpen);
  return (
    <button onClick={() => setOpen(true)}
      className="flex items-center gap-2.5 rounded-xl bg-surface-2 py-2 pl-3 pr-2 text-[13px] text-ink-3 ring-1 ring-line transition hover:bg-surface-3 hover:text-ink-2">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.6" /><path d="m11 11 3.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
      {!compact && <span>Search moments</span>}
      <span className="rounded-md bg-surface-4 px-1.5 py-0.5 font-mono text-[10.5px] text-ink-3">⌘K</span>
    </button>
  );
}
