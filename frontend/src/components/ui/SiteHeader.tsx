import type { ReactNode, RefObject } from "react";
import { Link, NavLink } from "react-router";
import { motion, useScroll, useTransform } from "motion/react";
import { Logo } from "./Logo";
import { SearchButton } from "../search/SearchPalette";

/** Site header for the full-page screens: logo, primary nav with the current page marked, search.
 *  Sticky inside the page's scroll container; its backdrop fades in once the page scrolls. */
export function SiteHeader({ scroller }: { scroller: RefObject<HTMLDivElement | null> }) {
  const { scrollY } = useScroll({ container: scroller });
  const backdrop = useTransform(scrollY, [0, 48], [0, 1]);
  return (
    <header className="sticky top-0 z-20">
      <motion.div aria-hidden className="absolute inset-0 border-b border-line bg-bg/85 backdrop-blur-xl" style={{ opacity: backdrop }} />
      <div className="relative mx-auto flex h-16 max-w-[1280px] items-center justify-between gap-4 px-5 md:h-[72px] md:px-8">
        <Link to="/" aria-label="MatchMind home" className="rounded-xl"><Logo size={30} /></Link>
        <nav aria-label="Primary" className="flex items-center gap-1 md:gap-1.5">
          <Item to="/" end>Matches</Item>
          <Item to="/players">Underrated players</Item>
          <Item to="/backtest">Market backtest</Item>
          <SearchButton className="ml-2 hidden rounded-full sm:flex" />
          <SearchButton compact className="rounded-full sm:hidden" />
        </nav>
      </div>
    </header>
  );
}

function Item({ to, end, children }: { to: string; end?: boolean; children: ReactNode }) {
  return (
    <NavLink to={to} end={end}
      className={({ isActive }) => `hidden rounded-full px-3 py-2 text-[14px] font-medium transition-colors duration-150 md:block ${isActive ? "bg-surface-2 text-ink" : "text-ink-2 hover:bg-surface-2 hover:text-ink"}`}>
      {children}
    </NavLink>
  );
}
