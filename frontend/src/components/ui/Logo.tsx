export function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden>
        <rect width="32" height="32" rx="8" fill="var(--surface-3)" />
        <rect x="5" y="8" width="22" height="16" rx="1.5" fill="none" stroke="var(--ink-2)" strokeWidth="1.4" />
        <line x1="16" y1="8" x2="16" y2="24" stroke="var(--ink-2)" strokeWidth="1.4" />
        <circle cx="16" cy="16" r="3" fill="none" stroke="var(--ink-2)" strokeWidth="1.4" />
        <circle cx="22.5" cy="12.5" r="2" fill="var(--ai)" />
      </svg>
      <span className="font-display text-lg font-semibold uppercase tracking-[0.12em] text-ink">MatchMind</span>
    </span>
  );
}
