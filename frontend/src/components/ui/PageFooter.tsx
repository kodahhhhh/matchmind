import { Link } from "react-router";
import { Logo } from "./Logo";

/** Footer for the full-page screens (landing, players, backtest). */
export function PageFooter({ className = "mt-28" }: { className?: string }) {
  return (
    <footer className={`border-t border-line ${className}`}>
      <div className="mx-auto flex max-w-[1280px] flex-col gap-6 px-5 py-10 md:flex-row md:items-center md:justify-between md:px-8">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:gap-6">
          <Logo size={26} />
          <p className="text-[13.5px] text-ink-3">Event data from StatsBomb Open Data. Prices from Pinnacle and Polymarket.</p>
        </div>
        <nav aria-label="Footer" className="flex flex-wrap gap-x-5 gap-y-2 text-[13.5px] text-ink-3">
          <Link to="/" className="transition-colors duration-150 hover:text-ink">Matches</Link>
          <Link to="/players" className="transition-colors duration-150 hover:text-ink">Underrated players</Link>
          <Link to="/backtest" className="transition-colors duration-150 hover:text-ink">Versus the bookies</Link>
        </nav>
      </div>
    </footer>
  );
}

/** Shared error state for full-page screens: says what failed and offers a retry. */
export function LoadError({ title, onRetry }: { title: string; onRetry: () => void }) {
  return (
    <div role="alert" className="rounded-[20px] bg-surface-1 px-6 py-14 text-center ring-1 ring-line">
      <p className="text-[15px] font-medium text-ink">{title}</p>
      <p className="mt-1.5 text-[14px] text-ink-3">Check that the API is running, then try again.</p>
      <button type="button" onClick={onRetry}
        className="mt-5 rounded-full bg-surface-2 px-4 py-2 text-[13.5px] font-medium text-ink ring-1 ring-line transition-[background-color,transform] duration-150 ease-out hover:bg-surface-3 active:scale-[0.97]">
        Try again
      </button>
    </div>
  );
}
