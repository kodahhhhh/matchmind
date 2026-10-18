export function Logo({ size = 34 }: { size?: number }) {
  return (
    <span className="flex items-center gap-2.5">
      <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden>
        <defs>
          <linearGradient id="logo-g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#235c3c" />
            <stop offset="100%" stopColor="#123522" />
          </linearGradient>
        </defs>
        <rect width="40" height="40" rx="11" fill="url(#logo-g)" />
        <rect x="7" y="10" width="26" height="20" rx="2" fill="none" stroke="rgba(255,255,255,0.75)" strokeWidth="1.6" />
        <line x1="20" y1="10" x2="20" y2="30" stroke="rgba(255,255,255,0.75)" strokeWidth="1.6" />
        <circle cx="20" cy="20" r="3.6" fill="none" stroke="rgba(255,255,255,0.75)" strokeWidth="1.6" />
        <circle cx="28" cy="15" r="2.6" fill="#b6a4ff" />
      </svg>
      <span className="text-[17px] font-semibold tracking-[-0.02em] text-ink">MatchPulse</span>
    </span>
  );
}
